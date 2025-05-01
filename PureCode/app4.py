from flask import Flask, request, redirect, render_template_string, session
import socket
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Required for session handling

# Printer configuration
PRINTER_IP = '192.168.2.218'
PRINTER_PORT = 9100

# ESC/POS commands
CUT_PAPER = b'\x1D\x56\x00'  # Full cut command
LINE_FEED = b'\n'

# Sample menu - customize with your actual items and prices
MENU_ITEMS = {
    "COCKTAILS": {
        "Mojito": 12,
        "Pina Colada": 14,  # Removed ñ for ASCII compatibility
        "Daiquiri": 13,
    },
    "SNACKS": {
        "Fish Tacos": 9,
        "Ceviche": 11,
        "Nachos": 8,
    },
    "DESSERTS": {
        "Churros": 6,
        "Flan": 5,
        "Ice Cream": 4,
    }
}

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Beach Bar Orders</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: #f0f8ff; }
        .beach-header { background: #87CEEB; padding: 20px; }
        .order-card { border: 2px solid #4682B4; margin: 10px; }
        .btn-beach { background: #4682B4; color: white; }
        .btn-danger-beach { background: #dc3545; color: white; }
        .table-number { font-size: 1.5rem; font-weight: bold; color: #2F4F4F; }
        .item-row { border-bottom: 1px solid #dee2e6; padding: 8px 0; }
        .quantity-controls { display: flex; align-items: center; gap: 5px; }
    </style>
</head>
<body>
    <div class="beach-header text-center">
        <h1>🏖️ Beach Bar Orders 🍹</h1>
        <div class="table-number">Table: {{ table_number or "Not selected" }}</div>
    </div>

    <div class="container mt-4">
        <!-- Table Selection -->
        <div class="row mb-4">
            <div class="col-12">
                <form action="/set_table" method="post" class="row g-2">
                    <div class="col-md-8">
                        <select name="table_number" class="form-select">
                            <option value="">Select Table</option>
                            {% for n in range(1, 21) %}
                            <option value="{{ n }}" {% if n == table_number %}selected{% endif %}>Table {{ n }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="col-md-4">
                        <button type="submit" class="btn btn-beach w-100">Set Table</button>
                    </div>
                </form>
            </div>
        </div>

        <!-- Menu Items -->
        <div class="row">
            {% for category, items in MENU_ITEMS.items() %}
            <div class="col-md-4 mb-4">
                <div class="card order-card">
                    <div class="card-header bg-primary text-white">{{ category }}</div>
                    <div class="card-body">
                        {% for item, price in items.items() %}
                        <form action="/add_item" method="post" class="mb-2">
                            <input type="hidden" name="table_number" value="{{ table_number }}">
                            <input type="hidden" name="item" value="{{ item }}">
                            <input type="hidden" name="price" value="{{ price }}">
                            <div class="d-flex justify-content-between align-items-center">
                                <div>
                                    {{ item }}<br>
                                    <small>${{ price }}</small>
                                </div>
                                <button type="submit" class="btn btn-beach">+ Add</button>
                            </div>
                        </form>
                        {% endfor %}
                    </div>
                </div>
            </div>
            {% endfor %}
        </div>

        <!-- Order Summary -->
        {% if order_items %}
        <div class="row mt-4">
            <div class="col-12">
                <div class="card order-card">
                    <div class="card-header bg-success text-white">
                        Current Order (Total: ${{ "%.2f"|format(total) }})
                    </div>
                    <div class="card-body">
                        {% for item in order_items %}
                        <div class="item-row d-flex justify-content-between align-items-center">
                            <div>{{ item.name }} - ${{ "%.2f"|format(item.price) }}</div>
                            <div class="quantity-controls">
                                <form action="/decrease_item" method="post" style="display:inline;">
                                    <input type="hidden" name="item_id" value="{{ loop.index0 }}">
                                    <input type="hidden" name="table_number" value="{{ table_number }}">
                                    <button type="submit" class="btn btn-sm btn-beach">-</button>
                                </form>
                                <span>x{{ item.quantity }}</span>
                                <form action="/increase_item" method="post" style="display:inline;">
                                    <input type="hidden" name="item_id" value="{{ loop.index0 }}">
                                    <input type="hidden" name="table_number" value="{{ table_number }}">
                                    <button type="submit" class="btn btn-sm btn-beach">+</button>
                                </form>
                                <form action="/remove_item" method="post" style="display:inline;">
                                    <input type="hidden" name="item_id" value="{{ loop.index0 }}">
                                    <input type="hidden" name="table_number" value="{{ table_number }}">
                                    <button type="submit" class="btn btn-sm btn-danger-beach">×</button>
                                </form>
                            </div>
                        </div>
                        {% endfor %}
                    </div>
                    <div class="card-footer">
                        <form action="/print" method="post">
                            <input type="hidden" name="table_number" value="{{ table_number }}">
                            <textarea name="receipt" hidden>{{ receipt_content }}</textarea>
                            <button type="submit" class="btn btn-beach w-100">🖨️ Print Receipt</button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
        {% endif %}
    </div>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE,
                                MENU_ITEMS=MENU_ITEMS,
                                table_number=session.get('table_number'),
                                order_items=session.get('order_items', []),
                                total=session.get('total', 0),
                                receipt_content=session.get('receipt_content', ''))

@app.route('/set_table', methods=['POST'])
def set_table():
    session['table_number'] = int(request.form['table_number']) if request.form['table_number'] else None
    session.pop('order_items', None)
    session.pop('total', None)
    return redirect('/')

@app.route('/add_item', methods=['POST'])
def add_item():
    if not session.get('table_number'):
        return redirect('/')
    
    item = request.form['item']
    price = float(request.form['price'])
    
    # Update order items
    order_items = session.get('order_items', [])
    existing = next((i for i in order_items if i['name'] == item), None)
    
    if existing:
        existing['quantity'] += 1
        existing['total'] += price
    else:
        order_items.append({
            'name': item,
            'price': price,
            'quantity': 1,
            'total': price
        })
    
    session['order_items'] = order_items
    session['total'] = sum(item['total'] for item in order_items)
    return redirect('/')

@app.route('/increase_item', methods=['POST'])
def increase_item():
    if not session.get('table_number'):
        return redirect('/')
    
    item_id = int(request.form['item_id'])
    order_items = session.get('order_items', [])
    
    if 0 <= item_id < len(order_items):
        item = order_items[item_id]
        item['quantity'] += 1
        item['total'] += item['price']
    
    session['order_items'] = order_items
    session['total'] = sum(item['total'] for item in order_items)
    return redirect('/')

@app.route('/decrease_item', methods=['POST'])
def decrease_item():
    if not session.get('table_number'):
        return redirect('/')
    
    item_id = int(request.form['item_id'])
    order_items = session.get('order_items', [])
    
    if 0 <= item_id < len(order_items):
        item = order_items[item_id]
        if item['quantity'] > 1:
            item['quantity'] -= 1
            item['total'] -= item['price']
        else:
            order_items.pop(item_id)
    
    session['order_items'] = order_items
    session['total'] = sum(item['total'] for item in order_items)
    return redirect('/')

@app.route('/remove_item', methods=['POST'])
def remove_item():
    if not session.get('table_number'):
        return redirect('/')
    
    item_id = int(request.form['item_id'])
    order_items = session.get('order_items', [])
    
    if 0 <= item_id < len(order_items):
        order_items.pop(item_id)
    
    session['order_items'] = order_items
    session['total'] = sum(item['total'] for item in order_items)
    return redirect('/')

@app.route('/print', methods=['POST'])
def print_receipt():
    table_number = request.form['table_number']
    order_items = session.get('order_items', [])
    
    # Generate receipt content
    receipt_lines = [
        "BEACH BAR RECEIPT",
        "=================",
        f"Table: {table_number}",
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "ITEMS:",
        "------"
    ]
    
    for item in order_items:
        receipt_lines.append(f"{item['name']} x{item['quantity']} @ ${item['price']:.2f} = ${item['total']:.2f}")
    
    receipt_lines += [
        "",
        "-----------------",
        f"TOTAL: ${session.get('total', 0):.2f}",
        "",
        "Thank you for your order!",
        "Enjoy the beach!"
    ]
    
    # Convert to printable format
    receipt_content = "\n".join(receipt_lines)
    
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            s.connect((PRINTER_IP, PRINTER_PORT))
            
            # Send content with proper line feeds and cut command
            s.sendall(receipt_content.encode('utf-8'))
            s.sendall(LINE_FEED * 3)
            s.sendall(CUT_PAPER)
            
    except Exception as e:
        print(f"Print error: {e}")
    
    # Clear session after printing
    session.pop('order_items', None)
    session.pop('total', None)
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)