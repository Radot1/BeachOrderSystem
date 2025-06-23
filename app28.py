from flask import Flask, request, redirect, render_template_string, session, jsonify
import socket
import csv
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this to a secure random key

# Printer configuration
PRINTER_IP = '192.168.2.218'
PRINTER_PORT = 9100

# ESC/POS commands
CUT_PAPER = b'\x1D\x56\x00'  # Full cut command
LINE_FEED = b'\n'

# Menu XML file path
MENU_FILE = 'menu.xml'

def ensure_menu_file():
    """Create initial menu.xml if it doesn't exist"""
    if not os.path.exists(MENU_FILE):
        root = ET.Element('menu')
        categories = [
            ('Snacks', 'bg-green-100', [
                ('Chicken nuggets with potatoes', '', 8),
                ('Homemade Pizza Margherita', '', 9.5),
            ]),
            ('Salads', 'bg-green-100', [
                ('No1 Salads Seasonal Fruits', '', 7),
                ('No2 Salads Pure', '', 7.5),
            ]),
            ('Coffees', 'bg-yellow-100', [
                ('Freddo Cappuccino', '', 3.5, 'fas fa-cube'),
                ('Freddo Espresso', '', 3, 'fas fa-cube'),
            ])
        ]
        
        for cat_name, color, items in categories:
            category = ET.SubElement(root, 'category', name=cat_name, color=color)
            for item in items:
                item_elem = ET.SubElement(category, 'item')
                ET.SubElement(item_elem, 'name').text = item[0]
                ET.SubElement(item_elem, 'description').text = item[1] if len(item) > 1 else ''
                ET.SubElement(item_elem, 'price').text = str(item[2])
                if len(item) > 3:
                    ET.SubElement(item_elem, 'icon').text = item[3]
        
        tree = ET.ElementTree(root)
        tree.write(MENU_FILE, encoding='utf-8', xml_declaration=True)

def get_menu_data():
    """Read menu data from XML file"""
    ensure_menu_file()
    tree = ET.parse(MENU_FILE)
    root = tree.getroot()
    
    menu_data = {}
    for category in root.findall('category'):
        cat_name = category.get('name')
        cat_color = category.get('color')
        items = []
        
        for item in category.findall('item'):
            name = item.find('name').text
            description_elem = item.find('description')
            description = description_elem.text if description_elem is not None else ''
            price = float(item.find('price').text)
            icon_elem = item.find('icon')
            icon = icon_elem.text if icon_elem is not None else ''
            
            items.append({
                'name': name,
                'description': description,
                'basePrice': price,
                'icon': icon
            })
        
        menu_data[cat_name] = {
            'color': cat_color,
            'items': items
        }
    
    return menu_data

def save_menu_data(menu_data):
    """Save menu data to XML file"""
    root = ET.Element('menu')
    
    for cat_name, category in menu_data.items():
        cat_elem = ET.SubElement(root, 'category', name=cat_name, color=category['color'])
        
        for item in category['items']:
            item_elem = ET.SubElement(cat_elem, 'item')
            ET.SubElement(item_elem, 'name').text = item['name']
            desc_elem = ET.SubElement(item_elem, 'description')
            desc_elem.text = item.get('description', '')
            ET.SubElement(item_elem, 'price').text = str(item['basePrice'])
            if item.get('icon'):
                icon_elem = ET.SubElement(item_elem, 'icon')
                icon_elem.text = item['icon']
    
    tree = ET.ElementTree(root)
    tree.write(MENU_FILE, encoding='utf-8', xml_declaration=True)

def log_order_to_csv(order_data):
    # Create directory if it doesn't exist
    logs_dir = Path("order_logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Daily CSV filename (e.g., "orders_2023-08-15.csv")
    today = datetime.now().strftime("%Y-%m-%d")
    csv_file = logs_dir / f"orders_{today}.csv"
    
    # CSV headers
    fieldnames = ["timestamp", "seat", "item_name", "quantity", "price", "payment_method"]
    
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
                "quantity": item['quantity'],
                "price": item['price'],
                "payment_method": ""  # Items don't have payment method
            })

    # Calculate daily totals for cash and card
    daily_cash_total = 0
    daily_card_total = 0
    if csv_file.exists():
        with open(csv_file, mode='r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Only sum rows that are actual items
                if row['item_name'] and row['item_name'] not in ['ORDER TOTAL', 'DAILY TOTAL', 'CASH TOTAL', 'CARD TOTAL']:
                    try:
                        item_total = float(row['price']) * int(row['quantity'])
                        # Check payment method for order total rows
                        if row['payment_method'] == 'CASH':
                            daily_cash_total += item_total
                        elif row['payment_method'] == 'CARD':
                            daily_card_total += item_total
                    except (ValueError, TypeError):
                        pass

    # Append the order total with payment method
    payment_method = "CARD" if order_data.get('payByCard') else "CASH"
    with open(csv_file, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # Write the current order total
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            order_data['seat'],
            "ORDER TOTAL",
            "",  # Empty quantity field
            order_data['total'],
            payment_method
        ])
        
        # Write the daily totals
        if order_data['items']:
            writer.writerow(["", "", "CASH TOTAL", "", round(daily_cash_total, 2), ""])
            writer.writerow(["", "", "CARD TOTAL", "", round(daily_card_total, 2), ""])
            writer.writerow(["", "", "DAILY TOTAL", "", round(daily_cash_total + daily_card_total, 2), ""])

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
            border-color: #f59e0b;
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
        
        /* Modal Styles */
        .modal-backdrop {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.5);
            z-index: 99;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.3s ease;
        }
        .modal-backdrop.active {
            opacity: 1;
            pointer-events: auto;
        }
        .modal {
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%) scale(0.95);
            transition: transform 0.3s ease, opacity 0.3s ease;
            z-index: 100;
            opacity: 0;
            pointer-events: none;
        }
        .modal.active {
             transform: translate(-50%, -50%) scale(1);
             opacity: 1;
             pointer-events: auto;
        }
        .pill-btn.active {
            background-color: #3b82f6;
            color: white;
        }
    </style>
    <script>
        // Global variables
        let currentRow = 'A';
        let currentSeat = null;
        let orderItems = [];
        let total = 0;
        let orderPanelOpen = false;
        let menuData = {};
        const colorOptions = {
            yellow: 'bg-yellow-100',
            green: 'bg-green-100',
            purple: 'bg-purple-100'
        };

        // Toggle mobile order panel
        function toggleOrderPanel() {
            orderPanelOpen = !orderPanelOpen;
            const panel = document.getElementById('order-panel-mobile');
            const backdrop = document.getElementById('order-panel-backdrop');
            
            if (orderPanelOpen) {
                panel.classList.add('active');
                backdrop.classList.add('active');
                document.body.style.overflow = 'hidden';
            } else {
                panel.classList.remove('active');
                backdrop.classList.remove('active');
                document.body.style.overflow = '';
            }
        }

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
            
            for (let i = 1; i <= 25; i++) {
                const seat = document.createElement('button');
                seat.className = 'seat py-2 px-1 bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 text-base sm:text-sm w-full';
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
            
            let description = '';
            for (const categoryName in menuData) {
                const category = menuData[categoryName];
                for (const item of category.items) {
                    if (item.name === name.split(' (')[0]) {
                        description = item.description || '';
                        break;
                    }
                }
                if (description) break;
            }
            
            const existingItem = orderItems.find(item => item.name === name && !item.customText);
            
            if (existingItem) {
                existingItem.quantity += 1;
            } else {
                orderItems.push({ 
                    name, 
                    price, 
                    quantity: 1,
                    customText: "",
                    description: description
                });
            }
            
            total += price;
            updateOrderDisplay();
            
            if (window.innerWidth < 1024 && !orderPanelOpen) {
                toggleOrderPanel();
            }
        }

        function updateOrderDisplay() {
            const orderItemsContainer = document.getElementById('order-items');
            const mobileOrderItemsContainer = document.getElementById('mobile-order-items');
            
            if (orderItems.length === 0) {
                orderItemsContainer.innerHTML = '<p class="text-blue-500 text-center py-4 text-sm">No items added yet</p>';
                if (mobileOrderItemsContainer) {
                    mobileOrderItemsContainer.innerHTML = '<p class="text-blue-500 text-center py-4 text-sm">No items added yet</p>';
                }
                document.getElementById('order-total').textContent = '€0';
                if (document.getElementById('mobile-order-total')) {
                    document.getElementById('mobile-order-total').textContent = '€0';
                }
                return;
            }
            
            let itemsHTML = '';
            orderItems.forEach((item, index) => {
                const displayName = item.quantity > 1 
                    ? `${item.name} "${item.quantity}"` 
                    : item.name;
                    
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
            if (mobileOrderItemsContainer) {
                mobileOrderItemsContainer.innerHTML = itemsHTML;
            }
            document.getElementById('order-total').textContent = `€${total.toFixed(2)}`;
            if (document.getElementById('mobile-order-total')) {
                document.getElementById('mobile-order-total').textContent = `€${total.toFixed(2)}`;
            }
        }

        function adjustQuantity(index, change) {
            const item = orderItems[index];
            const newQuantity = item.quantity + change;
            
            if (newQuantity < 1) {
                removeItem(index);
                return;
            }
            
            total += item.price * change;
            item.quantity = newQuantity;
            
            updateOrderDisplay();
        }

        function editItemText(index) {
            const item = orderItems[index];
            const customText = prompt("Add text to append to this item (it will appear in brackets):", item.customText || '');
            
            if (customText !== null) {
                item.customText = customText;
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

            const desktopNotes = document.getElementById('order-notes').value;
            const mobileNotesEl = document.getElementById('mobile-order-notes');
            const mobileNotes = mobileNotesEl ? mobileNotesEl.value : '';
            const notes = mobileNotes || desktopNotes;

            const payByCardDesktopEl = document.getElementById('pay-by-card');
            const payByCardMobileEl = document.getElementById('mobile-pay-by-card');
            const payByCard = (payByCardDesktopEl && payByCardDesktopEl.checked) || (payByCardMobileEl && payByCardMobileEl.checked);

            const orderData = {
                seat: currentSeat,
                items: orderItems,
                total: total,
                notes: notes,
                payByCard: payByCard
            };
            
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
                    orderItems = [];
                    total = 0;
                    
                    document.getElementById('order-notes').value = '';
                    if (mobileNotesEl) {
                        mobileNotesEl.value = '';
                    }

                    if (payByCardDesktopEl) payByCardDesktopEl.checked = false;
                    if (payByCardMobileEl) payByCardMobileEl.checked = false;

                    updateOrderDisplay();
                    if (window.innerWidth < 1024) {
                        toggleOrderPanel();
                    }
                } else {
                    alert('Printing failed: ' + (data.message || 'Unknown error'));
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Printing failed: ' + error.message);
            });
        }
        
        // Menu Management Functions
        function openManagementModal() {
            document.getElementById('management-modal').classList.add('active');
            document.getElementById('modal-backdrop').classList.add('active');
            switchManagementView('categories');
            renderManagementCategories();
            renderManagementItems();
        }

        function closeManagementModal() {
            document.getElementById('management-modal').classList.remove('active');
            document.getElementById('modal-backdrop').classList.remove('active');
        }

        function switchManagementView(view) {
             document.querySelectorAll('.pill-btn').forEach(btn => btn.classList.remove('active'));
             document.querySelector(`.pill-btn[data-view="${view}"]`).classList.add('active');
             
             document.getElementById('category-management-view').classList.toggle('hidden', view !== 'categories');
             document.getElementById('item-management-view').classList.toggle('hidden', view !== 'items');
        }

        function renderManagementCategories() {
            const container = document.getElementById('management-categories-list');
            container.innerHTML = '';
            Object.keys(menuData).forEach(categoryName => {
                const category = menuData[categoryName];
                const div = document.createElement('div');
                div.className = 'flex justify-between items-center p-2 bg-gray-100 rounded';
                div.innerHTML = `
                    <div class="flex items-center">
                        <div class="w-4 h-4 rounded-full mr-3 ${category.color}"></div>
                        <span>${categoryName}</span>
                    </div>
                    <div>
                        <button onclick="editCategory('${categoryName}')" class="text-blue-500 hover:text-blue-700 mr-2"><i class="fas fa-edit"></i></button>
                        <button onclick="deleteCategory('${categoryName}')" class="text-red-500 hover:text-red-700"><i class="fas fa-trash"></i></button>
                    </div>
                `;
                container.appendChild(div);
            });
        }
        
        async function addCategory() {
            const newCategoryName = prompt("Enter new category name:");
            if (!newCategoryName) return;
            
            const colorKey = prompt("Choose a color: yellow, green, or purple").toLowerCase();
            const colorClass = colorOptions[colorKey] || 'bg-yellow-100';

            try {
                const response = await fetch('/api/menu/category', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        name: newCategoryName, 
                        color: colorClass 
                    })
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.message || 'Failed to add category');
                }
                
                // Reload menu data
                await loadMenuData();
                renderManagementCategories();
                renderCategoryTabs();
                renderMenu();
            } catch (error) {
                console.error('Error adding category:', error);
                alert('Error: ' + error.message);
            }
        }

        async function editCategory(oldName) {
            const newName = prompt("Enter new name for category:", oldName);
            if (!newName) return;
            
            const colorKey = prompt(`Choose a new color for ${newName}: yellow, green, or purple`).toLowerCase();
            const newColorClass = colorOptions[colorKey] || menuData[oldName].color;

            try {
                const response = await fetch(`/api/menu/category/${encodeURIComponent(oldName)}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        new_name: newName,
                        color: newColorClass
                    })
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.message || 'Failed to update category');
                }
                
                // Reload menu data
                await loadMenuData();
                renderManagementCategories();
                renderCategoryTabs();
                renderMenu();
            } catch (error) {
                console.error('Error updating category:', error);
                alert('Error: ' + error.message);
            }
        }

        async function deleteCategory(categoryName) {
            if (!confirm(`Are you sure you want to delete the category "${categoryName}"? This will also delete all items within it.`)) {
                return;
            }
            
            try {
                const response = await fetch(`/api/menu/category/${encodeURIComponent(categoryName)}`, {
                    method: 'DELETE'
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.message || 'Failed to delete category');
                }
                
                // Reload menu data
                await loadMenuData();
                renderManagementCategories();
                renderCategoryTabs();
                renderMenu();
            } catch (error) {
                console.error('Error deleting category:', error);
                alert('Error: ' + error.message);
            }
        }
        
        function renderManagementItems() {
            const container = document.getElementById('management-items-list');
            const categorySelect = document.getElementById('item-category-select');
            container.innerHTML = '';
            const selectedCategory = categorySelect.value;
            
            // Re-populate select dropdown to ensure it's up to date
            const currentSelection = categorySelect.value;
            categorySelect.innerHTML = '';
             Object.keys(menuData).forEach(categoryName => {
                const option = document.createElement('option');
                option.value = categoryName;
                option.textContent = categoryName;
                categorySelect.appendChild(option);
            });
            categorySelect.value = currentSelection;

            if (menuData[selectedCategory] && menuData[selectedCategory].items) {
                menuData[selectedCategory].items.forEach((item, index) => {
                    const div = document.createElement('div');
                    div.className = 'flex justify-between items-center p-2 bg-gray-100 rounded';
                    div.innerHTML = `
                        <span>${item.name} - €${item.basePrice.toFixed(2)}</span>
                        <div>
                            <button onclick="editItem('${selectedCategory}', ${index})" class="text-blue-500 hover:text-blue-700 mr-2"><i class="fas fa-edit"></i></button>
                            <button onclick="deleteItem('${selectedCategory}', ${index})" class="text-red-500 hover:text-red-700"><i class="fas fa-trash"></i></button>
                        </div>
                    `;
                    container.appendChild(div);
                });
            }
        }
        
        async function addItem() {
            const category = document.getElementById('item-category-select').value;
            if(!category) {
                alert("Please select a category first.");
                return;
            }
            
            const name = prompt("Enter new item name:");
            if (!name) return;
            
            const price = parseFloat(prompt("Enter item price:"));
            if (isNaN(price)) {
                alert("Invalid price.");
                return;
            }
            
            const description = prompt("Enter item description (optional):");
            const icon = prompt("Enter icon class (optional, e.g., 'fas fa-coffee'):");

            try {
                const response = await fetch('/api/menu/item', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        category: category,
                        name: name,
                        description: description || '',
                        price: price,
                        icon: icon || ''
                    })
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.message || 'Failed to add item');
                }
                
                // Reload menu data
                await loadMenuData();
                renderManagementItems();
                renderMenu();
            } catch (error) {
                console.error('Error adding item:', error);
                alert('Error: ' + error.message);
            }
        }
        
        async function editItem(category, index) {
            const item = menuData[category].items[index];
            const name = prompt("Enter new item name:", item.name);
            if (!name) return;
            
            const price = parseFloat(prompt("Enter item price:", item.basePrice));
            if (isNaN(price)) {
                alert("Invalid price.");
                return;
            }
            
            const description = prompt("Enter item description:", item.description || "");
            const icon = prompt("Enter icon class:", item.icon || "");

            try {
                const response = await fetch('/api/menu/item', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        category: category,
                        index: index,
                        name: name,
                        description: description,
                        price: price,
                        icon: icon
                    })
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.message || 'Failed to update item');
                }
                
                // Reload menu data
                await loadMenuData();
                renderManagementItems();
                renderMenu();
            } catch (error) {
                console.error('Error updating item:', error);
                alert('Error: ' + error.message);
            }
        }

        async function deleteItem(category, index) {
            if (!confirm(`Are you sure you want to delete "${menuData[category].items[index].name}"?`)) {
                return;
            }
            
            try {
                const response = await fetch('/api/menu/item', {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        category: category,
                        index: index
                    })
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.message || 'Failed to delete item');
                }
                
                // Reload menu data
                await loadMenuData();
                renderManagementItems();
                renderMenu();
            } catch (error) {
                console.error('Error deleting item:', error);
                alert('Error: ' + error.message);
            }
        }
        
        // Menu Rendering Function
        function renderMenu() {
            const menuContainer = document.getElementById('menu-items');
            menuContainer.innerHTML = '';

            for (const categoryName in menuData) {
                const category = menuData[categoryName];
                const categoryDiv = document.createElement('div');
                categoryDiv.className = 'category-content hidden';
                categoryDiv.id = categoryName;
                
                const itemsGrid = document.createElement('div');
                itemsGrid.className = 'grid grid-cols-1 gap-1';

                category.items.forEach(item => {
                    const itemWrapper = document.createElement('div');
                    itemWrapper.className = 'relative';
                    
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
                    
                    itemButton.onclick = () => addToOrder(item.name, item.basePrice);
                    itemWrapper.appendChild(itemButton);
                    itemsGrid.appendChild(itemWrapper);
                });

                categoryDiv.appendChild(itemsGrid);
                menuContainer.appendChild(categoryDiv);
            }

            const firstCategoryButton = document.querySelector('.category-btn');
            if (firstCategoryButton) {
                firstCategoryButton.click();
            }
        }
        
        function renderCategoryTabs() {
            const container = document.getElementById('category-tabs-container');
            container.innerHTML = '';
            let isFirst = true;
            for (const categoryName in menuData) {
                const category = menuData[categoryName];
                const button = document.createElement('button');
                button.onclick = function() { selectCategory(categoryName, this) };
                button.className = `category-btn px-3 py-3 rounded-lg ${category.color} text-blue-800 font-medium whitespace-nowrap text-sm border-2 border-transparent`;
                button.innerHTML = `<i class="fas fa-tag mr-2"></i>${categoryName}`;
                
                container.appendChild(button);
            }
        }
        
        // Load menu data from server
        async function loadMenuData() {
            try {
                const response = await fetch('/api/menu');
                if (!response.ok) {
                    throw new Error('Failed to load menu data');
                }
                menuData = await response.json();
            } catch (error) {
                console.error('Error loading menu:', error);
                alert('Failed to load menu. Please try again.');
            }
        }
        
        // Initialize
        window.onload = async function() {
            // Load menu data from server
            await loadMenuData();
            
            generateSeatMap('A');
            document.querySelector('[data-row="A"]').classList.add('bg-blue-100', 'font-medium');
            renderCategoryTabs();
            renderMenu();
            
            if (window.innerWidth < 1024) {
                const toggleBtn = document.createElement('button');
                toggleBtn.className = 'fixed bottom-4 right-4 bg-blue-500 text-white p-3 rounded-full shadow-lg z-30 lg:hidden';
                toggleBtn.innerHTML = '<i class="fas fa-receipt"></i>';
                toggleBtn.onclick = toggleOrderPanel;
                document.body.appendChild(toggleBtn);
            }
        };

    </script>
</head>
<body class="bg-gradient-to-b from-blue-50 to-blue-100 min-h-screen">
    <div class="fixed top-4 right-4 z-50">
        <button onclick="openManagementModal()" class="bg-gray-700 text-white w-12 h-12 rounded-full shadow-lg flex items-center justify-center hover:bg-gray-800 transition">
            <i class="fas fa-cog text-xl"></i>
        </button>
    </div>

    <div id="modal-backdrop" class="modal-backdrop"></div>
    
    <div id="management-modal" class="modal bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col">
        <div class="p-4 border-b">
            <div class="flex justify-between items-center mb-4">
                <h2 class="text-lg font-semibold text-gray-800">Manage Menu</h2>
                <button onclick="closeManagementModal()" class="text-gray-500 hover:text-gray-800 text-2xl">&times;</button>
            </div>
             <div class="flex border-b">
                <button onclick="switchManagementView('categories')" data-view="categories" class="pill-btn flex-1 py-2 text-center text-gray-600 hover:bg-blue-100">Manage Categories</button>
                <button onclick="switchManagementView('items')" data-view="items" class="pill-btn flex-1 py-2 text-center text-gray-600 hover:bg-blue-100">Manage Items</button>
            </div>
        </div>
        <div class="p-6 overflow-y-auto flex-grow">
            <div id="category-management-view" class="hidden">
                <div class="flex justify-between items-center mb-4">
                    <h3 class="font-semibold text-gray-700">Categories</h3>
                    <button onclick="addCategory()" class="bg-blue-500 text-white px-3 py-1 rounded-md text-sm hover:bg-blue-600">Add New</button>
                </div>
                <div id="management-categories-list" class="space-y-2">
                    </div>
            </div>
            <div id="item-management-view" class="hidden">
                <div class="flex justify-between items-center mb-4">
                    <h3 class="font-semibold text-gray-700">Items</h3>
                    <button onclick="addItem()" class="bg-green-500 text-white px-3 py-1 rounded-md text-sm hover:bg-green-600">Add New</button>
                </div>
                <div class="mb-4">
                    <label for="item-category-select" class="block text-sm font-medium text-gray-700 mb-1">Category:</label>
                    <select id="item-category-select" onchange="renderManagementItems()" class="w-full p-2 border border-gray-300 rounded-md"></select>
                </div>
                <div id="management-items-list" class="space-y-2 max-h-64 overflow-y-auto">
                    </div>
            </div>
        </div>
        <div class="p-4 bg-gray-50 border-t text-right">
             <button onclick="closeManagementModal()" class="bg-gray-500 text-white px-4 py-2 rounded-md hover:bg-gray-600">Close</button>
        </div>
    </div>


    <div id="order-panel-backdrop" class="order-panel-backdrop lg:hidden" onclick="toggleOrderPanel()"></div>
    
    <div class="container mx-auto px-2 py-4">
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

        <div class="grid lg:grid-cols-2 gap-4">
            <div class="space-y-4">
                <div class="bg-white rounded-xl shadow-md p-4 border border-blue-200">
                    <h2 class="text-lg font-semibold text-blue-800 mb-3 flex items-center">
                        <i class="fas fa-map-marker-alt text-blue-500 mr-2"></i>
                        Select Your Seat
                    </h2>
                    
                    <div class="mb-4">
                        <div class="flex flex-wrap gap-2 mb-2">
                            <button onclick="selectRow('A')" class="row-btn py-2 px-6 text-xl bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition whitespace-nowrap" data-row="A">Row A</button>
                            <button onclick="selectRow('B')" class="row-btn py-2 px-6 text-xl bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition whitespace-nowrap" data-row="B">Row B</button>
                            <button onclick="selectRow('C')" class="row-btn py-2 px-6 text-xl bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition whitespace-nowrap" data-row="C">Row C</button>
                            <button onclick="selectRow('D')" class="row-btn py-2 px-6 text-xl bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition whitespace-nowrap" data-row="D">Row D</button>
                            <button onclick="selectRow('EXTRA')" class="row-btn py-2 px-6 text-xl bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition whitespace-nowrap" data-row="EXTRA">EXTRA</button>
                        </div>
                    </div>

                    <div class="mb-4">
                        <h3 class="text-xs font-medium text-blue-700 mb-2">Available Seats</h3>
                        <div id="seat-map" class="grid grid-cols-5 gap-2"></div>
                    </div>

                    <div id="selected-seat-display" class="bg-blue-50 p-3 rounded-lg border border-blue-200 flex items-center justify-between">
                        <div class="flex items-center">
                            <div class="mr-3 text-xl text-blue-600"><i class="fas fa-chair"></i></div>
                            <div>
                                <p class="text-blue-500 text-xs">Your seat</p>
                                <p id="selected-seat" class="font-medium text-blue-800">Not selected</p>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="bg-white rounded-xl shadow-md p-4 border border-blue-200">
                    <h2 class="text-lg font-semibold text-blue-800 mb-3 flex items-center">
                        <i class="fas fa-concierge-bell text-blue-500 mr-2"></i>
                        Menu
                    </h2>
                    <div id="category-tabs-container" class="mb-4 flex flex-wrap gap-2">
                        </div>
                    <div id="menu-items" class="mb-4 max-h-[60vh] overflow-y-auto pr-1"></div>
                </div>
            </div>

            <div class="hidden lg:block lg:sticky lg:top-4 h-fit">
                <div class="bg-white rounded-xl shadow-lg p-4 border border-blue-200 h-[calc(100vh-140px)] flex flex-col">
                    <div class="flex-1 overflow-hidden flex flex-col">
                        <div class="flex justify-between items-center mb-3">
                            <h3 class="text-sm font-semibold text-blue-800"><i class="fas fa-receipt mr-2"></i>Your Order</h3>
                            <button onclick="clearOrder()" class="text-red-500 hover:text-red-700 text-sm"><i class="fas fa-trash-alt mr-1"></i>Clear</button>
                        </div>
                        <div id="order-items" class="flex-1 overflow-y-auto space-y-2 pr-2">
                            <p class="text-blue-500 text-center py-4 text-sm">No items added yet</p>
                        </div>
                        <div class="mt-2 flex justify-between items-center bg-blue-100 px-3 py-2 rounded-lg">
                            <span class="font-medium text-blue-800 text-sm flex items-center"><i class="fas fa-coins mr-1"></i> Total:</span>
                            <span id="order-total" class="font-bold text-blue-700 text-sm">€0</span>
                        </div>
                    </div>
                    <div class="mb-2">
                        <label for="order-notes" class="block text-xs font-medium text-blue-700 mb-1 flex items-center"><i class="fas fa-sticky-note mr-1"></i> Special Instructions</label>
                        <textarea id="order-notes" rows="2" class="w-full px-3 py-2 border border-blue-200 rounded-lg focus:ring-1 focus:ring-blue-300 focus:border-blue-300 text-sm" placeholder="Allergies? Modifications?"></textarea>
                    </div>
                    <div class="flex items-center justify-center my-3">
                        <input id="pay-by-card" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500">
                        <label for="pay-by-card" class="ml-2 block text-sm font-medium text-blue-800">Pay by Card</label>
                    </div>
                    <button id="submit-order" onclick="submitOrder()" class="w-full py-3 bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white font-medium rounded-lg shadow-md transition disabled:opacity-50 disabled:cursor-not-allowed text-sm">
                        <i class="fas fa-paper-plane mr-1"></i> Send Order
                    </button>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
'''

def encode_escpos(text):
    return text.replace("€", "\xD5").encode('latin-1', errors='replace')

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/menu', methods=['GET'])
def api_get_menu():
    return jsonify(get_menu_data())

@app.route('/api/menu/category', methods=['POST'])
def api_add_category():
    data = request.json
    name = data.get('name')
    color = data.get('color')
    
    if not name or not color:
        return jsonify({'status': 'error', 'message': 'Name and color are required'}), 400
    
    menu_data = get_menu_data()
    
    if name in menu_data:
        return jsonify({'status': 'error', 'message': 'Category already exists'}), 400
    
    menu_data[name] = {
        'color': color,
        'items': []
    }
    
    save_menu_data(menu_data)
    return jsonify({'status': 'success'})

@app.route('/api/menu/category/<name>', methods=['PUT'])
def api_update_category(name):
    data = request.json
    new_name = data.get('new_name')
    color = data.get('color')
    
    menu_data = get_menu_data()
    
    if name not in menu_data:
        return jsonify({'status': 'error', 'message': 'Category not found'}), 404
    
    # If renaming, check new name doesn't exist
    if new_name and new_name != name and new_name in menu_data:
        return jsonify({'status': 'error', 'message': 'New category name already exists'}), 400
    
    category_data = menu_data[name]
    del menu_data[name]
    
    # Use new name if provided, otherwise keep original name
    category_name = new_name if new_name else name
    
    # Update color if provided
    if color:
        category_data['color'] = color
    
    menu_data[category_name] = category_data
    save_menu_data(menu_data)
    return jsonify({'status': 'success'})

@app.route('/api/menu/category/<name>', methods=['DELETE'])
def api_delete_category(name):
    menu_data = get_menu_data()
    
    if name not in menu_data:
        return jsonify({'status': 'error', 'message': 'Category not found'}), 404
    
    del menu_data[name]
    save_menu_data(menu_data)
    return jsonify({'status': 'success'})

@app.route('/api/menu/item', methods=['POST'])
def api_add_item():
    data = request.json
    category = data.get('category')
    name = data.get('name')
    description = data.get('description')
    price = data.get('price')
    icon = data.get('icon')
    
    menu_data = get_menu_data()
    
    if category not in menu_data:
        return jsonify({'status': 'error', 'message': 'Category not found'}), 404
    
    menu_data[category]['items'].append({
        'name': name,
        'description': description,
        'basePrice': price,
        'icon': icon
    })
    
    save_menu_data(menu_data)
    return jsonify({'status': 'success'})

@app.route('/api/menu/item', methods=['PUT'])
def api_update_item():
    data = request.json
    category = data.get('category')
    index = data.get('index')
    name = data.get('name')
    description = data.get('description')
    price = data.get('price')
    icon = data.get('icon')
    
    menu_data = get_menu_data()
    
    if category not in menu_data:
        return jsonify({'status': 'error', 'message': 'Category not found'}), 404
    
    items = menu_data[category]['items']
    
    if index < 0 or index >= len(items):
        return jsonify({'status': 'error', 'message': 'Invalid item index'}), 400
    
    items[index] = {
        'name': name,
        'description': description,
        'basePrice': price,
        'icon': icon
    }
    
    save_menu_data(menu_data)
    return jsonify({'status': 'success'})

@app.route('/api/menu/item', methods=['DELETE'])
def api_delete_item():
    data = request.json
    category = data.get('category')
    index = data.get('index')
    
    menu_data = get_menu_data()
    
    if category not in menu_data:
        return jsonify({'status': 'error', 'message': 'Category not found'}), 404
    
    items = menu_data[category]['items']
    
    if index < 0 or index >= len(items):
        return jsonify({'status': 'error', 'message': 'Invalid item index'}), 400
    
    del items[index]
    save_menu_data(menu_data)
    return jsonify({'status': 'success'})

@app.route('/print', methods=['POST'])
def print_receipt():
    try:
        order_data = request.json
        seat = order_data['seat']
        pay_by_card = order_data.get('payByCard', False)

        log_order_to_csv(order_data)

        ESC = b'\x1B'
        RESET = ESC + b'!\x00'
        BOLD_LARGE = ESC + b'!\x38'
        BOLD = ESC + b'!\x08'
        SMALL = ESC + b'!\x00'
        SET_CP_858 = ESC + b'\x74\x13'

        pure_text = "PURE"
        spacing = 32 - len(pure_text) - len(seat)

        receipt_lines = [
            SET_CP_858,
            encode_escpos(pure_text + ' ' * spacing),
            BOLD_LARGE + encode_escpos(seat) + RESET,
            encode_escpos("\n" + "="*32),
            encode_escpos(f"\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"),
            encode_escpos("\n\nITEMS:\n------")
        ]

        for item in order_data['items']:
            qty = item.get('quantity', 1)
            line = f"\n{qty}x {item['name']}"
            
            if item.get('customText'):
                line += f" [{item['customText']}]"
            line += f" - €{item['price'] * qty:.2f}"
            receipt_lines.append(encode_escpos(line))
            
            description = item.get('description', '')
            if description:
                receipt_lines.append(SMALL + encode_escpos(f"\n  ({description})") + RESET)

        # Add payment method to receipt
        payment_text = "CARD" if pay_by_card else "CASH"
        receipt_lines.extend([
            encode_escpos("\n\n" + "-"*32),
            encode_escpos(f"\nSUBTOTAL: €{sum(item['price'] * item.get('quantity', 1) for item in order_data['items']):.2f}"),
            encode_escpos(f"\nTOTAL: €{order_data['total']:.2f}"),
            BOLD + encode_escpos(f"\n\nPAYMENT METHOD: {payment_text}") + RESET,
        ])

        receipt_lines.extend([
            encode_escpos(f"\n\nNotes: {order_data.get('notes', 'None')}"),
            encode_escpos("\n" + "="*32),
            encode_escpos("\nThank you!\n")
        ])

        data = b"".join(receipt_lines) + (LINE_FEED * 3) + CUT_PAPER

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((PRINTER_IP, PRINTER_PORT))
            s.sendall(data)

        return {'status': 'success'}

    except Exception as e:
        return {'status': 'error', 'message': str(e)}

if __name__ == '__main__':
    # Ensure menu file exists on startup
    ensure_menu_file()
    app.run(host='0.0.0.0', port=5000, debug=True)