from flask import Flask, request, redirect, render_template_string, session
import socket
import csv
from datetime import datetime
from pathlib import Path

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this to a secure random key

# Printer configuration
PRINTER_IP = '192.168.2.218'
PRINTER_PORT = 9100

# ESC/POS commands
CUT_PAPER = b'\x1D\x56\x00'  # Full cut command
LINE_FEED = b'\n'

def log_order_to_csv(order_data):
    # Create directory if it doesn't exist
    logs_dir = Path("order_logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Daily CSV filename (e.g., "orders_2023-08-15.csv")
    today = datetime.now().strftime("%Y-%m-%d")
    csv_file = logs_dir / f"orders_{today}.csv"
    
    # CSV headers
    fieldnames = ["timestamp", "seat", "item_name", "price"]
    
    # Write the order items to CSV
    file_exists = csv_file.exists()
    
    with open(csv_file, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        if not file_exists:
            writer.writeheader()
        
        for item in order_data['items']:
            writer.writerow({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "seat": order_data['seat'],
                "item_name": item['name'],
                "price": item['price'],
            })

    # Calculate daily total from all regular items (not totals)
    daily_total = 0
    if csv_file.exists():
        with open(csv_file, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Only sum rows that are actual items (not ORDER TOTAL or DAILY TOTAL)
                if row['item_name'] and row['item_name'] not in ['ORDER TOTAL', 'DAILY TOTAL']:
                    try:
                        daily_total += float(row['price'])
                    except ValueError:
                        pass

    # Append the order total
    with open(csv_file, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # Write the current order total
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            order_data['seat'],
            "ORDER TOTAL",
            order_data['total']
        ])
        # Write the daily total (only if we have items in this order)
        if order_data['items']:
            writer.writerow([
                "",
                "",
                "DAILY TOTAL",
                round(daily_total, 2)  # Round to 2 decimal places
            ])

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        .seat {
            transition: all 0.2s ease;
        }
        .seat.selected {
            transform: scale(1.1);
            box-shadow: 0 0 10px rgba(251, 191, 36, 0.7);
        }
        .category-btn.active {
            background-color: #f59e0b;
            color: white;
        }
        .order-item {
            animation: fadeIn 0.3s ease-in;
        }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        ::-webkit-scrollbar-thumb {
            background-color: rgba(59, 130, 246, 0.5);
            border-radius: 3px;
        }
        .flex-wrap {
            flex-wrap: wrap;
        }
        .gap-2 {
            gap: 0.5rem;
        }
        .mb-2 {
            margin-bottom: 0.5rem;
        }
        #seat-map {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 0.5rem;
            margin-bottom: 0.5rem;
        }
    </style>
    <script>
        // Global variables
        let currentRow = 'A';
        let currentSeat = null;
        let orderItems = [];
        let total = 0;

        // Seat functions
        function selectRow(row) {
            currentRow = row;
            generateSeatMap(row);
            
            document.querySelectorAll('.row-btn').forEach(btn => {
                btn.classList.remove('bg-blue-100', 'font-medium');
            });
            event.currentTarget.classList.add('bg-blue-100', 'font-medium');
        }

        function generateSeatMap(row) {
    const seatMap = document.getElementById('seat-map');
    seatMap.innerHTML = '';
    
    // Create 25 seats in a 5x5 grid
    for (let i = 1; i <= 25; i++) {
        const seat = document.createElement('button');
        seat.className = 'seat py-2 px-1 bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 text-xs sm:text-sm w-full';
        seat.textContent = i;
        seat.onclick = function() { selectSeat(this); };
        seat.dataset.seat = `${row}${i}`;
        seatMap.appendChild(seat);
    }
}

        function selectSeat(element) {
            if (currentSeat) {
                document.querySelector(`[data-seat="${currentSeat}"]`)?.classList.remove('selected');
            }
            currentSeat = element.dataset.seat;
            element.classList.add('selected');
            updateSelectedSeatDisplay();
        }

        function updateSelectedSeatDisplay() {
            const seatText = document.getElementById('selected-seat');
            const mobileDisplay = document.getElementById('mobile-seat-display').querySelector('span');
            
            if (currentSeat) {
                seatText.textContent = currentSeat;
                mobileDisplay.textContent = currentSeat;
            } else {
                seatText.textContent = 'Not selected';
                mobileDisplay.textContent = 'No seat';
            }
        }

        // Category functions
        function selectCategory(category) {
            document.querySelectorAll('.category-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            event.currentTarget.classList.add('active');
            
            document.querySelectorAll('.category-content').forEach(content => {
                content.classList.add('hidden');
            });
            document.getElementById(category).classList.remove('hidden');
        }

        // Order functions
        function addToOrder(name, price) {
    if (!currentSeat) {
        alert("Please select your seat first!");
        return;
    }
    
    // Check if item already exists in order
    const existingItem = orderItems.find(item => item.name === name && !item.customText);
    
    if (existingItem) {
        existingItem.quantity += 1;
    } else {
        orderItems.push({ 
            name, 
            price, 
            quantity: 1,  // Add quantity field
            customText: ""
        });
    }
    
    total += price;
    updateOrderDisplay();
}

        function updateOrderDisplay() {
    const orderItemsContainer = document.getElementById('order-items');
    
    if (orderItems.length === 0) {
        orderItemsContainer.innerHTML = '<p class="text-blue-500 text-center py-4 text-sm">No items added yet</p>';
        document.getElementById('order-total').textContent = '€0';
        return;
    }
    
    let itemsHTML = '';
    orderItems.forEach((item, index) => {
        // Display name with quantity in quotes if > 1
        const displayName = item.quantity > 1 
            ? `${item.name} "${item.quantity}"` 
            : item.name;
            
        // Add custom text if it exists
        const fullDisplayName = item.customText 
            ? `${displayName} [${item.customText}]` 
            : displayName;
            
        itemsHTML += `
            <div class="order-item flex justify-between items-center py-1.5 border-b border-blue-200 last:border-0">
                <div class="truncate pr-2">
                    <p class="text-blue-800 text-sm truncate">${fullDisplayName}</p>
                </div>
                <div class="flex items-center">
                    <span class="text-blue-700 font-medium mr-2 text-sm">€${(item.price * item.quantity).toFixed(2)}</span>
                    <div class="flex items-center border border-blue-200 rounded-md">
                        <button onclick="adjustQuantity(${index}, -1)" class="text-blue-400 hover:text-blue-600 px-2 py-1">
                            <i class="fas fa-minus text-xs"></i>
                        </button>
                        <span class="text-blue-800 text-sm mx-1">${item.quantity}</span>
                        <button onclick="adjustQuantity(${index}, 1)" class="text-blue-400 hover:text-blue-600 px-2 py-1">
                            <i class="fas fa-plus text-xs"></i>
                        </button>
                    </div>
                    <button onclick="editItemText(${index})" class="text-blue-400 hover:text-blue-600 text-sm ml-2">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button onclick="removeItem(${index})" class="text-red-400 hover:text-red-600 text-sm ml-2">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
            </div>
        `;
    });
    
    orderItemsContainer.innerHTML = itemsHTML;
    document.getElementById('order-total').textContent = `€${total.toFixed(2)}`;
}

function adjustQuantity(index, change) {
    const item = orderItems[index];
    const newQuantity = item.quantity + change;
    
    if (newQuantity < 1) {
        removeItem(index);
        return;
    }
    
    // Update total by the difference
    total += item.price * change;
    item.quantity = newQuantity;
    
    updateOrderDisplay();
}

function editItemText(index) {
    const item = orderItems[index];
    const customText = prompt("Add text to append to this item (it will appear in brackets):", item.customText || '');
    
    if (customText !== null) { // Only update if user didn't cancel
        item.customText = customText;
        updateOrderDisplay();
    }
}

    function editItemNotes(index) {
    const item = orderItems[index];
    const newNotes = prompt("Add or edit notes for this item:", item.notes || '');
    
    if (newNotes !== null) { // Only update if user didn't cancel
        item.notes = newNotes;
        updateOrderDisplay();
    }
}

        function removeItem(index) {
    const item = orderItems[index];
    total -= item.price * item.quantity;
    orderItems.splice(index, 1);
    updateOrderDisplay();
}

        function clearOrder() {
    if (orderItems.length === 0) return;
    
    if (confirm("Are you sure you want to clear your order?")) {
        orderItems = [];
        total = 0;
        updateOrderDisplay();
    }
}

        function submitOrder() {
    if (!currentSeat || orderItems.length === 0) return;
    
    const notes = document.getElementById('order-notes').value;
    const orderData = {
        seat: currentSeat,
        items: orderItems,
        total: total,
        notes: notes
    };
    
    // Send to server for printing
    fetch('/print', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(orderData)
    })
    .then(response => response.json())
    .then(data => {
        if (data.status === 'success') {
            // Clear the order on success
            orderItems = [];
            total = 0;
            document.getElementById('order-notes').value = '';
            updateOrderDisplay();
        } else {
            alert('Printing failed: ' + (data.message || 'Unknown error'));
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Printing failed: ' + error.message);
    });
}

        // Initialize
        window.onload = function() {
            generateSeatMap('A');
            document.querySelector('[data-row="A"]').classList.add('bg-blue-100', 'font-medium');
            renderMenu(); // This ensures the DOM is ready before rendering
        };
        
        function toggleSubOptions(itemId) {
    const subOptions = document.getElementById(itemId);
    subOptions.classList.toggle('hidden');
    
    // Close other open sub-options
    document.querySelectorAll('.sub-options').forEach(option => {
        if (option.id !== itemId && !option.classList.contains('hidden')) {
            option.classList.add('hidden');
        }
    });
}

// Close sub-options when clicking elsewhere
document.addEventListener('click', function(event) {
    if (!event.target.closest('.relative')) {
        document.querySelectorAll('.sub-options').forEach(option => {
            option.classList.add('hidden');
        });
    }
});

// Menu Data Structure
const menuData = {
    Snacks: [

        { name: "Chicken nuggets with potatoes", description: "", basePrice: 8},
        { name: "Homemade Pizza Margherita", description: "Cheese, Tomato sauce, Sliced tomato, Origano", basePrice: 9.5},
        { name: "Homemade Cured meat Pizza", description: "Cheese, Tomato sauce, Ham, Bacon, Peppers", basePrice: 11},
        { name: "Club sandwich", description: "Cheese, Ham/Turkey, Tomato, Lettuce, Mayo, Chips", basePrice: 7.5, options: [
            { label: "Ham", priceAdjustment: 0 },
            { label: "Turkey", priceAdjustment: 0 }
            ]},
        { name: "Chicken club sandwich", description: "Cheese, Chicken, Tomato, Cucumber, Sauce, Chips", basePrice: 8},
        { name: "Arabic Pita", description: "Cheese, Chicken, Lettuce, Tomato, Maustard Sauce", basePrice: 4.5},
        { name: "Tost", description: "Cheese, Ham/Turkey", basePrice: 3, options: [
            { label: "Ham", priceAdjustment: 0 },
            { label: "Turkey", priceAdjustment: 0 },
            { label: "Ham + Tomato", priceAdjustment: 0.5 },
            { label: "Turkey + Tomato", priceAdjustment: 0.5 }
            ]}
    ],
    Salads: [

        { name: "1 Salads Seasonal Fruits", description: "", basePrice: 7},
        { name: "2 Salads Pure", description: "Pineapple, Mango, Melon, Watermelon, Chia seeds", basePrice: 7.5},
        { name: "3 Salads Ceasar's", description: "", basePrice: 8},
        { name: "4 Salads Tuna salad", description: "Tuna, Lettuce, Cucumber, Pepper, Croutons, Corn, Dill", basePrice: 8},
        { name: "5 Salads Arugula", description: "Lettuce, Tomato, Cucumber, Locust bean nuts, Balsamic", basePrice: 7.5},
    ],
    Coffees: [
        
        { name: "Freddo Cappuccino", description: "", basePrice: 3.5, icon: "fas fa-cube", options: [
            { label: "None", priceAdjustment: 0 },
            { label: "One", priceAdjustment: 0 },
            { label: "Medium", priceAdjustment: 0 },
            { label: "Sweet", priceAdjustment: 0 }
            ]},
        { name: "Freddo Espresso", description: "", basePrice: 3, icon: "fas fa-cube", options: [
            { label: "None", priceAdjustment: 0 },
            { label: "One", priceAdjustment: 0 },
            { label: "Medium", priceAdjustment: 0 },
            { label: "Sweet", priceAdjustment: 0 }
            ]},
        { name: "Frappe", description: "", basePrice: 3, icon: "fas fa-cube", options: [
            { label: "None", priceAdjustment: 0 },
            { label: "One", priceAdjustment: 0 },
            { label: "Medium", priceAdjustment: 0 },
            { label: "Sweet", priceAdjustment: 0 }
            ]},
        { name: "Espresso", description: "", basePrice: 2, options: [
            { label: "None", priceAdjustment: 0 },
            { label: "One", priceAdjustment: 0 },
            { label: "Medium", priceAdjustment: 0 },
            { label: "Sweet", priceAdjustment: 0 }
            ]},
        { name: "Espresso Americano", description: "", basePrice: 2, options: [
            { label: "None", priceAdjustment: 0 },
            { label: "One", priceAdjustment: 0 },
            { label: "Medium", priceAdjustment: 0 },
            { label: "Sweet", priceAdjustment: 0 }
            ]},
        { name: "Cappuccino", description: "", basePrice: 3.5, options: [
            { label: "None", priceAdjustment: 0 },
            { label: "One", priceAdjustment: 0 },
            { label: "Medium", priceAdjustment: 0 },
            { label: "Sweet", priceAdjustment: 0 }
            ]},
        { name: "Greek Coffee Double", description: "", basePrice: 3, options: [
            { label: "None", priceAdjustment: 0 },
            { label: "One", priceAdjustment: 0 },
            { label: "Medium", priceAdjustment: 0 },
            { label: "Sweet", priceAdjustment: 0 }
            ]}
    ],
    Spirits: [

        { name: "Vodka", description: "Lemon & Cola", basePrice: 6.5, options: [
            { label: "Lemon", priceAdjustment: 0 },
            { label: "Cola", priceAdjustment: 0 }
            ]},
        { name: "Bacardi Cola", description: "", basePrice: 6.5},
        { name: "Gin Tonic", description: "", basePrice: 6.5},
        { name: "Whiskey", description: "", basePrice: 6.5},
        { name: "Wine small bottle", description: "", basePrice: 3.5, options: [
            { label: "White", priceAdjustment: 0 },
            { label: "Red", priceAdjustment: 0 },
            { label: "Sweet", priceAdjustment: 0 },
            { label: "Roze", priceAdjustment: 0 }
            ]}
    ],
    Cocktails: [

        { name: "Mojito", description: "", basePrice: 8},
        { name: "Daquiri", description: "", basePrice: 8},
        { name: "Caipirinha", description: "", basePrice: 8},
        { name: "Aperol", description: "", basePrice: 8}
    ],
    Baguets: [

        { name: "No1 Baguette - Ham/Turkey", description: "Cheese, ham/turkey, lettuce, tomato, mayo", basePrice: 4.5, options: [
            { label: "Ham", priceAdjustment: 0 },
            { label: "Turkey", priceAdjustment: 0 }
            ]},
        { name: "No2 Baguette - Chicken", description: "Cheese, chicken, tomato, cucumber, sauce", basePrice: 5},
        { name: "No3 Baguette - Feta", description: "Feta, tomato, olive paste, oregano, olive oil", basePrice: 4.5}
    ],
    Smoothies: [
        { name: "No1 Smoothies ", description: "Strawberry", basePrice: 4.5 },
        { name: "No2 Smoothies ", description: "Banana, Honey", basePrice: 4.5 },
        { name: "No3 Smoothies ", description: "Strawberry, Banana, Apple", basePrice: 5 },
        { name: "No4 Smoothies ", description: "Mango, Apple, Strawberry, Honey", basePrice: 5 },
        { name: "No5 Smoothies ", description: "Pineapple, Banana, Mango", basePrice: 5 }
    ],
    Slushies: [
        { name: "Strawberry", description: "", basePrice: 4 },
        { name: "Lemon", description: "", basePrice: 4 }
    ],
    Milkshakes: [
        { name: "Strawberry", description: "", basePrice: 4.5 },
        { name: "Vanilla", description: "", basePrice: 4.5 },
        { name: "Chocolate", description: "", basePrice: 4.5 }
    ],
    "Fresh Juices": [
        { name: "No1 Juices ", description: "Orange", basePrice: 3.5 },
        { name: "No2 Juices ", description: "Mixed Fruits", basePrice: 4.5 },
        { name: "No3 Juices ", description: "Apple, Carrot, Orange", basePrice: 4.5 },
        { name: "No4 Juices ", description: "Celery, Apple, Carrot, Orange", basePrice: 5 },
        { name: "No5 Juices ", description: "Beetroot, Apple, Ginger, Lemon", basePrice: 5 },
        { name: "No6 Juices", description: "Coconut, Carrot, Ginger, Apple, Lemon", basePrice: 5 }
    ],
    "Yogurt Bowls": [
        { name: "No1 Yogurt, Kiwi, Strawberry, Seeds", description: "", basePrice: 4.5 },
        { name: "No2 Yogurt, Chocolate, Banana, Honey", description: "", basePrice: 5 },
        { name: "No3 Yogurt, Honey, Walnuts", description: "", basePrice: 4.5 }
    ],
    "Beers": [
        { name: "Alfa", description: "", basePrice: 2 },
        { name: "Mythos", description: "", basePrice: 2 },
        { name: "Corona", description: "", basePrice: 4.5 },
        { name: "Amstel", description: "", basePrice: 2 },
        { name: "Heineken", description: "", basePrice: 2 }
    ],
    "Soft Drinks": [
        { name: "Coca Cola", description: "", basePrice: 2, options: [
            { label: "Classic", priceAdjustment: 0 },
            { label: "Zero", priceAdjustment: 0 }
            ]},
        { name: "Fanta", description: "", basePrice: 2, options: [
            { label: "Lemon", priceAdjustment: 0 },
            { label: "Orange", priceAdjustment: 0 }
            ]},
        { name: "Sprite", description: "", basePrice: 2 },
        { name: "Schweppes", description: "", basePrice: 2, options: [
            { label: "Pomegranate", priceAdjustment: 0 },
            { label: "Grapefruit", priceAdjustment: 0 },
            { label: "Lemon", priceAdjustment: 0 }
            ]},
        { name: "Green Tea", description: "", basePrice: 2 },
        { name: "Red bull", description: "", basePrice: 3.5 },
        { name: "Ice tea", description: "", basePrice: 2, options: [
            { label: "Lemon", priceAdjustment: 0 },
            { label: "Peach", priceAdjustment: 0 }
            ]},
    ]
};


// Menu Rendering Function
function renderMenu() {
    const menuContainer = document.getElementById('menu-items');
    menuContainer.innerHTML = '';

    for (const category in menuData) {
        const categoryDiv = document.createElement('div');
        categoryDiv.className = 'category-content hidden';
        categoryDiv.id = category;
        
        const itemsGrid = document.createElement('div');
        itemsGrid.className = 'grid grid-cols-1 gap-1';

        menuData[category].forEach(item => {
            const itemWrapper = document.createElement('div');
            itemWrapper.className = 'relative';
            
            // Main item button
            const itemButton = document.createElement('button');
            itemButton.className = 'flex justify-between items-center p-2 bg-blue-50 hover:bg-blue-100 rounded-lg transition text-left w-full';
            itemButton.innerHTML = `
    <div class="flex items-center truncate">
        ${item.icon ? `<i class="${item.icon} mr-2 text-blue-500"></i>` : ''}
        <div class="truncate">
            <h4 class="font-medium text-blue-800 text-sm truncate">${item.name}</h4>
            <p class="text-xs text-blue-600 truncate">${item.description || ''}</p>
        </div>
    </div>
    <span class="font-bold text-blue-700 text-sm ml-2">€${item.basePrice}</span>
`;
            
            // Add click handler for items with options
            if (item.options && item.options.length > 0) {
                itemButton.onclick = () => toggleSubOptions(`${category}-${item.name.toLowerCase().replace(' ', '-')}`);
            } else {
                itemButton.onclick = () => addToOrder(item.name, item.basePrice);
            }

            // Sub-options container
            if (item.options && item.options.length > 0) {
                const optionsDiv = document.createElement('div');
                optionsDiv.id = `${category}-${item.name.toLowerCase().replace(' ', '-')}`;
                optionsDiv.className = 'sub-options hidden bg-blue-50 rounded-b-lg p-2 border-t border-blue-100';
                
                item.options.forEach(option => {
                    const optionButton = document.createElement('button');
                    const totalPrice = item.basePrice + option.priceAdjustment;
                    optionButton.className = 'flex justify-between items-center p-1 px-2 hover:bg-blue-100 rounded text-left w-full text-sm';
                    optionButton.onclick = () => addToOrder(
                        `${item.name} (${option.label})`, 
                        totalPrice
                    );
                    optionButton.innerHTML = `
                        <span>${option.label}</span>
                        ${option.priceAdjustment > 0 ? 
                            `<span class="font-bold text-blue-700 text-xs">€${totalPrice.toFixed(2)}</span>` : ''
                        }
                    `;
                    optionsDiv.appendChild(optionButton);
                });

                itemWrapper.appendChild(optionsDiv);
            }

            itemWrapper.appendChild(itemButton);
            itemsGrid.appendChild(itemWrapper);
        });

        categoryDiv.appendChild(itemsGrid);
        menuContainer.appendChild(categoryDiv);
    }

    // Show first category by default
    document.querySelector('.category-btn').click();
}

// Price Update Function
function updatePrice(itemName, newPrice) {
    for (const category in menuData) {
        const item = menuData[category].find(i => i.name === itemName);
        if (item) {
            item.basePrice = newPrice;
            renderMenu();
            break;
        }
    }
}
    </script>
</head>
<body class="bg-gradient-to-b from-blue-50 to-blue-100 min-h-screen">
    <div class="container mx-auto px-2 py-4">
        <!-- Mobile Header -->
        <div class="flex items-center justify-between mb-4 px-2">
            <div class="flex items-center">
                <i class="fas fa-umbrella-beach text-2xl text-amber-500 mr-2"></i>
                <h1 class="text-xl font-bold text-blue-800">Beach Bar</h1>
            </div>
            <div id="mobile-seat-display" class="bg-blue-100 px-3 py-1 rounded-full text-sm font-medium text-blue-700">
                <i class="fas fa-chair mr-1"></i>
                <span>No seat</span>
            </div>
        </div>

        <div class="grid grid-cols-1 gap-4">
            <!-- Seat Selection -->
            <div class="bg-white rounded-xl shadow-md p-4 border border-blue-200">
                <h2 class="text-lg font-semibold text-blue-800 mb-3 flex items-center">
                    <i class="fas fa-map-marker-alt text-blue-500 mr-2"></i>
                    Select Your Seat
                </h2>
                
                <!-- Row Selection - Updated to 2 lines -->
<div class="mb-4">
    <!-- First Row of Letters -->
    <div class="flex flex-wrap gap-2 mb-2">
        <button onclick="selectRow('A')" class="row-btn py-2 px-4 bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition whitespace-nowrap" data-row="A">Row A</button>
        <button onclick="selectRow('B')" class="row-btn py-2 px-4 bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition whitespace-nowrap" data-row="B">Row B</button>
        <button onclick="selectRow('C')" class="row-btn py-2 px-4 bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition whitespace-nowrap" data-row="C">Row C</button>
    </div>
    
    <!-- Second Row of Letters -->
    <div class="flex flex-wrap gap-2">
        <button onclick="selectRow('D')" class="row-btn py-2 px-4 bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition whitespace-nowrap" data-row="D">Row D</button>
        <button onclick="selectRow('EXTRA')" class="row-btn py-2 px-4 bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition whitespace-nowrap" data-row="EXTRA">Row EXTRA</button>
    </div>
</div>

                <!-- Seat Map -->
                    <div class="mb-4">
                        <h3 class="text-xs font-medium text-blue-700 mb-2">Available Seats</h3>
                        <div id="seat-map" class="grid grid-cols-5 gap-2">
                        <!-- Seats will be generated here -->
                    </div>
                </div>

                <!-- Selected Seat Display -->
                <div id="selected-seat-display" class="bg-blue-50 p-3 rounded-lg border border-blue-200 flex items-center justify-between">
                    <div class="flex items-center">
                        <div class="mr-3 text-xl text-blue-600">
                            <i class="fas fa-chair"></i>
                        </div>
                        <div>
                            <p class="text-blue-500 text-xs">Your seat</p>
                            <p id="selected-seat" class="font-medium text-blue-800">Not selected</p>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Order Panel -->
<div class="bg-white rounded-xl shadow-md p-4 border border-blue-200">
    <h2 class="text-lg font-semibold text-blue-800 mb-3 flex items-center">
        <i class="fas fa-concierge-bell text-blue-500 mr-2"></i>
        Place Your Order
    </h2>
    
    <!-- Category Tabs -->
<!-- Category Tabs - Now in 4 rows -->
<div class="mb-4">
    <!-- First Row -->
    <div class="flex flex-wrap gap-2 mb-2">
        
        <button onclick="selectCategory('Coffees')" class="category-btn px-3 py-1.5 rounded-lg bg-blue-50 text-blue-800 font-medium whitespace-nowrap text-xs">
            <i class="fas fa-mug-saucer"></i> Coffees
        </button>
        <button onclick="selectCategory('Fresh Juices')" class="category-btn px-3 py-1.5 rounded-lg bg-blue-50 text-blue-800 font-medium whitespace-nowrap text-xs">
            <i class="fas fa-glass-whiskey"></i> Juices
        </button>
        <button onclick="selectCategory('Smoothies')" class="category-btn px-3 py-1.5 rounded-lg bg-blue-50 text-blue-800 font-medium whitespace-nowrap text-xs">
            <i class="fas fa-blender"></i> Smoothies
        </button>
        
    </div>
    
    <div class="flex flex-wrap gap-2 mb-2">
        
        <button onclick="selectCategory('Milkshakes')" class="category-btn px-3 py-1.5 rounded-lg bg-blue-50 text-blue-800 font-medium whitespace-nowrap text-xs">
            <i class="fas fa-ice-cream"></i> Milkshakes
        </button>
        <button onclick="selectCategory('Slushies')" class="category-btn px-3 py-1.5 rounded-lg bg-blue-50 text-blue-800 font-medium whitespace-nowrap text-xs">
            <i class="fas fa-snowflake"></i> Slushies
        </button>
        <button onclick="selectCategory('Soft Drinks')" class="category-btn px-3 py-1.5 rounded-lg bg-blue-50 text-blue-800 font-medium whitespace-nowrap text-xs">
            <i class="fas fa-glass-whiskey"></i> Soft Drinks
        </button>
        
    </div>
    
    <!-- Second Row -->
    <div class="flex flex-wrap gap-2 mb-2">
        
        <button onclick="selectCategory('Beers')" class="category-btn px-3 py-1.5 rounded-lg bg-blue-50 text-blue-800 font-medium whitespace-nowrap text-xs">
            <i class="fas fa-beer-mug-empty"></i> Beers
        </button>
        <button onclick="selectCategory('Spirits')" class="category-btn px-3 py-1.5 rounded-lg bg-blue-50 text-blue-800 font-medium whitespace-nowrap text-xs">
            <i class="fas fa-wine-glass"></i> Spirits
        </button>
        <button onclick="selectCategory('Snacks')" class="category-btn active px-3 py-1.5 rounded-lg bg-blue-50 text-blue-800 font-medium whitespace-nowrap text-xs">
            <i class="fas fa-pizza-slice"></i> Snacks
        </button>
        
    </div>
        <div class="flex flex-wrap gap-2 mb-2">
        
        <button onclick="selectCategory('Baguets')" class="category-btn px-3 py-1.5 rounded-lg bg-blue-50 text-blue-800 font-medium whitespace-nowrap text-xs">
            <i class="fas fa-bread-slice"></i> Baguets
        </button>
        <button onclick="selectCategory('Salads')" class="category-btn px-3 py-1.5 rounded-lg bg-blue-50 text-blue-800 font-medium whitespace-nowrap text-xs">
            <i class="fas fa-bowl-food"></i> Salads
        </button>
        <button onclick="selectCategory('Yogurt Bowls')" class="category-btn px-3 py-1.5 rounded-lg bg-blue-50 text-blue-800 font-medium whitespace-nowrap text-xs">
            <i class="fas fa-bowl-food"></i> Yogurt
        </button>
        
    </div>
    
    <div class="flex flex-wrap gap-2">
        
        <button onclick="selectCategory('Cocktails')" class="category-btn px-3 py-1.5 rounded-lg bg-blue-50 text-blue-800 font-medium whitespace-nowrap text-xs">
            <i class="fas fa-martini-glass"></i> Cocktails
        </button>
        
    </div>
    
</div>

    <!-- Menu Items -->
    <div id="menu-items" class="mb-4 max-h-60 overflow-y-auto pr-1">
        
    </div>

    <!-- Current Order -->
    <div class="mb-4">
        <div class="flex justify-between items-center mb-2">
            <h3 class="text-xs font-medium text-blue-700 flex items-center">
                <i class="fas fa-receipt mr-1"></i> Your Order
            </h3>
            <button onclick="clearOrder()" class="text-xs text-red-500 hover:text-red-700 flex items-center">
                <i class="fas fa-trash-alt mr-1 text-xs"></i> Clear
            </button>
        </div>
        <div id="order-items" class="bg-blue-50 rounded-lg p-2 min-h-16 max-h-32 overflow-y-auto">
            <p class="text-blue-500 text-center py-4 text-sm">No items added yet</p>
        </div>
        <div class="mt-2 flex justify-between items-center bg-blue-100 px-3 py-2 rounded-lg">
            <span class="font-medium text-blue-800 text-sm flex items-center">
                <i class="fas fa-coins mr-1"></i> Total:
            </span>
            <span id="order-total" class="font-bold text-blue-700 text-sm">$0</span>
        </div>
    </div>

    <!-- Order Notes -->
    <div class="mb-4">
        <label for="order-notes" class="block text-xs font-medium text-blue-700 mb-1 flex items-center">
            <i class="fas fa-sticky-note mr-1"></i> Special Instructions
        </label>
        <textarea id="order-notes" rows="2" class="w-full px-3 py-2 border border-blue-200 rounded-lg focus:ring-1 focus:ring-blue-300 focus:border-blue-300 text-sm" placeholder="Allergies? Modifications?"></textarea>
    </div>

    <!-- Submit Button -->
    <button id="submit-order" onclick="submitOrder()" class="w-full py-3 bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white font-medium rounded-lg shadow-md transition disabled:opacity-50 disabled:cursor-not-allowed text-sm">
        <i class="fas fa-paper-plane mr-1"></i> Send Order
    </button>
</div>
        </div>
    </div>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/print', methods=['POST'])
def print_receipt():
    try:
        order_data = request.json
        seat = order_data['seat']
        
        # Log to CSV
        log_order_to_csv(order_data)
        
        # ESC/POS commands
        ESC = b'\x1B'
        RESET = ESC + b'!\x00'  # Reset formatting
        BOLD_LARGE = ESC + b'!\x38'  # Double height + bold
        
        # Calculate spacing (assuming 32 character width)
        pure_text = "PURE"
        spacing = 32 - len(pure_text) - len(seat)  # Space between texts
        
        # Build receipt content
        receipt_lines = [
            # Left "PURE" + right-aligned seat number (bold and large)
            pure_text.encode('utf-8') + b' ' * spacing + BOLD_LARGE + seat.encode('utf-8') + RESET,
            b"\n" + ("="*32).encode('utf-8'),  # Divider line
            f"\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}".encode('utf-8'),
            b"\n\nITEMS:\n------"
        ]
        
        # Add items
        for item in order_data['items']:
            receipt_lines.append(f"\n{item['name']} - ${item['price']}".encode('utf-8'))
        
        # Add footer
        receipt_lines.extend([
            b"\n\n" + ("-"*32).encode('utf-8'),
            f"\nTOTAL: ${order_data['total']}".encode('utf-8'),
            f"\n\nNotes: {order_data.get('notes', 'None')}".encode('utf-8'),
            b"\n" + ("="*32).encode('utf-8'),
            b"\nThank you!"
            b"\n"
        ])
        
        # Combine all parts
        data = b"".join(receipt_lines) + (LINE_FEED * 3) + CUT_PAPER
        
        # Send to printer
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((PRINTER_IP, PRINTER_PORT))
            s.sendall(data)
            
        return {'status': 'success'}
        
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)