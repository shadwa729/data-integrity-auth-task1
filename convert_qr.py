import base64

# Paste your full Base64 QR code string here (from Postman)
base64_string = """iVBORw0KGgoAAAANSUhEUgAAAcIAAAHCAQAAAABUY"""

# Fix the padding issue (Base64 must be a multiple of 4)
missing_padding = len(base64_string) % 4
if missing_padding:
    base64_string += "=" * (4 - missing_padding)

# Convert Base64 to an image file
with open("qr_code.png", "wb") as img_file:
    img_file.write(base64.b64decode(base64_string))

print("✅ QR Code saved as 'qr_code.png'. Open and scan it in Google Authenticator!")
