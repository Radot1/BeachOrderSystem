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

def ensure_menu_file_has_order():
    """Reads the XML and adds an 'order' attribute if missing."""
    if not os.path.exists(MENU_FILE):
        return

    tree = ET.parse(MENU_FILE)
    root = tree.getroot()
    
    needs_rewrite = False
    for i, category_elem in enumerate(root.findall('category')):
        if 'order' not in category_elem.attrib:
            category_elem.set('order', str(i))
            needs_rewrite = True
    
    if needs_rewrite:
        tree.write(MENU_FILE, encoding='utf-8', xml_declaration=True)


def get_menu_data():
    """Read menu data from XML file, preserving order."""
    ensure_menu_file_has_order()
    tree = ET.parse(MENU_FILE)
    root = tree.getroot()
    
    # Read categories into a list
    categories = []
    for category in root.findall('category'):
        cat_name = category.get('name')
        cat_color = category.get('color')
        cat_order = int(category.get('order', 999))
        
        items = []
        for item in category.findall('item'):
            name = item.find('name').text
            description_elem = item.find('description')
            description = description_elem.text if description_elem is not None else ''
            price = float(item.find('price').text)
            icon_elem = item.find('icon')
            icon = icon_elem.text if icon_elem is not None else ''
            
            item_dict = {
                'name': name,
                'description': description,
                'basePrice': price,
                'icon': icon,
                'options': []
            }
            
            options_elem = item.find('options')
            if options_elem is not None:
                for option in options_elem.findall('option'):
                    item_dict['options'].append({
                        'label': option.get('label'),
                        'priceAdjustment': float(option.get('price_adjustment', '0'))
                    })
            items.append(item_dict)

        categories.append({
            'name': cat_name,
            'color': cat_color,
            'order': cat_order,
            'items': items
        })
    
    # Sort by the order attribute and return
    categories.sort(key=lambda x: x['order'])
    return categories

def save_menu_data(menu_list):
    """Save menu data list to XML file, preserving order."""
    root = ET.Element('menu')
    
    for index, category in enumerate(menu_list):
        cat_elem = ET.SubElement(root, 'category', 
                                 name=category['name'], 
                                 color=category['color'],
                                 order=str(index)) # Save index as order
        
        for item in category['items']:
            item_elem = ET.SubElement(cat_elem, 'item')
            ET.SubElement(item_elem, 'name').text = item['name']
            desc_elem = ET.SubElement(item_elem, 'description')
            desc_elem.text = item.get('description', '')
            ET.SubElement(item_elem, 'price').text = str(item['basePrice'])
            if item.get('icon'):
                icon_elem = ET.SubElement(item_elem, 'icon')
                icon_elem.text = item['icon']
            
            if 'options' in item and item['options']:
                options_elem = ET.SubElement(item_elem, 'options')
                for option in item['options']:
                    ET.SubElement(options_elem, 'option', 
                                  label=option['label'], 
                                  price_adjustment=str(option.get('priceAdjustment', 0)))
    
    tree = ET.ElementTree(root)
    tree.write(MENU_FILE, encoding='utf-8', xml_declaration=True)


def log_order_to_csv(order_data):
    logs_dir = Path("order_logs")
    logs_dir.mkdir(exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    csv_file = logs_dir / f"orders_{today}.csv"
    temp_file = csv_file.with_suffix('.tmp')

    fieldnames = ["timestamp", "seat", "item_name", "quantity", "price", "payment_method"]
    payment_method = "CARD" if order_data.get('payByCard') else "CASH"

    # Read existing rows as dicts (so header names are preserved)
    existing = []
    if csv_file.exists():
        with open(csv_file, newline='', encoding='utf-8') as f:
            dr = csv.DictReader(f)
            for row in dr:
                # skip any already-written TOTAL lines
                if row.get('item_name') and "TOTAL" not in row['item_name']:
                    existing.append(row)

    # Write everything back (header + old rows + new order + recalculated totals)
    with open(temp_file, 'w', newline='', encoding='utf-8') as f:
        dw = csv.DictWriter(f, fieldnames=fieldnames)
        dw.writeheader()

        # rewrite old entries
        for row in existing:
            dw.writerow(row)

        # write new order lines
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for item in order_data['items']:
            dw.writerow({
                "timestamp": now,
                "seat": order_data['seat'],
                "item_name": item['name'],
                "quantity": item.get('quantity', 1),
                "price": item['price'],
                "payment_method": ""
            })
        # order total
        dw.writerow({
            "timestamp": now,
            "seat": order_data['seat'],
            "item_name": "ORDER TOTAL",
            "quantity": "",
            "price": order_data['total'],
            "payment_method": payment_method
        })

    # Now recalc daily totals correctly
    daily_cash = daily_card = 0.0
    with open(temp_file, newline='', encoding='utf-8') as f:
        dr = csv.DictReader(f)
        for row in dr:
            if row['item_name'] == 'ORDER TOTAL':
                amt = float(row.get('price', 0) or 0)
                if row.get('payment_method') == 'CASH':
                    daily_cash += amt
                elif row.get('payment_method') == 'CARD':
                    daily_card += amt

    # append final summary rows
    with open(temp_file, 'a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(["", "", "CASH TOTAL", "", f"{daily_cash:.2f}", ""])
        w.writerow(["", "", "CARD TOTAL", "", f"{daily_card:.2f}", ""])
        w.writerow(["", "", "DAILY TOTAL", "", f"{(daily_cash + daily_card):.2f}", ""])

    # atomically replace
    os.replace(temp_file, csv_file)


HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        .seat { transition: all 0.2s ease; }
        .seat.selected { transform: scale(1.1); box-shadow: 0 0 10px rgba(251, 191, 36, 0.7); }
        .category-btn.active { background-color: #f59e0b; color: white; border-color: #f59e0b; }
        .order-item { animation: fadeIn 0.3s ease-in; }
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-thumb { background-color: rgba(59, 130, 246, 0.5); border-radius: 3px; }
        .modal-backdrop {
            position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.5); z-index: 99; opacity: 0;
            pointer-events: none; transition: opacity 0.3s ease;
        }
        .modal-backdrop.active { opacity: 1; pointer-events: auto; }
        .modal {
            position: fixed; top: 50%; left: 50%;
            transform: translate(-50%, -50%) scale(0.95);
            transition: transform 0.3s ease, opacity 0.3s ease;
            z-index: 100; opacity: 0; pointer-events: none;
        }
        .modal.active { transform: translate(-50%, -50%) scale(1); opacity: 1; pointer-events: auto; }
        .pill-btn.active { background-color: #3b82f6; color: white; }
        .options-modal-item {
            display: block; width: 100%; padding: 0.75rem 1rem;
            margin-bottom: 0.5rem; border: 1px solid #e5e7eb;
            border-radius: 0.5rem; text-align: left;
            transition: background-color 0.2s;
        }
        .options-modal-item:hover { background-color: #f3f4f6; }
        .color-swatch {
            width: 2rem; height: 2rem; border-radius: 9999px; cursor: pointer;
            border: 2px solid transparent; transition: all 0.2s;
        }
        .color-swatch.selected { border-color: #3b82f6; transform: scale(1.1); }

    @media (max-width: 1023px) {
        #seat-map { grid-template-columns: repeat(8, minmax(60px, 1fr)); overflow-x: auto; padding-bottom: 8px; }
        .order-panel-mobile {
            position: fixed; bottom: 0; left: 0; right: 0;
            max-height: 60vh; border-radius: 1rem 1rem 0 0;
            box-shadow: 0 -4px 12px rgba(0,0,0,0.1); z-index: 50;
            transform: translateY(100%); transition: transform 0.3s ease;
        }
        .order-panel-mobile.active { transform: translateY(0); }
        .order-panel-backdrop {
            position: fixed; top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(0,0,0,0.3); z-index: 40; opacity: 0;
            pointer-events: none; transition: opacity 0.3s ease;
        }
        .order-panel-backdrop.active { opacity: 1; pointer-events: auto; }
    }
    .order-item { word-break: break-word; line-height: 1.4; }
    .category-content { gap: 0.75rem; }
    .menu-item { padding: 1rem; border-radius: 0.75rem; }
    </style>
    <script>
        // Global variables
        let currentRow = 'A';
        let currentSeat = null;
        let orderItems = [];
        let total = 0;
        let orderPanelOpen = false;
        let menuData = []; // Changed to array to preserve order
        let currentItemWithOptions = null; // Used for the options modal
        const colorOptions = {
            'bg-yellow-100': 'Yellow',
            'bg-green-100': 'Green',
            'bg-purple-100': 'Purple',
            'bg-blue-100': 'Blue',
            'bg-red-100': 'Red',
            'bg-orange-100': 'Orange',
            'bg-teal-100': 'Teal'
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

        // --- ITEM OPTIONS MODAL ---
        function showOptionsModal(item) {
            currentItemWithOptions = item;
            const modal = document.getElementById('options-modal');
            const backdrop = document.getElementById('modal-backdrop');
            const title = document.getElementById('options-modal-title');
            const container = document.getElementById('options-modal-list');

            title.textContent = `Choose option for ${item.name}`;
            container.innerHTML = '';

            item.options.forEach(option => {
                const button = document.createElement('button');
                button.className = 'options-modal-item';
                let priceText = '';
                if (option.priceAdjustment > 0) {
                    priceText = ` (+€${option.priceAdjustment.toFixed(2)})`;
                } else if (option.priceAdjustment < 0) {
                     priceText = ` (-€${Math.abs(option.priceAdjustment).toFixed(2)})`;
                }
                button.innerHTML = `
                    <span class="font-medium text-gray-800">${option.label}</span>
                    <span class="text-gray-600">${priceText}</span>
                `;
                button.onclick = () => selectOption(option);
                container.appendChild(button);
            });

            modal.classList.add('active');
            backdrop.classList.add('active');
        }

        function closeOptionsModal() {
            document.getElementById('options-modal').classList.remove('active');
            document.getElementById('modal-backdrop').classList.remove('active');
            currentItemWithOptions = null;
        }
        
        function selectOption(option) {
            const baseItem = currentItemWithOptions;
            const finalPrice = baseItem.basePrice + option.priceAdjustment;
            const itemNameWithOptions = `${baseItem.name} (${option.label})`;

            addToOrder(itemNameWithOptions, finalPrice, baseItem.description);
            closeOptionsModal();
        }


        // Order functions
        function addToOrder(name, price, description) {
            if (!currentSeat) {
                alert("Please select your seat first!");
                return;
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
                    description: description || ""
                });
            }
            
            total += price;
            updateOrderDisplay();
            
            if (window.innerWidth < 1024 && !orderPanelOpen) {
                toggleOrderPanel();
            }
        }

        function handleItemClick(item) {
            if (item.options && item.options.length > 0) {
                showOptionsModal(item);
            } else {
                addToOrder(item.name, item.basePrice, item.description);
            }
        }

        function updateOrderDisplay() {
            const orderItemsContainer = document.getElementById('order-items');
            const mobileOrderItemsContainer = document.getElementById('mobile-order-items');
            
            if (orderItems.length === 0) {
                orderItemsContainer.innerHTML = '<p class="text-blue-500 text-center py-4 text-sm">No items added yet</p>';
                if (mobileOrderItemsContainer) mobileOrderItemsContainer.innerHTML = '<p class="text-blue-500 text-center py-4 text-sm">No items added yet</p>';
                document.getElementById('order-total').textContent = '€0.00';
                if (document.getElementById('mobile-order-total')) document.getElementById('mobile-order-total').textContent = '€0.00';
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
                                <button onclick="adjustQuantity(${index}, -1)" class="text-blue-400 hover:text-blue-600 px-2 py-1"><i class="fas fa-minus text-xs"></i></button>
                                <span class="text-blue-800 text-sm mx-1">${item.quantity}</span>
                                <button onclick="adjustQuantity(${index}, 1)" class="text-blue-400 hover:text-blue-600 px-2 py-1"><i class="fas fa-plus text-xs"></i></button>
                            </div>
                            <button onclick="editItemText(${index})" class="text-blue-400 hover:text-blue-600 text-sm ml-2"><i class="fas fa-edit"></i></button>
                            <button onclick="removeItem(${index})" class="text-red-400 hover:text-red-600 text-sm ml-2"><i class="fas fa-times"></i></button>
                        </div>
                    </div>
                `;
            });
            
            orderItemsContainer.innerHTML = itemsHTML;
            if (mobileOrderItemsContainer) mobileOrderItemsContainer.innerHTML = itemsHTML;
            document.getElementById('order-total').textContent = `€${total.toFixed(2)}`;
            if (document.getElementById('mobile-order-total')) document.getElementById('mobile-order-total').textContent = `€${total.toFixed(2)}`;
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
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(orderData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    orderItems = [];
                    total = 0;
                    
                    document.getElementById('order-notes').value = '';
                    if (mobileNotesEl) mobileNotesEl.value = '';

                    if (payByCardDesktopEl) payByCardDesktopEl.checked = false;
                    if (payByCardMobileEl) payByCardMobileEl.checked = false;

                    updateOrderDisplay();
                    if (window.innerWidth < 1024) toggleOrderPanel();
                } else {
                    alert('Printing failed: ' + (data.message || 'Unknown error'));
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Printing failed: ' + error.message);
            });
        }
        
        // --- MENU MANAGEMENT ---
        let currentEditItem = { category: null, index: -1, options: [] };
        
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

        // Category Management
        function renderManagementCategories() {
            const container = document.getElementById('management-categories-list');
            container.innerHTML = '';
            menuData.forEach((category, index) => {
                const div = document.createElement('div');
                div.className = 'flex justify-between items-center p-2 bg-gray-100 rounded';
                div.innerHTML = `
                    <div class="flex items-center">
                         <div class="flex flex-col mr-3">
                            <button onclick="reorderCategory('${category.name}', 'up')" class="text-gray-400 hover:text-gray-700 ${index === 0 ? 'invisible' : ''}"><i class="fas fa-angle-up text-xs"></i></button>
                            <button onclick="reorderCategory('${category.name}', 'down')" class="text-gray-400 hover:text-gray-700 ${index === menuData.length - 1 ? 'invisible' : ''}"><i class="fas fa-angle-down text-xs"></i></button>
                        </div>
                        <div class="w-4 h-4 rounded-full mr-3 ${category.color}"></div>
                        <span>${category.name}</span>
                    </div>
                    <div>
                        <button onclick="openCategoryEditModal('${category.name}')" class="text-blue-500 hover:text-blue-700 mr-2"><i class="fas fa-edit"></i></button>
                        <button onclick="deleteCategory('${category.name}')" class="text-red-500 hover:text-red-700"><i class="fas fa-trash"></i></button>
                    </div>`;
                container.appendChild(div);
            });
        }
        
        async function addCategory() {
            const newCategoryName = prompt("Enter new category name:");
            if (!newCategoryName) return;
            
            const defaultColor = Object.keys(colorOptions)[0];

            try {
                const response = await fetch('/api/menu/category', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: newCategoryName, color: defaultColor })
                });
                if (!response.ok) throw new Error((await response.json()).message || 'Failed to add category');
                await loadAndRenderAll();
            } catch (error) { alert('Error: ' + error.message); }
        }

        async function reorderCategory(categoryName, direction) {
            try {
                const response = await fetch('/api/menu/category/reorder', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ name: categoryName, direction: direction })
                });
                if (!response.ok) throw new Error((await response.json()).message || 'Failed to reorder');
                await loadAndRenderAll();
            } catch (error) {
                alert('Error reordering category: ' + error.message);
            }
        }
        
        // Category Edit Modal
        let currentEditingCategory = null;
        function openCategoryEditModal(categoryName) {
            currentEditingCategory = categoryName;
            const category = menuData.find(c => c.name === categoryName);
            if (!category) return;

            document.getElementById('category-edit-name-input').value = category.name;
            renderColorSwatches(category.color);
            
            document.getElementById('category-edit-modal').classList.add('active');
            document.getElementById('modal-backdrop').classList.add('active');
        }

        function closeCategoryEditModal() {
             document.getElementById('category-edit-modal').classList.remove('active');
             document.getElementById('modal-backdrop').classList.remove('active');
             currentEditingCategory = null;
        }

        function renderColorSwatches(selectedColorClass) {
            const container = document.getElementById('category-color-swatches');
            container.innerHTML = '';
            for (const colorClass in colorOptions) {
                const swatch = document.createElement('div');
                swatch.className = `color-swatch ${colorClass} ${selectedColorClass === colorClass ? 'selected' : ''}`;
                swatch.dataset.color = colorClass;
                swatch.title = colorOptions[colorClass];
                swatch.onclick = () => {
                    document.querySelectorAll('.color-swatch').forEach(s => s.classList.remove('selected'));
                    swatch.classList.add('selected');
                };
                container.appendChild(swatch);
            }
        }

        async function saveCategoryChanges() {
            const newName = document.getElementById('category-edit-name-input').value;
            const selectedSwatch = document.querySelector('.color-swatch.selected');
            if (!newName || !selectedSwatch) {
                alert('Please provide a name and select a color.');
                return;
            }
            const newColor = selectedSwatch.dataset.color;

            try {
                const response = await fetch(`/api/menu/category/${encodeURIComponent(currentEditingCategory)}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ new_name: newName, color: newColor })
                });
                if (!response.ok) throw new Error((await response.json()).message || 'Failed to update category');
                
                closeCategoryEditModal();
                await loadAndRenderAll();

            } catch (error) { alert('Error: ' + error.message); }
        }


        async function deleteCategory(categoryName) {
            if (!confirm(`Are you sure you want to delete the category "${categoryName}"? This will also delete all items within it.`)) return;
            try {
                const response = await fetch(`/api/menu/category/${encodeURIComponent(categoryName)}`, { method: 'DELETE' });
                if (!response.ok) throw new Error((await response.json()).message || 'Failed to delete category');
                await loadAndRenderAll();
                // If the deleted category was selected, select the first one
                if (!menuData.some(c => c.name === document.querySelector('.category-btn.active')?.dataset.category)) {
                    document.querySelector('.category-btn')?.click();
                }
            } catch (error) { alert('Error: ' + error.message); }
        }
        
        // Item Management & Options
        function renderManagementItems() {
            const container = document.getElementById('management-items-list');
            const categorySelect = document.getElementById('item-category-select');
            container.innerHTML = '';
            const selectedCategoryName = categorySelect.value;
            
            const currentSelection = categorySelect.value;
            categorySelect.innerHTML = '<option value="">-- Select Category --</option>';
            menuData.forEach(category => {
                const option = document.createElement('option');
                option.value = category.name;
                option.textContent = category.name;
                categorySelect.appendChild(option);
            });
            categorySelect.value = currentSelection;

            const selectedCategory = menuData.find(c => c.name === selectedCategoryName);
            if (selectedCategory && selectedCategory.items) {
                selectedCategory.items.forEach((item, index) => {
                    const div = document.createElement('div');
                    div.className = 'flex justify-between items-center p-2 bg-gray-100 rounded';
                    div.innerHTML = `
                        <span>${item.name} - €${item.basePrice.toFixed(2)}</span>
                        <div>
                            <button onclick="openItemEditModal('${selectedCategoryName}', ${index})" class="text-blue-500 hover:text-blue-700 mr-2"><i class="fas fa-edit"></i></button>
                            <button onclick="deleteItem('${selectedCategoryName}', ${index})" class="text-red-500 hover:text-red-700"><i class="fas fa-trash"></i></button>
                        </div>`;
                    container.appendChild(div);
                });
            }
        }
        
        function openItemEditModal(categoryName, index) {
            const modal = document.getElementById('item-edit-modal');
            const backdrop = document.getElementById('modal-backdrop');
            
            if (index === -1) { // Adding new item
                if (!categoryName) {
                    alert("Please select a category first.");
                    return;
                }
                document.getElementById('item-edit-title').textContent = 'Add New Item';
                document.getElementById('item-name-input').value = '';
                document.getElementById('item-price-input').value = '';
                document.getElementById('item-desc-input').value = '';
                document.getElementById('item-icon-input').value = '';
                currentEditItem = { category: categoryName, index: -1, options: [] };
            } else { // Editing existing item
                const category = menuData.find(c => c.name === categoryName);
                if (!category) return;
                const item = category.items[index];
                document.getElementById('item-edit-title').textContent = `Edit ${item.name}`;
                document.getElementById('item-name-input').value = item.name;
                document.getElementById('item-price-input').value = item.basePrice;
                document.getElementById('item-desc-input').value = item.description || '';
                document.getElementById('item-icon-input').value = item.icon || '';
                currentEditItem = { category: categoryName, index: index, options: JSON.parse(JSON.stringify(item.options || [])) };
            }
            
            renderItemOptionsEditor();
            modal.classList.add('active');
            backdrop.classList.add('active');
        }

        function closeItemEditModal() {
            document.getElementById('item-edit-modal').classList.remove('active');
            document.getElementById('modal-backdrop').classList.remove('active');
        }

        function renderItemOptionsEditor() {
            const container = document.getElementById('item-options-editor');
            container.innerHTML = '';
            currentEditItem.options.forEach((opt, i) => {
                container.innerHTML += `
                    <div class="flex items-center gap-2 mb-2 p-2 bg-gray-50 rounded">
                        <input type="text" value="${opt.label}" onchange="updateOption(${i}, 'label', this.value)" placeholder="Option Label" class="flex-grow p-1 border rounded">
                        <input type="number" value="${opt.priceAdjustment}" onchange="updateOption(${i}, 'priceAdjustment', this.value)" step="0.01" placeholder="Price +/-" class="w-24 p-1 border rounded">
                        <button onclick="removeOption(${i})" class="text-red-500 hover:text-red-700"><i class="fas fa-trash"></i></button>
                    </div>
                `;
            });
        }
        
        function addOption() {
            currentEditItem.options.push({ label: '', priceAdjustment: 0 });
            renderItemOptionsEditor();
        }

        function removeOption(index) {
            currentEditItem.options.splice(index, 1);
            renderItemOptionsEditor();
        }

        function updateOption(index, key, value) {
            if (key === 'priceAdjustment') {
                currentEditItem.options[index][key] = parseFloat(value) || 0;
            } else {
                currentEditItem.options[index][key] = value;
            }
        }
        
        async function saveItem() {
            const category = currentEditItem.category;
            const name = document.getElementById('item-name-input').value;
            const price = parseFloat(document.getElementById('item-price-input').value);
            if (!name || isNaN(price)) {
                alert("Item name and a valid price are required.");
                return;
            }

            const itemData = {
                category: category,
                name: name,
                description: document.getElementById('item-desc-input').value,
                price: price,
                icon: document.getElementById('item-icon-input').value,
                options: currentEditItem.options
            };
            
            let url = '/api/menu/item';
            let method = 'POST';
            if (currentEditItem.index > -1) {
                method = 'PUT';
                itemData.index = currentEditItem.index;
            }

            try {
                const response = await fetch(url, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(itemData)
                });
                if (!response.ok) throw new Error((await response.json()).message || 'Failed to save item');
                closeItemEditModal();
                await loadAndRenderAll();

            } catch (error) {
                console.error('Error saving item:', error);
                alert('Error: ' + error.message);
            }
        }

        async function deleteItem(categoryName, index) {
            const category = menuData.find(c => c.name === categoryName);
            if (!category) return;
            if (!confirm(`Are you sure you want to delete "${category.items[index].name}"?`)) return;

            try {
                const response = await fetch('/api/menu/item', {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ category: categoryName, index: index })
                });
                if (!response.ok) throw new Error((await response.json()).message || 'Failed to delete item');
                await loadAndRenderAll();
            } catch (error) { alert('Error: ' + error.message); }
        }
        
        // --- DATA LOADING AND RENDERING ---
        
        async function loadAndRenderAll() {
            await loadMenuData();
            renderCategoryTabs();
            renderMenu();
            // Also re-render management views if they are open
            if(document.getElementById('management-modal').classList.contains('active')) {
                renderManagementCategories();
                renderManagementItems();
            }
        }
        
        function renderMenu() {
            const menuContainer = document.getElementById('menu-items');
            menuContainer.innerHTML = '';

            menuData.forEach(category => {
                const categoryDiv = document.createElement('div');
                categoryDiv.className = 'category-content hidden';
                categoryDiv.id = category.name;
                
                const itemsGrid = document.createElement('div');
                itemsGrid.className = 'grid grid-cols-1 gap-1';

                category.items.forEach(item => {
                    const itemButton = document.createElement('button');
                    itemButton.className = 'flex justify-between items-center p-2 bg-blue-50 hover:bg-blue-100 rounded-lg transition text-left w-full';
                    const hasOptions = item.options && item.options.length > 0;
                    itemButton.innerHTML = `
                        <div class="flex items-center truncate">
                            ${item.icon ? `<i class="${item.icon} mr-2 text-blue-500"></i>` : ''}
                            <div class="truncate">
                                <h4 class="font-medium text-blue-800 text-sm truncate">${item.name}</h4>
                                <p class="text-xs text-blue-600 truncate">${item.description || ''}</p>
                            </div>
                        </div>
                        <div class="flex items-center">
                          <span class="font-bold text-blue-700 text-sm ml-2">€${item.basePrice.toFixed(2)}</span>
                          ${hasOptions ? '<i class="fas fa-ellipsis-v ml-3 text-blue-400"></i>' : ''}
                        </div>
                    `;
                    
                    itemButton.onclick = () => handleItemClick(item);
                    itemsGrid.appendChild(itemButton);
                });

                categoryDiv.appendChild(itemsGrid);
                menuContainer.appendChild(categoryDiv);
            });
        }
        
        function renderCategoryTabs() {
            const container = document.getElementById('category-tabs-container');
            container.innerHTML = '';
            menuData.forEach(category => {
                const button = document.createElement('button');
                button.onclick = function() { selectCategory(category.name, this) };
                button.className = `category-btn px-3 py-3 rounded-lg ${category.color} text-blue-800 font-medium whitespace-nowrap text-sm border-2 border-transparent`;
                button.innerHTML = `<i class="fas fa-tag mr-2"></i>${category.name}`;
                container.appendChild(button);
            });
        }
        
        // Load menu data from server
        async function loadMenuData() {
            try {
                const response = await fetch('/api/menu');
                if (!response.ok) throw new Error('Failed to load menu data');
                menuData = await response.json();
            } catch (error) {
                console.error('Error loading menu:', error);
                alert('Failed to load menu. Please try again.');
            }
        }
        
        // Initialize
        window.onload = async function() {
            await loadMenuData();
            
            generateSeatMap('A');
            document.querySelector('[data-row="A"]').classList.add('bg-blue-100', 'font-medium');
            renderCategoryTabs();
            renderMenu();

            // Auto-select first category if available
            const firstCategoryButton = document.querySelector('#category-tabs-container .category-btn');
            if (firstCategoryButton) {
                firstCategoryButton.click();
            }
            
            const fab = document.createElement('button');
            fab.id = 'fab-order-toggle';
            fab.className = 'fixed bottom-4 right-4 bg-blue-500 text-white w-14 h-14 rounded-full shadow-lg z-50 lg:hidden flex items-center justify-center';
            fab.innerHTML = '<i class="fas fa-receipt text-xl"></i>';
            fab.onclick = toggleOrderPanel;
            document.body.appendChild(fab);
        };

    </script>
</head>
<body class="bg-gradient-to-b from-blue-50 to-blue-100 min-h-screen">
    <div class="fixed top-4 right-4 z-50">
        <button onclick="openManagementModal()" class="bg-gray-700 text-white w-12 h-12 rounded-full shadow-lg flex items-center justify-center hover:bg-gray-800 transition">
            <i class="fas fa-cog text-xl"></i>
        </button>
    </div>

    <!-- Universal Modal Backdrop -->
    <div id="modal-backdrop" class="modal-backdrop" onclick="closeManagementModal(); closeItemEditModal(); closeOptionsModal(); closeCategoryEditModal();"></div>
    
    <!-- Management Modal -->
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
                <div class="flex justify-between items-center mb-4"><h3 class="font-semibold text-gray-700">Categories</h3><button onclick="addCategory()" class="bg-blue-500 text-white px-3 py-1 rounded-md text-sm hover:bg-blue-600">Add New</button></div>
                <div id="management-categories-list" class="space-y-2"></div>
            </div>
            <div id="item-management-view" class="hidden">
                 <div class="flex justify-between items-center mb-4">
                    <h3 class="font-semibold text-gray-700">Items</h3>
                    <button onclick="openItemEditModal(document.getElementById('item-category-select').value, -1)" class="bg-green-500 text-white px-3 py-1 rounded-md text-sm hover:bg-green-600 disabled:opacity-50" id="add-new-item-btn">Add New</button>
                </div>
                <div class="mb-4">
                    <label for="item-category-select" class="block text-sm font-medium text-gray-700 mb-1">Category:</label>
                    <select id="item-category-select" onchange="renderManagementItems()" class="w-full p-2 border border-gray-300 rounded-md"></select>
                </div>
                <div id="management-items-list" class="space-y-2 max-h-64 overflow-y-auto"></div>
            </div>
        </div>
        <div class="p-4 bg-gray-50 border-t text-right"><button onclick="closeManagementModal()" class="bg-gray-500 text-white px-4 py-2 rounded-md hover:bg-gray-600">Close</button></div>
    </div>
    
    <!-- Category Edit Modal -->
    <div id="category-edit-modal" class="modal bg-white rounded-xl shadow-2xl w-full max-w-md">
        <div class="p-4 border-b"><h2 class="text-lg font-semibold text-gray-800">Edit Category</h2></div>
        <div class="p-6 space-y-4">
            <div>
                <label for="category-edit-name-input" class="block text-sm font-medium text-gray-700">Category Name</label>
                <input id="category-edit-name-input" type="text" class="mt-1 w-full p-2 border rounded-md">
            </div>
            <div>
                <label class="block text-sm font-medium text-gray-700">Color</label>
                <div id="category-color-swatches" class="mt-2 grid grid-cols-7 gap-2">
                    <!-- Color swatches will be rendered here -->
                </div>
            </div>
        </div>
        <div class="p-4 bg-gray-50 border-t flex justify-end gap-3">
            <button onclick="closeCategoryEditModal()" class="bg-gray-300 text-gray-800 px-4 py-2 rounded-md hover:bg-gray-400">Cancel</button>
            <button onclick="saveCategoryChanges()" class="bg-blue-500 text-white px-4 py-2 rounded-md hover:bg-blue-600">Save Changes</button>
        </div>
    </div>


    <!-- Item Edit Modal -->
    <div id="item-edit-modal" class="modal bg-white rounded-xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col">
        <div class="p-4 border-b"><h2 id="item-edit-title" class="text-lg font-semibold text-gray-800">Edit Item</h2></div>
        <div class="p-6 overflow-y-auto flex-grow space-y-4">
            <div><label class="block text-sm font-medium">Name</label><input id="item-name-input" type="text" class="w-full p-2 border rounded"></div>
            <div><label class="block text-sm font-medium">Base Price (€)</label><input id="item-price-input" type="number" step="0.01" class="w-full p-2 border rounded"></div>
            <div><label class="block text-sm font-medium">Description</label><input id="item-desc-input" type="text" class="w-full p-2 border rounded"></div>
            <div><label class="block text-sm font-medium">Icon (e.g., 'fas fa-coffee')</label><input id="item-icon-input" type="text" class="w-full p-2 border rounded"></div>
            
            <div class="border-t pt-4">
                <div class="flex justify-between items-center mb-2">
                    <h3 class="font-semibold text-gray-700">Item Options</h3>
                    <button onclick="addOption()" class="bg-blue-500 text-white px-3 py-1 text-sm rounded hover:bg-blue-600">Add Option</button>
                </div>
                <div id="item-options-editor" class="space-y-2 max-h-40 overflow-y-auto"></div>
            </div>
        </div>
        <div class="p-4 bg-gray-50 border-t flex justify-end gap-3">
            <button onclick="closeItemEditModal()" class="bg-gray-300 text-gray-800 px-4 py-2 rounded hover:bg-gray-400">Cancel</button>
            <button onclick="saveItem()" class="bg-green-500 text-white px-4 py-2 rounded hover:bg-green-600">Save Item</button>
        </div>
    </div>

    <!-- Options Modal (for ordering) -->
    <div id="options-modal" class="modal bg-white rounded-xl shadow-2xl w-full max-w-sm">
        <div class="p-4 border-b flex justify-between items-center">
             <h2 id="options-modal-title" class="text-lg font-semibold text-gray-800">Choose Option</h2>
             <button onclick="closeOptionsModal()" class="text-gray-500 hover:text-gray-800 text-2xl">&times;</button>
        </div>
        <div id="options-modal-list" class="p-4"></div>
    </div>

    <div id="order-panel-backdrop" class="order-panel-backdrop lg:hidden" onclick="toggleOrderPanel()"></div>
    
    <div class="container mx-auto px-2 py-4">
        <div class="flex items-center justify-between mb-4 px-2">
            <div class="flex items-center">
                <i class="fas fa-umbrella-beach text-2xl text-amber-500 mr-2"></i>
                <h1 class="text-xl font-bold text-blue-800">Beach Bar</h1>
            </div>
            <div id="mobile-seat-display" class="bg-blue-100 px-3 py-1 rounded-full text-sm font-medium text-blue-700">
                <i class="fas fa-chair mr-1"></i><span>No seat</span>
            </div>
        </div>
        <div class="grid lg:grid-cols-2 gap-4">
            <div class="space-y-4">
                <div class="bg-white rounded-xl shadow-md p-4 border border-blue-200">
                    <h2 class="text-lg font-semibold text-blue-800 mb-3 flex items-center"><i class="fas fa-map-marker-alt text-blue-500 mr-2"></i>Select Your Seat</h2>
                    <div class="mb-4">
                        <div class="flex flex-wrap gap-2 mb-2">
                            <button onclick="selectRow('A')" class="row-btn py-2 px-6 text-xl bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition" data-row="A">Row A</button>
                            <button onclick="selectRow('B')" class="row-btn py-2 px-6 text-xl bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition" data-row="B">Row B</button>
                            <button onclick="selectRow('C')" class="row-btn py-2 px-6 text-xl bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition" data-row="C">Row C</button>
                            <button onclick="selectRow('D')" class="row-btn py-2 px-6 text-xl bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition" data-row="D">Row D</button>
                            <button onclick="selectRow('EXTRA')" class="row-btn py-2 px-6 text-xl bg-blue-50 text-blue-800 rounded-lg hover:bg-blue-100 transition" data-row="EXTRA">EXTRA</button>
                        </div>
                    </div>
                    <div class="mb-4">
                        <h3 class="text-xs font-medium text-blue-700 mb-2">Available Seats</h3>
                        <div id="seat-map" class="grid grid-cols-5 gap-2"></div>
                    </div>
                    <div id="selected-seat-display" class="bg-blue-50 p-3 rounded-lg border border-blue-200 flex items-center"><div class="mr-3 text-xl text-blue-600"><i class="fas fa-chair"></i></div><div><p class="text-blue-500 text-xs">Your seat</p><p id="selected-seat" class="font-medium text-blue-800">Not selected</p></div></div>
                </div>
                <div class="bg-white rounded-xl shadow-md p-4 border border-blue-200">
                    <h2 class="text-lg font-semibold text-blue-800 mb-3 flex items-center"><i class="fas fa-concierge-bell text-blue-500 mr-2"></i>Menu</h2>
                    <div id="category-tabs-container" class="mb-4 flex flex-wrap gap-2"></div>
                    <div id="menu-items" class="mb-4 max-h-[60vh] overflow-y-auto pr-1"></div>
                </div>
            </div>
            <div class="hidden lg:block lg:sticky lg:top-4 h-fit">
                <div class="bg-white rounded-xl shadow-lg p-4 border border-blue-200 h-[calc(100vh-140px)] flex flex-col">
                    <div class="flex-1 overflow-hidden flex flex-col">
                        <div class="flex justify-between items-center mb-3"><h3 class="text-sm font-semibold text-blue-800"><i class="fas fa-receipt mr-2"></i>Your Order</h3><button onclick="clearOrder()" class="text-red-500 hover:text-red-700 text-sm"><i class="fas fa-trash-alt mr-1"></i>Clear</button></div>
                        <div id="order-items" class="flex-1 overflow-y-auto space-y-2 pr-2"><p class="text-blue-500 text-center py-4 text-sm">No items added yet</p></div>
                        <div class="mt-2 flex justify-between items-center bg-blue-100 px-3 py-2 rounded-lg"><span class="font-medium text-blue-800 text-sm flex items-center"><i class="fas fa-coins mr-1"></i> Total:</span><span id="order-total" class="font-bold text-blue-700 text-sm">€0</span></div>
                    </div>
                    <div class="mb-2">
                        <label for="order-notes" class="block text-xs font-medium text-blue-700 mb-1 flex items-center"><i class="fas fa-sticky-note mr-1"></i> Special Instructions</label>
                        <textarea id="order-notes" rows="2" class="w-full px-3 py-2 border border-blue-200 rounded-lg focus:ring-1 focus:ring-blue-300 focus:border-blue-300 text-sm" placeholder="Allergies? Modifications?"></textarea>
                    </div>
                    <div class="flex items-center justify-center my-3"><input id="pay-by-card" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"><label for="pay-by-card" class="ml-2 block text-sm font-medium text-blue-800">Pay by Card</label></div>
                    <button id="submit-order" onclick="submitOrder()" class="w-full py-3 bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white font-medium rounded-lg shadow-md transition disabled:opacity-50 disabled:cursor-not-allowed text-sm"><i class="fas fa-paper-plane mr-1"></i> Send Order</button>
                </div>
            </div>
        </div>
    </div>
    <div id="order-panel-mobile" class="order-panel-mobile lg:hidden bg-white p-4 overflow-y-auto">
        <div class="flex justify-between items-center mb-3"><h3 class="text-sm font-semibold text-blue-800"><i class="fas fa-receipt mr-2"></i>Your Order</h3><button onclick="toggleOrderPanel()" class="text-gray-500 hover:text-gray-700 text-sm"><i class="fas fa-times"></i></button></div>
        <div id="mobile-order-items" class="flex-1 overflow-y-auto space-y-2 pr-2 mb-4"><p class="text-blue-500 text-center py-4 text-sm">No items added yet</p></div>
        <div class="mt-2 flex justify-between items-center bg-blue-100 px-3 py-2 rounded-lg mb-4"><span class="font-medium text-blue-800 text-sm flex items-center"><i class="fas fa-coins mr-1"></i> Total:</span><span id="mobile-order-total" class="font-bold text-blue-700 text-sm">€0</span></div>
        <div class="mb-2"><label for="mobile-order-notes" class="block text-xs font-medium text-blue-700 mb-1 flex items-center"><i class="fas fa-sticky-note mr-1"></i> Special Instructions</label><textarea id="mobile-order-notes" rows="2" class="w-full px-3 py-2 border border-blue-200 rounded-lg text-sm" placeholder="Allergies? Modifications?"></textarea></div>
        <div class="flex items-center justify-center my-3"><input id="mobile-pay-by-card" type="checkbox" class="h-4 w-4 rounded border-gray-300"><label for="mobile-pay-by-card" class="ml-2 block text-sm font-medium text-blue-800">Pay by Card</label></div>
        <button onclick="submitOrder()" class="w-full py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-medium rounded-lg shadow-md text-sm"><i class="fas fa-paper-plane mr-1"></i> Send Order</button>
    </div>
</body>
</html>
'''

def encode_escpos(text):
    # Standard ESC/POS euro sign for code page 858
    return text.replace("€", "\xD5").encode('cp858', errors='replace')

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
    if any(c['name'] == name for c in menu_data):
        return jsonify({'status': 'error', 'message': 'Category already exists'}), 400
    
    menu_data.append({'name': name, 'color': color, 'items': []})
    save_menu_data(menu_data)
    return jsonify({'status': 'success'})

@app.route('/api/menu/category/<name>', methods=['PUT'])
def api_update_category(name):
    data = request.json
    new_name = data.get('new_name')
    color = data.get('color')
    menu_data = get_menu_data()
    
    cat_to_update = next((c for c in menu_data if c['name'] == name), None)
    if not cat_to_update:
        return jsonify({'status': 'error', 'message': 'Category not found'}), 404
        
    if new_name and new_name != name and any(c['name'] == new_name for c in menu_data):
        return jsonify({'status': 'error', 'message': 'New category name already exists'}), 400
    
    if new_name:
        cat_to_update['name'] = new_name
    if color:
        cat_to_update['color'] = color

    save_menu_data(menu_data)
    return jsonify({'status': 'success'})

@app.route('/api/menu/category/<name>', methods=['DELETE'])
def api_delete_category(name):
    menu_data = get_menu_data()
    
    initial_len = len(menu_data)
    menu_data = [c for c in menu_data if c['name'] != name]
    
    if len(menu_data) == initial_len:
        return jsonify({'status': 'error', 'message': 'Category not found'}), 404
        
    save_menu_data(menu_data)
    return jsonify({'status': 'success'})

@app.route('/api/menu/category/reorder', methods=['POST'])
def api_reorder_category():
    data = request.json
    name = data.get('name')
    direction = data.get('direction')
    
    menu_data = get_menu_data()
    
    try:
        index = next(i for i, c in enumerate(menu_data) if c['name'] == name)
    except StopIteration:
        return jsonify({'status': 'error', 'message': 'Category not found'}), 404

    if direction == 'up' and index > 0:
        menu_data.insert(index - 1, menu_data.pop(index))
    elif direction == 'down' and index < len(menu_data) - 1:
        menu_data.insert(index + 1, menu_data.pop(index))
    else:
        return jsonify({'status': 'error', 'message': 'Invalid move'}), 400

    save_menu_data(menu_data)
    return jsonify({'status': 'success'})

@app.route('/api/menu/item', methods=['POST'])
def api_add_item():
    data = request.json
    category_name = data.get('category')
    menu_data = get_menu_data()
    
    category = next((c for c in menu_data if c['name'] == category_name), None)
    if not category:
        return jsonify({'status': 'error', 'message': 'Category not found'}), 404
    
    new_item = {
        'name': data.get('name'),
        'description': data.get('description'),
        'basePrice': data.get('price'),
        'icon': data.get('icon'),
        'options': data.get('options', [])
    }
    category['items'].append(new_item)
    save_menu_data(menu_data)
    return jsonify({'status': 'success'})

@app.route('/api/menu/item', methods=['PUT'])
def api_update_item():
    data = request.json
    category_name = data.get('category')
    index = data.get('index')
    menu_data = get_menu_data()
    
    category = next((c for c in menu_data if c['name'] == category_name), None)
    if not category or not isinstance(index, int):
        return jsonify({'status': 'error', 'message': 'Invalid category or item index'}), 400
    
    items = category['items']
    if index < 0 or index >= len(items):
        return jsonify({'status': 'error', 'message': 'Item index out of bounds'}), 400
    
    items[index] = {
        'name': data.get('name'),
        'description': data.get('description'),
        'basePrice': data.get('price'),
        'icon': data.get('icon'),
        'options': data.get('options', [])
    }
    save_menu_data(menu_data)
    return jsonify({'status': 'success'})

@app.route('/api/menu/item', methods=['DELETE'])
def api_delete_item():
    data = request.json
    category_name = data.get('category')
    index = data.get('index')
    menu_data = get_menu_data()
    
    category = next((c for c in menu_data if c['name'] == category_name), None)
    if not category or not isinstance(index, int):
        return jsonify({'status': 'error', 'message': 'Invalid category or item index'}), 400
    
    items = category['items']
    if index < 0 or index >= len(items):
        return jsonify({'status': 'error', 'message': 'Item index out of bounds'}), 400
    
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
        SMALL = ESC + b'!\x01' # Using small font for descriptions
        SET_CP_858 = ESC + b'\x74\x13' # Code Page 858 for euro symbol

        pure_text = "PURE"
        spacing = 32 - len(pure_text) - len(seat)

        receipt_lines = [
            SET_CP_858,
            encode_escpos(pure_text + ' ' * spacing),
            BOLD_LARGE + encode_escpos(seat) + RESET,
            encode_escpos("\n" + "="*32),
            encode_escpos(f"\nTime: {datetime.now().strftime('%d-%m-%Y %H:%M:%S')}"),
            encode_escpos("\n\nITEMS:\n------")
        ]

        for item in order_data['items']:
            qty = item.get('quantity', 1)
            line = f"\n{qty}x {item['name']}"
            
            if item.get('customText'):
                line += f" [{item['customText']}]"
            
            price_str = f"EUR{item['price'] * qty:.2f}"
            line_spacing = 32 - len(line) - len(price_str)
            line += ' ' * line_spacing + price_str

            receipt_lines.append(encode_escpos(line))

        payment_text = "CARD" if pay_by_card else "CASH"
        total_str = f"TOTAL: EUR{order_data['total']:.2f}"
        
        receipt_lines.extend([
            encode_escpos("\n\n" + "-"*32),
            BOLD + encode_escpos("\n" + ' ' * (32 - len(total_str)) + total_str) + RESET,
            encode_escpos(f"\n\nPAYMENT: {payment_text}"),
        ])

        if order_data.get('notes'):
            receipt_lines.append(encode_escpos(f"\n\nNotes: {order_data.get('notes')}"))

        receipt_lines.extend([
            encode_escpos("\n" + "="*32),
            encode_escpos("\nThank you!\n")
        ])

        data = b"".join(receipt_lines) + (LINE_FEED * 3) + CUT_PAPER

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((PRINTER_IP, PRINTER_PORT))
            s.sendall(data)

        return jsonify({'status': 'success'})

    except socket.timeout:
        return jsonify({'status': 'error', 'message': f'Connection to printer ({PRINTER_IP}) timed out.'}), 500
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    ensure_menu_file_has_order() # Check/update menu file on startup
    app.run(host='0.0.0.0', port=5000, debug=True)
