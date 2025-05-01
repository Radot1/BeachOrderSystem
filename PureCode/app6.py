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

# Menu items matching your HTML
MENU_ITEMS = {
    "drinks": {
        "Tropical Punch": 8,
        "Coconut Mojito": 10,
        "Sunset Margarita": 9,
        "Local Beer": 5,
        "Soft Drink": 3,
        "Bottled Water": 2
    },
    "food": {
        "Fish Tacos": 12,
        "Beach Burger": 11,
        "Grilled Shrimp": 14,
        "Caesar Salad": 9
    },
    "snacks": {
        "Nachos": 8,
        "Coconut Shrimp": 10,
        "Chicken Wings": 9,
        "French Fries": 5
    }
}

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
        /* Custom scrollbar for mobile */
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        ::-webkit-scrollbar-thumb {
            background-color: rgba(59, 130, 246, 0.5);
            border-radius: 3px;
        }
    </style>
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
                
                <!-- Row Selection - Horizontal Scroll on Mobile -->
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

                <!-- Seat Map - Smaller on Mobile -->
                <div class="mb-4">
                    <h3 class="text-xs font-medium text-blue-700 mb-2">Available Seats</h3>
                    <div id="seat-map" class="grid grid-cols-6 gap-1">
                        <!-- Seats will be generated here by JavaScript -->
                    </div>
                </div>

                <!-- Selected Seat Display - Simplified for Mobile -->
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
                
                <!-- Category Tabs - Horizontal Scroll on Mobile -->
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

                <!-- Menu Items - Scrollable on Mobile -->
                <div id="menu-items" class="mb-4 max-h-60 overflow-y-auto pr-1">
                    <!-- Drinks Category (default visible) -->
                    <div id="drinks" class="category-content">
                        <div class="grid grid-cols-1 gap-1">
                            <button onclick="addToOrder('Tropical Punch', 8)" class="flex justify-between items-center p-2 bg-blue-50 hover:bg-blue-100 rounded-lg transition text-left w-full">
                                <div class="truncate">
                                    <h4 class="font-medium text-blue-800 text-sm truncate">Tropical Punch</h4>
                                    <p class="text-xs text-blue-600 truncate">Rum, pineapple, orange, grenadine</p>
                                </div>
                                <span class="font-bold text-blue-700 text-sm ml-2">$8</span>
                            </button>
                            <button onclick="addToOrder('Coconut Mojito', 10)" class="flex justify-between items-center p-2 bg-blue-50 hover:bg-blue-100 rounded-lg transition text-left w-full">
                                <div class="truncate">
                                    <h4 class="font-medium text-blue-800 text-sm truncate">Coconut Mojito</h4>
                                    <p class="text-xs text-blue-600 truncate">White rum, coconut water, lime, mint</p>
                                </div>
                                <span class="font-bold text-blue-700 text-sm ml-2">$10</span>
                            </button>
                            <button onclick="addToOrder('Sunset Margarita', 9)" class="flex justify-between items-center p-2 bg-blue-50 hover:bg-blue-100 rounded-lg transition text-left w-full">
                                <div class="truncate">
                                    <h4 class="font-medium text-blue-800 text-sm truncate">Sunset Margarita</h4>
                                    <p class="text-xs text-blue-600 truncate">Tequila, triple sec, lime, orange juice</p>
                                </div>
                                <span class="font-bold text-blue-700 text-sm ml-2">$9</span>
                            </button>
                            <button onclick="addToOrder('Local Beer', 5)" class="flex justify-between items-center p-2 bg-blue-50 hover:bg-blue-100 rounded-lg transition text-left w-full">
                                <div class="truncate">
                                    <h4 class="font-medium text-blue-800 text-sm truncate">Local Beer</h4>
                                    <p class="text-xs text-blue-600 truncate">500ml bottle</p>
                                </div>
                                <span class="font-bold text-blue-700 text-sm ml-2">$5</span>
                            </button>
                            <button onclick="addToOrder('Soft Drink', 3)" class="flex justify-between items-center p-2 bg-blue-50 hover:bg-blue-100 rounded-lg transition text-left w-full">
                                <div class="truncate">
                                    <h4 class="font-medium text-blue-800 text-sm truncate">Soft Drink</h4>
                                    <p class="text-xs text-blue-600 truncate">Cola, lemonade, or orange</p>
                                </div>
                                <span class="font-bold text-blue-700 text-sm ml-2">$3</span>
                            </button>
                            <button onclick="addToOrder('Bottled Water', 2)" class="flex justify-between items-center p-2 bg-blue-50 hover:bg-blue-100 rounded-lg transition text-left w-full">
                                <div class="truncate">
                                    <h4 class="font-medium text-blue-800 text-sm truncate">Bottled Water</h4>
                                    <p class="text-xs text-blue-600 truncate">500ml mineral water</p>
                                </div>
                                <span class="font-bold text-blue-700 text-sm ml-2">$2</span>
                            </button>
                        </div>
                    </div>

                    <!-- Food Category (hidden by default) -->
                    <div id="food" class="category-content hidden">
                        <div class="grid grid-cols-1 gap-1">
                            <button onclick="addToOrder('Fish Tacos', 12)" class="flex justify-between items-center p-2 bg-blue-50 hover:bg-blue-100 rounded-lg transition text-left w-full">
                                <div class="truncate">
                                    <h4 class="font-medium text-blue-800 text-sm truncate">Fish Tacos</h4>
                                    <p class="text-xs text-blue-600 truncate">Grilled fish, slaw, lime crema</p>
                                </div>
                                <span class="font-bold text-blue-700 text-sm ml-2">$12</span>
                            </button>
                            <button onclick="addToOrder('Beach Burger', 11)" class="flex justify-between items-center p-2 bg-blue-50 hover:bg-blue-100 rounded-lg transition text-left w-full">
                                <div class="truncate">
                                    <h4 class="font-medium text-blue-800 text-sm truncate">Beach Burger</h4>
                                    <p class="text-xs text-blue-600 truncate">Beef patty, cheese, lettuce, special sauce</p>
                                </div>
                                <span class="font-bold text-blue-700 text-sm ml-2">$11</span>
                            </button>
                            <button onclick="addToOrder('Grilled Shrimp', 14)" class="flex justify-between items-center p-2 bg-blue-50 hover:bg-blue-100 rounded-lg transition text-left w-full">
                                <div class="truncate">
                                    <h4 class="font-medium text-blue-800 text-sm truncate">Grilled Shrimp</h4>
                                    <p class="text-xs text-blue-600 truncate">With garlic butter and lime</p>
                                </div>
                                <span class="font-bold text-blue-700 text-sm ml-2">$14</span>
                            </button>
                            <button onclick="addToOrder('Caesar Salad', 9)" class="flex justify-between items-center p-2 bg-blue-50 hover:bg-blue-100 rounded-lg transition text-left w-full">
                                <div class="truncate">
                                    <h4 class="font-medium text-blue-800 text-sm truncate">Caesar Salad</h4>
                                    <p class="text-xs text-blue-600 truncate">Romaine, croutons, parmesan</p>
                                </div>
                                <span class="font-bold text-blue-700 text-sm ml-2">$9</span>
                            </button>
                        </div>
                    </div>

                    <!-- Snacks Category (hidden by default) -->
                    <div id="snacks" class="category-content hidden">
                        <div class="grid grid-cols-1 gap-1">
                            <button onclick="addToOrder('Nachos', 8)" class="flex justify-between items-center p-2 bg-blue-50 hover:bg-blue-100 rounded-lg transition text-left w-full">
                                <div class="truncate">
                                    <h4 class="font-medium text-blue-800 text-sm truncate">Nachos</h4>
                                    <p class="text-xs text-blue-600 truncate">With cheese, guacamole, salsa</p>
                                </div>
                                <span class="font-bold text-blue-700 text-sm ml-2">$8</span>
                            </button>
                            <button onclick="addToOrder('Coconut Shrimp', 10)" class="flex justify-between items-center p-2 bg-blue-50 hover:bg-blue-100 rounded-lg transition text-left w-full">
                                <div class="truncate">
                                    <h4 class="font-medium text-blue-800 text-sm truncate">Coconut Shrimp</h4>
                                    <p class="text-xs text-blue-600 truncate">With sweet chili sauce</p>
                                </div>
                                <span class="font-bold text-blue-700 text-sm ml-2">$10</span>
                            </button>
                            <button onclick="addToOrder('Chicken Wings', 9)" class="flex justify-between items-center p-2 bg-blue-50 hover:bg-blue-100 rounded-lg transition text-left w-full">
                                <div class="truncate">
                                    <h4 class="font-medium text-blue-800 text-sm truncate">Chicken Wings</h4>
                                    <p class="text-xs text-blue-600 truncate">BBQ or Buffalo style</p>
                                </div>
                                <span class="font-bold text-blue-700 text-sm ml-2">$9</span>
                            </button>
                            <button onclick="addToOrder('French Fries', 5)" class="flex justify-between items-center p-2 bg-blue-50 hover:bg-blue-100 rounded-lg transition text-left w-full">
                                <div class="truncate">
                                    <h4 class="font-medium text-blue-800 text-sm truncate">French Fries</h4>
                                    <p class="text-xs text-blue-600 truncate">With sea salt</p>
                                </div>
                                <span class="font-bold text-blue-700 text-sm ml-2">$5</span>
                            </button>
                        </div>
                    </div>
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

    <script>
        // Global variables
let currentRow = 'A'; // Set default row to A
let currentSeat = null; // Track selected seat
let orderItems = [];
let total = 0;

// Initialize the page
document.addEventListener('DOMContentLoaded', function() {
    // Generate seat map for row A by default
    generateSeatMap(currentRow);
    // Highlight the default row button
    document.querySelector('[data-row="A"]').classList.add('bg-blue-100', 'font-medium');
});

// Generate seat map for selected row
function generateSeatMap(row) {
    const seatMap = document.getElementById('seat-map');
    seatMap.innerHTML = '';
    
    // Create 12 seats (1-12) for the selected row
    for (let i = 1; i <= 12; i++) {
        const seatNumber = i;
        const seatId = `${row}${seatNumber}`;
        
        const seatElement = document.createElement('button');
        seatElement.className = 'seat py-2 px-1 bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 text-xs sm:text-sm';
        seatElement.textContent = seatNumber;
        seatElement.dataset.seat = seatId;
        seatElement.onclick = function() { selectSeat(this); };
        
        seatMap.appendChild(seatElement);
    }
}

// Select a row
function selectRow(row) {
    currentRow = row;
    generateSeatMap(row);
    
    // Update row button styles
    document.querySelectorAll('.row-btn').forEach(btn => {
        btn.classList.remove('bg-blue-100', 'font-medium');
    });
    document.querySelector(`[data-row="${row}"]`).classList.add('bg-blue-100', 'font-medium');
    
    // Reset seat selection if changing rows
    if (currentSeat) {
        const prevSeatElement = document.querySelector(`[data-seat="${currentSeat}"]`);
        if (prevSeatElement) {
            prevSeatElement.classList.remove('selected');
        }
        currentSeat = null;
        updateSelectedSeatDisplay();
        updateSubmitButton();
    }
}

// Select a seat
function selectSeat(element) {
    // Remove selection from previously selected seat
    if (currentSeat) {
        const prevSeatElement = document.querySelector(`[data-seat="${currentSeat}"]`);
        if (prevSeatElement) {
            prevSeatElement.classList.remove('selected');
        }
    }
    
    // Set new selection
    currentSeat = element.dataset.seat;
    element.classList.add('selected');
    
    // Update displays
    updateSelectedSeatDisplay();
    updateSubmitButton();
}



// Update the selected seat display
function updateSelectedSeatDisplay() {
    const display = document.getElementById('selected-seat-display');
    const seatText = document.getElementById('selected-seat');
    const mobileDisplay = document.getElementById('mobile-seat-display');
    
    if (currentSeat) {
        display.innerHTML = `
            <div class="flex items-center">
                <div class="mr-3 text-xl text-blue-600">
                    <i class="fas fa-chair"></i>
                </div>
                <div>
                    <p class="text-blue-500 text-xs">Your seat</p>
                    <p id="selected-seat" class="font-medium text-blue-800">${currentSeat}</p>
                </div>
            </div>
        `;
        
        mobileDisplay.innerHTML = `
            <i class="fas fa-chair mr-1"></i>
            <span>${currentSeat}</span>
        `;
    } else {
        display.innerHTML = `
            <div class="flex items-center">
                <div class="mr-3 text-xl text-blue-600">
                    <i class="fas fa-chair"></i>
                </div>
                <div>
                    <p class="text-blue-500 text-xs">Your seat</p>
                    <p id="selected-seat" class="font-medium text-blue-800">Not selected</p>
                </div>
            </div>
        `;
        
        mobileDisplay.innerHTML = `
            <i class="fas fa-chair mr-1"></i>
            <span>No seat</span>
        `;
    }
}

        // Select a category
        function selectCategory(category) {
            // Update category button styles
            document.querySelectorAll('.category-btn').forEach(btn => {
                btn.classList.remove('active');
            });
            event.target.classList.add('active');
            
            // Show selected category content
            document.querySelectorAll('.category-content').forEach(content => {
                content.classList.add('hidden');
            });
            document.getElementById(category).classList.remove('hidden');
        }

        // Add item to order
        function addToOrder(name, price) {
            if (!currentSeat) {
                alert("Please select your seat first!");
                return;
            }
            
            // Add item to order array
            orderItems.push({ name, price });
            total += price;
            
            // Update order display
            updateOrderDisplay();
            updateSubmitButton();
            
            // Scroll to order items
            document.getElementById('order-items').scrollTop = document.getElementById('order-items').scrollHeight;
        }

        // Update order display
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

        // Remove item from order
        function removeItem(index) {
            total -= orderItems[index].price;
            orderItems.splice(index, 1);
            updateOrderDisplay();
            updateSubmitButton();
        }

        // Clear entire order
        function clearOrder() {
            if (orderItems.length === 0) return;
            
            if (confirm("Are you sure you want to clear your order?")) {
                orderItems = [];
                total = 0;
                updateOrderDisplay();
                updateSubmitButton();
            }
        }

        // Update submit button state
        function updateSubmitButton() {
            const submitBtn = document.getElementById('submit-order');
            if (currentSeat && orderItems.length > 0) {
                submitBtn.disabled = false;
            } else {
                submitBtn.disabled = true;
            }
        }

        // Submit order
        function submitOrder() {
            if (!currentSeat || orderItems.length === 0) return;
            
            // Get order notes
            const notes = document.getElementById('order-notes').value;
            
            // Prepare data for printing
            const orderData = {
                seat: currentSeat,
                items: orderItems,
                total: total,
                notes: notes,
                timestamp: new Date().toLocaleString()
            };
            
            // Send to printer
            printReceipt(orderData);
            
            // Show confirmation modal
            showConfirmation(orderData);
        }

        // Show confirmation modal
        function showConfirmation(orderData) {
            const modal = document.getElementById('confirmation-modal');
            const message = document.getElementById('confirmation-message');
            const summary = document.getElementById('order-summary');
            
            // Create order summary
            let summaryText = `Seat ${orderData.seat}: `;
            orderData.items.forEach(item => {
                summaryText += `${item.name} ($${item.price}), `;
            });
            summaryText = summaryText.slice(0, -2); // Remove trailing comma
            summaryText += ` | Total: $${orderData.total}`;
            
            summary.textContent = summaryText;
            
            // Random server time estimate
            const waitTime = Math.floor(Math.random() * 15) + 10;
            message.textContent = `Your order will arrive in ~${waitTime} minutes.`;
            
            modal.classList.remove('hidden');
        }

        // Close modal
        function closeModal() {
            document.getElementById('confirmation-modal').classList.add('hidden');
            
            // Reset order
            orderItems = [];
            total = 0;
            document.getElementById('order-notes').value = '';
            updateOrderDisplay();
            updateSubmitButton();
        }

        // Print receipt function
        function printReceipt(orderData) {
            // Create receipt content
            let receiptContent = `
                BEACH BAR ORDER
                ================
                Seat: ${orderData.seat}
                Time: ${orderData.timestamp}
                
                ITEMS:
                ------
            `;
            
            orderData.items.forEach(item => {
                receiptContent += `${item.name} - $${item.price}\n`;
            });
            
            receiptContent += `
                ----------------
                TOTAL: $${orderData.total}
                
                Notes: ${orderData.notes || 'None'}
                ================
                Thank you!
            `;
            
            // In a real implementation, this would send to your thermal printer
            console.log('Printing receipt:\n', receiptContent);
            
            // Here you would add your printer connection code:
            // const data = receiptContent.encode('ascii') + (LINE_FEED * 3) + CUT_PAPER;
            // Send to printer using your existing method
        }
    </script>
    <script>
// Global seat selection functions
function selectRow(row) {
    console.log('Row selected:', row); // First verify this works
    currentRow = row;
    generateSeatMap(row);
    
    // Update UI
    document.querySelectorAll('.row-btn').forEach(btn => {
        btn.classList.remove('bg-blue-100', 'font-medium');
    });
    event.target.classList.add('bg-blue-100', 'font-medium');
}

function generateSeatMap(row) {
    const seatMap = document.getElementById('seat-map');
    if (!seatMap) {
        console.error('Seat map element not found!');
        return;
    }
    
    seatMap.innerHTML = '';
    for (let i = 1; i <= 12; i++) {
        const seat = document.createElement('button');
        seat.className = 'seat py-2 px-1 bg-blue-50 rounded-lg text-sm';
        seat.textContent = i;
        seat.onclick = function() { selectSeat(this); };
        seat.dataset.seat = `${row}${i}`;
        seatMap.appendChild(seat);
    }
}

function selectSeat(element) {
    if (currentSeat) {
        document.querySelector(`[data-seat="${currentSeat}"]`)
            ?.classList.remove('selected');
    }
    currentSeat = element.dataset.seat;
    element.classList.add('selected');
    updateSelectedSeatDisplay();
}

// Initialize
let currentRow = 'A';
let currentSeat = null;
generateSeatMap(currentRow);
</script>
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