from flask import Flask, request, redirect, render_template_string, session
import socket
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this to a secure random key

# Printer configuration
PRINTER_IP = '192.168.2.218'
PRINTER_PORT = 9100

# ESC/POS commands
CUT_PAPER = b'\x1D\x56\x00'  # Full cut command
LINE_FEED = b'\n'

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
            
            for (let i = 1; i <= 12; i++) {
                const seat = document.createElement('button');
                seat.className = 'seat py-2 px-1 bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 text-xs sm:text-sm';
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
            
            orderItems.push({ name, price });
            total += price;
            updateOrderDisplay();
        }

        function updateOrderDisplay() {
            const orderItemsContainer = document.getElementById('order-items');
            
            if (orderItems.length === 0) {
                orderItemsContainer.innerHTML = '<p class="text-blue-500 text-center py-4 text-sm">No items added yet</p>';
                document.getElementById('order-total').textContent = '$0';
                return;
            }
            
            let itemsHTML = '';
            orderItems.forEach((item, index) => {
                itemsHTML += `
                    <div class="order-item flex justify-between items-center py-1.5 border-b border-blue-200 last:border-0">
                        <div class="truncate pr-2">
                            <p class="text-blue-800 text-sm truncate">${item.name}</p>
                        </div>
                        <div class="flex items-center">
                            <span class="text-blue-700 font-medium mr-2 text-sm">$${item.price}</span>
                            <button onclick="removeItem(${index})" class="text-red-400 hover:text-red-600 text-xs">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    </div>
                `;
            });
            
            orderItemsContainer.innerHTML = itemsHTML;
            document.getElementById('order-total').textContent = `$${total}`;
        }

        function removeItem(index) {
            total -= orderItems[index].price;
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
                notes: notes,
                timestamp: new Date().toLocaleString()
            };
            
            console.log('Order submitted:', orderData);
            showConfirmation(orderData);
        }

        function showConfirmation(orderData) {
            const modal = document.getElementById('confirmation-modal');
            const summary = document.getElementById('order-summary');
            
            let summaryText = `Seat ${orderData.seat}: `;
            orderData.items.forEach(item => {
                summaryText += `${item.name} ($${item.price}), `;
            });
            summaryText = summaryText.slice(0, -2) + ` | Total: $${orderData.total}`;
            
            summary.textContent = summaryText;
            modal.classList.remove('hidden');
        }

        function closeModal() {
            document.getElementById('confirmation-modal').classList.add('hidden');
            orderItems = [];
            total = 0;
            document.getElementById('order-notes').value = '';
            updateOrderDisplay();
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
    drinks: [
        {
            name: 'Tropical Punch',
            description: 'Rum, pineapple, orange, grenadine',
            basePrice: 8,
            options: [
                { label: 'With Sugar', priceAdjustment: 0 },
                { label: 'No Sugar', priceAdjustment: 0 },
                { label: 'Extra Rum', priceAdjustment: 2 }
            ]
        },
        {
            name: 'Cappuccino',
            description: 'Espresso with steamed milk',
            basePrice: 5,
            options: [
                { label: 'With Sugar', priceAdjustment: 0 },
                { label: 'No Sugar', priceAdjustment: 0 },
                { label: 'Oat Milk', priceAdjustment: 1 }
            ]
        }
    ],
    food: [
        {
            name: 'Fish Tacos',
            description: 'Grilled fish, slaw, lime crema',
            basePrice: 12,
            options: [
                { label: 'Spicy', priceAdjustment: 0 },
                { label: 'Mild', priceAdjustment: 0 }
            ]
        }
    ],
    snacks: [
        {
            name: 'Nachos',
            description: 'With cheese, guacamole, salsa',
            basePrice: 8,
            options: [] // No options
        }
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
                <div class="truncate">
                    <h4 class="font-medium text-blue-800 text-sm truncate">${item.name}</h4>
                    <p class="text-xs text-blue-600 truncate">${item.description}</p>
                </div>
                <span class="font-bold text-blue-700 text-sm ml-2">$${item.basePrice}</span>
            `;
            
            // Add click handler for items with options
            if (item.options.length > 0) {
                itemButton.onclick = () => toggleSubOptions(`${category}-${item.name.toLowerCase().replace(' ', '-')}`);
            } else {
                itemButton.onclick = () => addToOrder(item.name, item.basePrice);
            }

            // Sub-options container
            if (item.options.length > 0) {
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
                            `<span class="font-bold text-blue-700 text-xs">$${totalPrice.toFixed(2)}</span>` : ''
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

// Initialize the menu
renderMenu();

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
                
                <!-- Row Selection -->
                <div class="mb-4">
                    <h3 class="text-xs font-medium text-blue-700 mb-2">Choose Row</h3>
                    <div class="flex space-x-2 overflow-x-auto pb-2">
                        <button onclick="selectRow('A')" class="row-btn py-2 px-4 bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition whitespace-nowrap" data-row="A">Row A</button>
                        <button onclick="selectRow('B')" class="row-btn py-2 px-4 bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition whitespace-nowrap" data-row="B">Row B</button>
                        <button onclick="selectRow('C')" class="row-btn py-2 px-4 bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition whitespace-nowrap" data-row="C">Row C</button>
                        <button onclick="selectRow('D')" class="row-btn py-2 px-4 bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition whitespace-nowrap" data-row="D">Row D</button>
                        <button onclick="selectRow('E')" class="row-btn py-2 px-4 bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition whitespace-nowrap" data-row="E">Row E</button>
                    </div>
                </div>

                <!-- Seat Map -->
                <div class="mb-4">
                    <h3 class="text-xs font-medium text-blue-700 mb-2">Available Seats</h3>
                    <div id="seat-map" class="grid grid-cols-6 gap-1">
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
    <div class="mb-4">
        <div class="flex space-x-2 overflow-x-auto pb-2">
            <button onclick="selectCategory('drinks')" class="category-btn active px-3 py-1.5 rounded-lg bg-blue-50 text-blue-800 font-medium whitespace-nowrap text-xs">
                <i class="fas fa-glass-whiskey mr-1"></i> Drinks
            </button>
            <button onclick="selectCategory('food')" class="category-btn px-3 py-1.5 rounded-lg bg-blue-50 text-blue-800 font-medium whitespace-nowrap text-xs">
                <i class="fas fa-utensils mr-1"></i> Food
            </button>
            <button onclick="selectCategory('snacks')" class="category-btn px-3 py-1.5 rounded-lg bg-blue-50 text-blue-800 font-medium whitespace-nowrap text-xs">
                <i class="fas fa-ice-cream mr-1"></i> Snacks
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

        <!-- Order Confirmation Modal -->
        <div id="confirmation-modal" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 hidden px-2">
            <div class="bg-white rounded-xl p-5 w-full max-w-sm mx-2">
                <div class="text-center mb-4">
                    <div class="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-green-100">
                        <i class="fas fa-check text-green-600 text-xl"></i>
                    </div>
                </div>
                <h3 class="text-lg font-medium text-gray-900 text-center mb-2">Order Received!</h3>
                <p id="confirmation-message" class="text-gray-500 text-center mb-4 text-sm">Your order has been sent to the bar.</p>
                <div class="bg-green-50 p-3 rounded-lg mb-4">
                    <p class="text-green-800 text-center font-medium text-sm" id="order-summary"></p>
                </div>
                <button onclick="closeModal()" class="w-full py-2 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700">
                    Close
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
    # This would handle the actual printing in your implementation
    receipt_data = request.json
    
    try:
        # Format receipt content for printer
        receipt_lines = [
            ""
            "BEACH BAR ORDER",
            "================",
            f"Seat: {receipt_data['seat']}",
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "ITEMS:",
            "------"
        ]
        
        for item in receipt_data['items']:
            receipt_lines.append(f"{item['name']} - ${item['price']}")
        
        receipt_lines += [
            "",
            "----------------",
            f"TOTAL: ${receipt_data['total']}",
            "",
            f"Notes: {receipt_data.get('notes', 'None')}",
            "================",
            "Thank you!"
            ""
        ]
        
        receipt_content = "\n".join(receipt_lines)
        data = receipt_content.encode('ascii') + (LINE_FEED * 3) + CUT_PAPER
        
        # Connect to printer and send data
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((PRINTER_IP, PRINTER_PORT))
            s.sendall(data)
            
        return {'status': 'success'}
        
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)