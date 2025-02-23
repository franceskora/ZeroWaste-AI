import os
import json
import requests
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from dotenv import load_dotenv
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO

load_dotenv()
IBM_API_KEY = os.getenv("IBM_API_KEY")
IBM_DEPLOYMENT_ID = os.getenv("IBM_DEPLOYMENT_ID")
IBM_REGION = "us-south"

app = Flask(__name__)
# ✅ Add a secret key
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "supersecretkey")  # Use .env or fallback
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventory.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

bcrypt = Bcrypt(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
migrate = Migrate(app, db)  # Enables database migrations

class User(db.Model, UserMixin):  # ✅ Inherit UserMixin
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

    def is_active(self):  # ✅ Required by Flask-Login
        return True  

    def get_id(self):  # ✅ Ensures correct user loading
        return str(self.id)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/")
def landing_page():
    return render_template("landing.html")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username")
        password = bcrypt.generate_password_hash(request.form.get("password")).decode("utf-8")

        new_user = User(username=username, password=password)
        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for("login"))

    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()
        
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("dashboard"))  # Redirect to inventory page
        else:
            return "Invalid credentials. Try again."
    
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("landing_page"))

# 🔥 New Dashboard Route (Protect Inventory with Login)
@app.route("/dashboard")
@login_required
def dashboard():
    items = Inventory.query.all()
    
    for item in items:
        if item.expiry_date:
            try:
                item.expiry_date = datetime.strptime(item.expiry_date, "%Y-%m-%d").date()
            except ValueError:
                pass

    low_stock_items = check_low_stock()  # Identify items below threshold
    placed_orders = check_and_reorder()  # Trigger auto-restocking if needed

    return render_template('index.html', items=items, low_stock_items=low_stock_items, placed_orders=placed_orders)

class Inventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    expiry_date = db.Column(db.String(20), nullable=True)
    barcode = db.Column(db.String(50), nullable=True, unique=True)  
    supplier = db.Column(db.String(100), nullable=True)  # ✅ NEW: Supplier name
    restock_threshold = db.Column(db.Integer, nullable=True)  # ✅ NEW: Restock level
    order_quantity = db.Column(db.Integer, nullable=True)  # ✅ NEW: Order size

with app.app_context():
    db.create_all()  # ✅ Update the database
 

class Sales(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('inventory.id'), nullable=False)
    sale_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    quantity_sold = db.Column(db.Integer, nullable=False)


@app.route('/add', methods=['GET', 'POST'])
def add():
    if request.method == 'POST':
        names = request.form.getlist('name[]')
        quantities = request.form.getlist('quantity[]')
        expiry_dates = request.form.getlist('expiry_date[]')
        barcodes = request.form.getlist('barcode[]')
        suppliers = request.form.getlist('supplier[]')  # ✅ Get supplier
        order_quantities = request.form.getlist('order_quantity[]')  # ✅ Get order quantity

        for i in range(len(names)):
            if not names[i]:
                return jsonify({"error": "Product name is required"}), 400

            barcode_val = barcodes[i] if barcodes[i] else None
            expiry_date_val = expiry_dates[i] if expiry_dates[i] else None
            supplier_val = suppliers[i] if suppliers[i] else None
            order_quantity_val = int(order_quantities[i]) if order_quantities[i] else None

            existing_item = Inventory.query.filter_by(name=names[i], expiry_date=expiry_date_val).first()

            if existing_item:
                existing_item.quantity += int(quantities[i])
            else:
                new_item = Inventory(
                    name=names[i],
                    quantity=int(quantities[i]),
                    expiry_date=expiry_date_val,
                    barcode=barcode_val,
                    supplier=supplier_val,  # ✅ Save supplier
                    order_quantity=order_quantity_val  # ✅ Save order quantity
                )
                db.session.add(new_item)

        db.session.commit()
        return redirect(url_for("dashboard"))

    return render_template('add_item.html')


@app.route('/delete/<int:item_id>', methods=['GET'])
def delete_item(item_id):
    item = Inventory.query.get(item_id)
    if item:
        db.session.delete(item)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/get_items', methods=['GET'])
def get_items():
    items = Inventory.query.all()
    inventory_data = [{'name': item.name, 'quantity': item.quantity} for item in items]
    return jsonify(inventory_data)

@app.route('/update_supplier/<int:item_id>', methods=['POST'])
def update_supplier(item_id):
    """Update the supplier and order quantity for an inventory item."""
    data = request.json
    supplier = data.get("supplier")
    order_quantity = data.get("order_quantity")

    item = Inventory.query.get(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    if not supplier or not order_quantity:
        return jsonify({"error": "Supplier and order quantity are required"}), 400

    item.supplier = supplier
    item.order_quantity = order_quantity
    db.session.commit()

    return jsonify({"success": f"Supplier and order quantity updated for {item.name}!"})


IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"
IBM_API_URL = f"https://{IBM_REGION}.ml.cloud.ibm.com/ml/v1/deployments/{IBM_DEPLOYMENT_ID}/text/generation?version=2021-05-01"

def get_iam_token():
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": "urn:ibm:params:oauth:grant-type:apikey", "apikey": IBM_API_KEY}
    response = requests.post(IAM_TOKEN_URL, headers=headers, data=data)
    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        print("⚠️ Error fetching IAM token:", response.text)
        return None

def get_ai_prediction(inventory_data):
    iam_token = get_iam_token()
    if not iam_token:
        return {"error": "Failed to authenticate with IBM Cloud"}

    headers = {"Authorization": f"Bearer {iam_token}", "Content-Type": "application/json", "Accept": "application/json"}
    payload = {
        "parameters": {
            "prompt_variables": {
                "inventory_data": json.dumps(inventory_data)
            }
        }
    }

    try:
        response = requests.post(IBM_API_URL, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        generated_text = result.get("results", [{}])[0].get("generated_text", "No prediction available")
        return {"prediction": generated_text}
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Watsonx.ai Error: {e}")
        return {"error": f"Failed to get prediction: {e}"}

@app.route('/predict', methods=['POST'])
def predict():
    items = Inventory.query.all()
    inventory_data = [{"name": item.name, "stock": item.quantity, "sales_trend": "unknown"} for item in items]
    return jsonify(get_ai_prediction(inventory_data))

@app.route('/get_product', methods=['GET'])
def get_product():
    barcode = request.args.get('barcode')
    if barcode:
        item = Inventory.query.filter_by(barcode=barcode).first()
        if item:
            return jsonify({'success': True, 'name': item.name})
        else:
            return jsonify({'success': False, 'message': 'Product not found'})
    return jsonify({'success': False, 'message': 'Barcode not provided'})

@app.route('/sale', methods=['POST'])
def record_sale():
    data = request.get_json()
    item_id = data.get('item_id')
    quantity_sold = data.get('quantity')

    item = Inventory.query.get(item_id)
    if item and item.quantity >= quantity_sold:
        item.quantity -= quantity_sold
        sale = Sales(item_id=item_id, quantity_sold=quantity_sold)
        db.session.add(sale)
        db.session.commit()
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'message': 'Insufficient stock'})

@app.route('/sale_barcode', methods=['POST'])
def record_sale_barcode():
    data = request.get_json()
    barcode = data.get('barcode')
    amount = data.get('amount')

    item = Inventory.query.filter_by(barcode=barcode).first()
    if item and item.quantity >= amount:
        item.quantity -= amount
        sale = Sales(item_id=item.id, quantity_sold=amount)
        db.session.add(sale)
        db.session.commit()
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'message': 'Insufficient stock'})

@app.route('/sale_name', methods=['POST'])
def record_sale_name():
    data = request.get_json()
    name = data.get('name')
    amount = data.get('amount')

    item = Inventory.query.filter_by(name=name).first()
    if item and item.quantity >= amount:
        item.quantity -= amount
        sale = Sales(item_id=item.id, quantity_sold=amount)
        db.session.add(sale)
        db.session.commit()
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'message': 'Insufficient stock or product not found'})

# ==================== STORE USER-DEFINED STOCK WARNING LEVEL ====================
stock_settings = {"warning_threshold": 5}  # Default value

@app.route('/set_threshold', methods=['POST'])
def set_threshold():
    """Update the stock warning threshold based on user input"""
    data = request.get_json()
    new_threshold = data.get("threshold")

    if new_threshold and isinstance(new_threshold, int) and new_threshold > 0:
        stock_settings["warning_threshold"] = new_threshold
        return jsonify({"success": True, "message": f"Threshold set to {new_threshold}"})
    else:
        return jsonify({"success": False, "message": "Invalid threshold value"}), 400

def check_low_stock():
    """Check for low stock based on user-defined threshold"""
    low_stock_items = set()
    threshold = stock_settings["warning_threshold"]  # Use the stored threshold
    items = Inventory.query.all()
    for item in items:
        if item.quantity < threshold:
            low_stock_items.add(item.name)
    return low_stock_items


@app.route('/restock_pdf')
def restock_pdf():
    low_stock_items = check_low_stock()  # Get low-stock items
    buffer = BytesIO()  # Create a buffer to store the PDF

    p = canvas.Canvas(buffer, pagesize=letter)
    p.setFont("Helvetica", 12)
    p.drawString(100, 750, "Restock List")
    y = 730

    for item_name in low_stock_items:
        y -= 20
        p.drawString(100, y, item_name)

    p.save()
    buffer.seek(0)

    return send_file(buffer, as_attachment=True, download_name='restock_list.pdf', mimetype='application/pdf')

@app.route('/recommend_supplier', methods=['POST'])
def recommend_supplier():
    """Uses AI to recommend the best supplier for a product."""
    data = request.get_json()
    product_name = data.get("product_name")

    if not product_name:
        return jsonify({"error": "No product name provided"}), 400

    # Example supplier database (in real life, fetch from API)
    suppliers = {
        "Laptop": ["TechWorld", "GadgetPro"],
        "Milk": ["DairyBest", "FreshFarms"],
        "Headphones": ["AudioTech", "SoundWave"]
    }

    recommended_supplier = suppliers.get(product_name, ["GenericSupplier"])[0]

    return jsonify({"supplier": recommended_supplier})

@app.route('/auto_restock', methods=['POST'])
def auto_restock():
    """Automatically places an order when stock runs low."""
    low_stock_items = Inventory.query.filter(Inventory.quantity < Inventory.restock_threshold).all()

    if not low_stock_items:
        return jsonify({"message": "No items need restocking."})

    orders = []
    for item in low_stock_items:
        if not item.supplier or not item.order_quantity:  # Ensure supplier & order size are set
            continue

        orders.append({
            "product": item.name,
            "supplier": item.supplier,
            "order_quantity": item.order_quantity
        })

        # Simulated supplier API request (Replace with real API)
        print(f"🚀 Placing order: {item.name} ({item.order_quantity}) from {item.supplier}")

    return jsonify({"message": "Orders placed", "orders": orders})


def check_and_reorder():
    """Check inventory levels and place an order if needed."""
    low_stock_items = Inventory.query.filter(Inventory.quantity < Inventory.restock_threshold).all()
    orders = []

    for item in low_stock_items:
        order_data = {
            "item_name": item.name,
            "quantity": item.order_quantity,  # Order based on set quantity
            "supplier": item.supplier or "Default Supplier"
        }

        # ✅ Simulate API Call (Replace with real supplier API)
        response = requests.post("https://fake-supplier-api.com/order", json=order_data)
        
        if response.status_code == 200:
            orders.append(order_data)

    return orders  # Returns a list of successfully placed orders

@app.route('/sales_data')
def sales_data():
    sales = Sales.query.all()
    inventory = Inventory.query.all()

    sales_dict = {item.name: 0 for item in inventory}
    for sale in sales:
        item = Inventory.query.get(sale.item_id)
        if item:
            sales_dict[item.name] += sale.quantity_sold

    inventory_dict = {item.name: item.quantity for item in inventory}

    return jsonify({'sales_data': sales_dict, 'inventory_data': inventory_dict})


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)