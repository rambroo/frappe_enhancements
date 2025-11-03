import frappe
import qrcode
import os
from frappe.utils import get_site_path

@frappe.whitelist()
def generate_qr_for_missing_items():
    """Generate QR codes for all items that are missing QR codes."""
    missing_qr_items = frappe.get_all('Item', filters={'custom_qr_image': ['is', 'not set']})
    
    for item in missing_qr_items:
        generate_qr_code_for_item(item)

@frappe.whitelist()
def generate_qr_code_for_item(item_code):
    """Generate a QR code for a given Item and attach it as an image."""
    item_doc = frappe.get_doc("Item", item_code)  # Fetch the Item document
    print(f"Generating QR code for Item Code: {item_doc.item_code}")

    qr_data = item_doc.item_code  # Use Item Code as QR data
    qr_image = qrcode.make(qr_data)  # Generate QR Code

    # Define directory path
    qr_dir = get_site_path("public", "files", "QR_CODE")
    os.makedirs(qr_dir, exist_ok=True)  # Ensure directory exists

    # Define full file path
    qr_code_filename = f"qr_{item_doc.item_code}.png"
    qr_code_path = os.path.join(qr_dir, qr_code_filename)

    # Save the QR Code Image
    qr_image.save(qr_code_path)

    # Set the file URL for Frappe
    qr_code_url = f"/files/QR_CODE/{qr_code_filename}"
    frappe.db.set_value("Item", item_doc.name, "custom_qr_image", qr_code_url)
    frappe.db.commit()  # Ensure changes are saved

    return qr_code_url  # Return URL if needed
