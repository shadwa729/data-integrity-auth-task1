from flask import Flask, request, jsonify
import pymysql
import bcrypt
import pyotp
import qrcode
from io import BytesIO
import base64
from flask_jwt_extended import JWTManager, create_access_token, jwt_required
from datetime import timedelta

app = Flask(__name__)

# ------------------ DATABASE CONNECTION ------------------
db = pymysql.connect(
    host="localhost",
    user="root",  
    password="",  
    database="auth_db"
)
cursor = db.cursor()

# ------------------ JWT CONFIGURATION (TOKEN EXPIRES IN 10 MINUTES) ------------------
app.config['JWT_SECRET_KEY'] = 'supersecretkey'  
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(minutes=10)  # Token expires in 10 minutes
jwt = JWTManager(app)

# ------------------ STEP 1: USER REGISTRATION ------------------

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    # Hash the password
    hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    # Generate a 2FA secret key
    twofa_secret = pyotp.random_base32()

    try:
        query = "INSERT INTO users (username, password, twofa_secret) VALUES (%s, %s, %s)"
        cursor.execute(query, (username, hashed_pw, twofa_secret))
        db.commit()
        return jsonify({"message": "✅ User registered successfully!", "2FA Secret": twofa_secret}), 201
    except pymysql.IntegrityError:
        return jsonify({"error": "❌ Username already exists"}), 409

# ------------------ STEP 2: GENERATE GOOGLE AUTH QR CODE ------------------

@app.route('/generate-qr', methods=['GET'])
def generate_qr():
    username = request.args.get('username')

    if not username:
        return jsonify({"error": "Username is required"}), 400

    # Get the user's 2FA secret from the database
    query = "SELECT twofa_secret FROM users WHERE username = %s"
    cursor.execute(query, (username,))
    user = cursor.fetchone()

    if not user:
        return jsonify({"error": "User not found"}), 404

    twofa_secret = user[0]

    # Generate OTP Auth URL
    otp_auth_url = pyotp.totp.TOTP(twofa_secret).provisioning_uri(username, issuer_name="SecureApp")

    # Generate QR code
    qr = qrcode.make(otp_auth_url)
    img_io = BytesIO()
    qr.save(img_io, format="PNG")
    img_io.seek(0)

    # Convert QR Code to Base64 for easy display
    qr_base64 = base64.b64encode(img_io.getvalue()).decode()

    return jsonify({"qr_code": qr_base64, "otp_auth_url": otp_auth_url})

# ------------------ STEP 3: VERIFY 2FA CODE ------------------

@app.route('/verify-2fa', methods=['POST'])
def verify_2fa():
    data = request.json
    username = data.get('username')
    otp_code = data.get('otp_code')

    if not username or not otp_code:
        return jsonify({"error": "Username and OTP code required"}), 400

    # Get the user's 2FA secret from the database
    query = "SELECT twofa_secret FROM users WHERE username = %s"
    cursor.execute(query, (username,))
    user = cursor.fetchone()

    if not user:
        return jsonify({"error": "User not found"}), 404

    twofa_secret = user[0]

    # Verify OTP Code
    totp = pyotp.TOTP(twofa_secret)
    if totp.verify(otp_code):
        return jsonify({"message": "✅ 2FA verification successful!"}), 200
    else:
        return jsonify({"error": "❌ Invalid 2FA code"}), 401

# ------------------ STEP 4: LOGIN WITH 2FA & JWT TOKEN ------------------

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    # Fetch user details from the database
    query = "SELECT password, twofa_secret FROM users WHERE username = %s"
    cursor.execute(query, (username,))
    user = cursor.fetchone()

    if not user:
        return jsonify({"error": "User not found"}), 404

    stored_password, twofa_secret = user

    # Verify password
    if not bcrypt.checkpw(password.encode('utf-8'), stored_password.encode('utf-8')):
        return jsonify({"error": "Invalid credentials"}), 401

    return jsonify({"message": "Enter 2FA code", "username": username}), 200

@app.route('/verify-login-2fa', methods=['POST'])
def verify_login_2fa():
    data = request.json
    username = data.get('username')
    otp_code = data.get('otp_code')

    if not username or not otp_code:
        return jsonify({"error": "Username and OTP code required"}), 400

    # Get the user's 2FA secret from the database
    query = "SELECT twofa_secret FROM users WHERE username = %s"
    cursor.execute(query, (username,))
    user = cursor.fetchone()

    if not user:
        return jsonify({"error": "User not found"}), 404

    twofa_secret = user[0]

    # Verify OTP Code
    totp = pyotp.TOTP(twofa_secret)
    if not totp.verify(otp_code):
        return jsonify({"error": "❌ Invalid 2FA code"}), 401

    # Generate JWT Token (Expires in 10 Minutes)
    access_token = create_access_token(identity=username)

    return jsonify({"message": "✅ Login successful!", "access_token": access_token}), 200

# ------------------ STEP 5: SECURED CRUD OPERATIONS ------------------

@app.route('/products', methods=['POST'])
@jwt_required()
def create_product():
    data = request.json
    name = data.get('name')
    description = data.get('description', '')
    price = data.get('price')
    quantity = data.get('quantity')

    if not name or not price or not quantity:
        return jsonify({"error": "Name, price, and quantity are required"}), 400

    query = "INSERT INTO products (name, description, price, quantity) VALUES (%s, %s, %s, %s)"
    cursor.execute(query, (name, description, price, quantity))
    db.commit()

    return jsonify({"message": "✅ Product created successfully!"}), 201

@app.route('/products/<int:product_id>', methods=['PUT'])
@jwt_required()
def update_product(product_id):
    data = request.json
    name = data.get('name')
    description = data.get('description')
    price = data.get('price')
    quantity = data.get('quantity')

    cursor.execute("UPDATE products SET name=%s, description=%s, price=%s, quantity=%s WHERE id=%s",
                   (name, description, price, quantity, product_id))
    db.commit()

    return jsonify({"message": "✅ Product updated successfully!"}), 200

@app.route('/products/<int:product_id>', methods=['DELETE'])
@jwt_required()
def delete_product(product_id):
    cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
    db.commit()
    return jsonify({"message": "✅ Product deleted successfully!"}), 200
@app.route('/products', methods=['GET'])
@jwt_required()
def get_products():
    cursor.execute("SELECT * FROM products")
    products = cursor.fetchall()

    return jsonify({"products": [
        {"id": p[0], "name": p[1], "description": p[2], "price": float(p[3]), "quantity": p[4]} for p in products
    ]}), 200


# ------------------ RUN THE FLASK APP ------------------

if __name__ == '__main__':
    app.run(debug=True)
