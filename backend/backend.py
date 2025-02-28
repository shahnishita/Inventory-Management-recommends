from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import psycopg2
import os
from docx import Document
import google.generativeai as genai
from dotenv import load_dotenv

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# ✅ Define and set UPLOAD_FOLDER correctly (Using /tmp for Vercel compatibility)
UPLOAD_FOLDER = "/tmp/recommendations"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)  # Ensure the folder exists
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ✅ Load environment variables
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # Read from .env
genai.configure(api_key=GEMINI_API_KEY)

# ✅ Connect to PostgreSQL database
try:
    conn = psycopg2.connect(
        database="postgres",
        user="postgres",
        password="nishu*2003",
        host="localhost",
        port="5432"
    )
    conn.autocommit = True  # Automatically commit changes
except Exception as e:
    print(f"Database connection error: {e}")

# ✅ Route to get all products
@app.route('/products', methods=['GET'])
def get_products():
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT product_id, name, price, category FROM Product;")
            products = cursor.fetchall()
        return jsonify([{"product_id": p[0], "name": p[1], "price": p[2], "category": p[3]} for p in products])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ Route to get all customers
@app.route('/customers', methods=['GET'])
def get_customers():
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT customer_id, name, email, location FROM Customer;")
            customers = cursor.fetchall()
        return jsonify([{"customer_id": c[0], "name": c[1], "email": c[2], "location": c[3]} for c in customers])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ Add a new customer
@app.route('/add-customer', methods=['POST'])
def add_customer():
    data = request.json
    name, email, location = data.get("name"), data.get("email"), data.get("location")

    if not name or not email or not location:
        return jsonify({"error": "All fields are required"}), 400

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO Customer (name, email, location) VALUES (%s, %s, %s) RETURNING customer_id;",
                (name, email, location)
            )
            customer_id = cursor.fetchone()[0]
        return jsonify({"message": "Customer added successfully!", "customer_id": customer_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ Get all orders
@app.route('/orders', methods=['GET'])
def get_orders():
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT o.order_id, c.name AS customer_name, p.name AS product_name, o.quantity, o.order_date
                FROM ordertable o
                JOIN Customer c ON o.customer_id = c.customer_id
                JOIN Product p ON o.product_id = p.product_id;
            """)
            orders = cursor.fetchall()
        return jsonify([
            {"order_id": o[0], "customer_name": o[1], "product_name": o[2], "quantity": o[3], "order_date": o[4]}
            for o in orders
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ Place an order
@app.route('/place-order', methods=['POST'])
def place_order():
    data = request.json
    customer_id, product_id, quantity = data.get("customer_id"), data.get("product_id"), data.get("quantity")

    if not customer_id or not product_id or not quantity:
        return jsonify({"error": "All fields are required"}), 400

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO ordertable (customer_id, product_id, quantity, order_date) VALUES (%s, %s, %s, NOW()) RETURNING order_id;",
                (customer_id, product_id, quantity)
            )
            order_id = cursor.fetchone()[0]
        return jsonify({"message": "Order placed successfully!", "order_id": order_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ Add a product
@app.route('/add-product', methods=['POST'])
def add_product():
    data = request.json
    name, price, category = data.get("name"), data.get("price"), data.get("category")

    if not name or not price or not category:
        return jsonify({"error": "All fields are required"}), 400

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO Product (name, price, category) VALUES (%s, %s, %s) RETURNING product_id;",
                (name, price, category)
            )
            product_id = cursor.fetchone()[0]
        return jsonify({"message": "Product added successfully!", "product_id": product_id}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ Fetch customer's purchase history
@app.route('/purchase-history/<int:customer_id>', methods=['GET'])
def get_purchase_history(customer_id):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT p.name, p.price, o.quantity, o.order_date
                FROM ordertable o
                JOIN Product p ON o.product_id = p.product_id
                WHERE o.customer_id = %s;
            """, (customer_id,))
            history = cursor.fetchall()
        return jsonify(history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ Generate product recommendations
@app.route('/recommendations/<int:customer_id>', methods=['GET'])
def recommendations(customer_id):
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT p.name FROM ordertable o
                JOIN Product p ON o.product_id = p.product_id
                WHERE o.customer_id = %s;
            """, (customer_id,))
            history = [row[0] for row in cursor.fetchall()]

        if not history:
            return jsonify({"error": "No purchase history found"}), 404

        prompt = f"Recommend 3 products based on: {', '.join(history)}."
        model = genai.GenerativeModel("gemini-1.5-pro")
        response = model.generate_content(prompt)
        recommendations = response.text if response.text else "No recommendations available."

        return jsonify({"customer_id": customer_id, "recommendations": recommendations})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ✅ File Upload Route (Updated for Vercel)
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)

    return jsonify({'message': 'File uploaded successfully', 'file_path': file_path})

# ✅ Run Flask app
if __name__ == '__main__':
    app.run(debug=True)
