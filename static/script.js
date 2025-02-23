// ==================== MULTIPLE ITEM ADDING (add_item.html) ====================

function addNewRow() {
    let table = document.getElementById("itemsTable").getElementsByTagName('tbody')[0];
    let newRow = table.insertRow();
    newRow.innerHTML = `
        <td><input type="text" name="barcode[]" placeholder="Scan Barcode (Optional)" oninput="fetchProductDetails(this)"></td>
        <td><input type="text" name="name[]" placeholder="Item Name" required></td>
        <td><input type="number" name="quantity[]" placeholder="Quantity" required></td>
        <td><input type="date" name="expiry_date[]"></td>
        <td><button type="button" class="btn-delete" onclick="removeRow(this)">🗑</button></td>
    `;
}

function removeRow(button) {
    let row = button.closest("tr");
    row.remove();
}

function fetchProductDetails(inputElement) {
    let barcode = inputElement.value.trim();
    let row = inputElement.closest("tr");
    let nameInput = row.querySelector("input[name='name[]']");

    if (barcode.length >= 8) {
        fetch(`/get_product?barcode=${barcode}`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    nameInput.value = data.name;
                } else {
                    alert("⚠ Product not found. Please enter manually.");
                    nameInput.value = "";
                }
            })
            .catch(error => console.error("Error fetching product details:", error));
    }
}

// ==================== DELETE CONFIRMATION (index.html) ====================

let itemIdToDelete = null;

function confirmDelete(itemId) {
    itemIdToDelete = itemId;
    document.getElementById("delete-popup").style.display = "block";
}

function closeConfirmation() {
    document.getElementById("delete-popup").style.display = "none";
}

document.addEventListener("DOMContentLoaded", function () {
    let confirmButton = document.getElementById("confirm-delete");
    if (confirmButton) {
        confirmButton.addEventListener("click", function () {
            if (itemIdToDelete) {
                window.location.href = `/delete/${itemIdToDelete}`;
            }
        });
    }
});

// ==================== AI DEMAND FORECAST (index.html) ====================

function getPrediction() {
    document.getElementById('ai_prediction').innerText = "Loading...";
    fetch('/get_items?' + new Date().getTime())
        .then(response => response.json())
        .then(items => {
            if (items.length === 0) {
                document.getElementById('ai_prediction').innerText = "No items in inventory.";
                return;
            }

            let inventoryData = items.map(item => ({
                name: item.name,
                stock: item.quantity,
                sales_trend: "unknown"
            }));

            return fetch('/predict', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ inventory_data: inventoryData })
            });
        })
        .then(response => response.json())
        .then(data => {
            if (data.prediction) {
                document.getElementById('ai_prediction').innerText = data.prediction;
            } else if (data.error) {
                document.getElementById('ai_prediction').innerText = "Error: " + data.error;
            } else {
                document.getElementById('ai_prediction').innerText = "Error fetching prediction.";
            }

        })
        .catch(error => {
            console.error('Error:', error);
            document.getElementById('ai_prediction').innerText = "An unexpected error occurred.";
        });
}

// ==================== Record General Sale ====================
function recordGeneralSale() {
    let barcode = document.getElementById("generalBarcode").value;
    let name = document.getElementById("generalName").value;
    let amount = parseInt(document.getElementById("saleAmount").value);

    if (isNaN(amount) || amount < 1) {
        alert("Please enter a valid amount.");
        return;
    }

    if (barcode) {
        fetch('/sale_barcode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ barcode: barcode, amount: amount })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert("Sale recorded successfully!");
                window.location.reload();
            } else {
                alert("Error recording sale: " + data.message);
            }
        })
        .catch(error => console.error('Error:', error));
    } else if (name) {
        fetch('/sale_name', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, amount: amount })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert("Sale recorded successfully!");
                window.location.reload();
            } else {
                alert("Error recording sale: " + data.message);
            }
        })
        .catch(error => console.error('Error:', error));
    } else {
        alert("Please enter a barcode or product name.");
    }
}
// ==================== STOCK WARNING SYSTEM ====================

// Save and apply user-defined stock warning threshold
function setStockThreshold() {
    let threshold = document.getElementById("stockThreshold").value;
    if (!threshold || threshold < 1) {
        alert("⚠ Please enter a valid stock warning level.");
        return;
    }

    fetch('/set_threshold', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ threshold: parseInt(threshold) })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            localStorage.setItem("stockThreshold", threshold);
            alert("✅ Stock warning level saved!");
            applyStockWarnings();
        } else {
            alert("⚠ Error: " + data.message);
        }
    })
    .catch(error => console.error("Error:", error));
}

// Apply stock warnings dynamically
function applyStockWarnings() {
    let threshold = localStorage.getItem("stockThreshold") || 5; // Default is 5
    let warningElements = document.querySelectorAll(".low-stock-warning");

    warningElements.forEach(el => {
        let quantity = parseInt(el.getAttribute("data-quantity"));
        if (quantity <= threshold) {
            el.style.display = "inline"; // Show warning if stock is low
        } else {
            el.style.display = "none"; // Hide warning if stock is okay
        }
    });
}

document.addEventListener("DOMContentLoaded", function () {
    fetch('/sales_data')
        .then(response => response.json())
        .then(data => {
            createSalesChart(data.sales_data);
            createInventoryChart(data.inventory_data);
        });

    function createSalesChart(salesData) {
        let ctx = document.getElementById('salesChart').getContext('2d');
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: Object.keys(salesData),
                datasets: [{
                    label: 'Units Sold',
                    data: Object.values(salesData),
                    backgroundColor: 'rgba(54, 162, 235, 0.6)',
                    borderColor: 'rgba(54, 162, 235, 1)',
                    borderWidth: 1
                }]
            },
            options: { responsive: true }
        });
    }

    function createInventoryChart(inventoryData) {
        let ctx = document.getElementById('inventoryChart').getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: Object.keys(inventoryData),
                datasets: [{
                    label: 'Stock Levels',
                    data: Object.values(inventoryData),
                    backgroundColor: 'rgba(255, 99, 132, 0.6)',
                    borderColor: 'rgba(255, 99, 132, 1)',
                    borderWidth: 1
                }]
            },
            options: { responsive: true }
        });
    }
});

function updateSupplierForItem(itemId) {
    let supplier = document.getElementById(`supplier_${itemId}`).value;
    let orderQuantity = document.getElementById(`orderQuantity_${itemId}`).value;

    if (!supplier || !orderQuantity) {
        alert("⚠ Please enter both supplier and order quantity!");
        return;
    }

    fetch(`/update_supplier/${itemId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ supplier: supplier, order_quantity: orderQuantity })
    })
    .then(response => response.json())
    .then(data => {
        alert(data.success || data.error);
    })
    .catch(error => console.error("Error updating supplier details:", error));
}

// Run when page loads
document.addEventListener("DOMContentLoaded", function () {
    applyStockWarnings();

    fetch('/get_low_stock')
    .then(response => response.json())
    .then(data => {
        createRestockChart(data.low_stock);
    })
    .catch(error => console.error("Error fetching restock data:", error));

});

function createRestockChart(lowStockData) {
    let ctx = document.getElementById('predictionChart').getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: Object.keys(lowStockData),
            datasets: [{
                label: 'Stock Left',
                data: Object.values(lowStockData),
                backgroundColor: 'rgba(255, 206, 86, 0.6)',
                borderColor: 'rgba(255, 206, 86, 1)',
                borderWidth: 1
            }]
        },
        options: { responsive: true }
    });
}

