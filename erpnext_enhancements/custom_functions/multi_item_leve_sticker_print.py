import frappe
import base64
from frappe.utils.pdf import get_pdf
from frappe.utils import get_site_path
import os
import qrcode
from io import BytesIO
import math

@frappe.whitelist()
def download_multiple_item_stickers(item_codes):
    """
    Generate PDF with multiple QR codes arranged in fixed layout (10 items per page)
    """
    try:
        if isinstance(item_codes, str):
            import json
            item_codes = json.loads(item_codes)
        
        # Fixed layout: 10 items per page
        items_per_page = 10
        
        # Get item data with QR codes
        item_data = []
        for item_code in item_codes:
            item_doc = frappe.get_doc("Item", item_code)
            
            # Generate QR code if not exists
            if not item_doc.custom_qr_image:
                generate_qr_code_for_item(item_doc)
                item_doc.reload()
            
            if item_doc.custom_qr_image:
                # Get item price from Item Price doctype
                item_price = get_item_price(item_code)
                
                item_data.append({
                    'item_code': item_code,
                    'item_name': item_doc.item_name or item_code,
                    'item_price': item_price,
                    'qr_url': item_doc.custom_qr_image
                })
        
        if not item_data:
            frappe.throw("No QR codes found for the selected items")
        
        # Generate HTML with QR codes in fixed layout
        html_content = generate_fixed_layout_html(item_data, items_per_page)
        
        # Convert to PDF
        pdf_data = get_pdf(html_content)
        
        # Encode to base64
        base64_pdf = base64.b64encode(pdf_data).decode('utf-8')
        
        # Calculate page count
        page_count = math.ceil(len(item_data) / items_per_page)
        
        return {
            "base64_pdf": base64_pdf,
            "item_count": len(item_data),
            "page_count": page_count
        }
        
    except Exception as e:
        frappe.log_error(f"Error in download_multiple_item_stickers: {str(e)}")
        frappe.throw(f"Error generating stickers: {str(e)}")

def get_item_price(item_code):
    """
    Get item price from Item Price doctype
    """
    try:
        # Try to get the default selling price
        item_price = frappe.db.get_value(
            'Item Price',
            {
                'item_code': item_code,
                'selling': 1
            },
            'price_list_rate',
            order_by='creation desc'
        )
        
        if item_price:
            return f"₹{item_price:.2f}"
        
        # If no selling price, try any price
        item_price = frappe.db.get_value(
            'Item Price',
            {'item_code': item_code},
            'price_list_rate',
            order_by='creation desc'
        )
        
        if item_price:
            return f"₹{item_price:.2f}"
        
        return "Price Not Set"
        
    except Exception as e:
        frappe.log_error(f"Error getting price for {item_code}: {str(e)}")
        return "Price Not Available"

def generate_fixed_layout_html(item_data, items_per_page=10):
    """
    Generate HTML with QR codes arranged in fixed layout (10 items per page)
    """
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {{
                size: A4;
                margin: 10mm;
            }}
            body {{
                margin: 0;
                padding: 0;
                font-family: Arial, sans-serif;
                font-size: 10pt;
            }}
            .page {{
                page-break-after: always;
                width: 100%;
            }}
            .header {{
                text-align: center;
                margin-bottom: 8mm;
                padding-bottom: 3mm;
                border-bottom: 2px solid #333;
            }}
            .company-name {{
                font-size: 14pt;
                font-weight: bold;
                color: #333;
                margin: 0;
            }}
            .item-row {{
                display: flex;
                align-items: center;
                width: 100%;
                border: 1px solid #ddd;
                border-radius: 3px;
                padding: 4mm;
                margin-bottom: 4mm;
                background-color: #fafafa;
                box-sizing: border-box;
            }}
            .qr-section {{
                flex: 0 0 auto;
                width: 24mm;
                margin-right: 6mm;
            }}
            .qr-section img {{
                width: 22mm;
                height: 22mm;
                object-fit: contain;
                border: 1px solid #ccc;
                border-radius: 2px;
                display: block;
            }}
            .details-section {{
                flex: 1 1 auto;
            }}
            .item-name {{
                font-weight: bold;
                font-size: 11pt;
                margin: 0 0 2mm 0;
                color: #333;
                line-height: 1.2;
            }}
            .item-code {{
                font-size: 9pt;
                color: #666;
                margin: 0 0 2mm 0;
                line-height: 1.1;
            }}
            .item-price {{
                font-size: 10.5pt;
                color: #2e7d32;
                font-weight: bold;
                margin: 0;
                line-height: 1.1;
            }}
        </style>

    </head>
    <body>
    """
    
    # Split item data into pages
    pages = [item_data[i:i + items_per_page] for i in range(0, len(item_data), items_per_page)]
    
    for page_index, page_items in enumerate(pages):
        
        for item in page_items:
            qr_url = item['qr_url']
            if not qr_url.startswith('http'):
                site_url = frappe.utils.get_url()
                qr_url = site_url + item['qr_url']
            
            html += f"""
            <div class="item-row">
                <div class="qr-section">
                    <img src="{qr_url}" alt="QR Code" onerror="this.style.display='none'" />
                </div>
                <div class="details-section">
                    <div class="company-name">The Srinath Collective</div>
                    <div class="item-name">{frappe.utils.escape_html(item['item_name'])}</div>
                    <div class="item-code">Code: {frappe.utils.escape_html(item['item_code'])}</div>
                    <div class="item-price">{frappe.utils.escape_html(item['item_price'])}</div>
                </div>

            </div>
            """
        
        html += '''
        </div>
        '''
    
    html += """
    </body>
    </html>
    """
    
    return html

def generate_qr_code_for_item(item_doc):
    """
    Generate QR code for an item and save it
    """
    try:
        # Create QR code data (you can customize this)
        qr_data = f"Item: {item_doc.name}\nName: {item_doc.item_name}"
        if item_doc.brand:
            qr_data += f"\nBrand: {item_doc.brand}"
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # Create QR code image
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Save to BytesIO
        img_buffer = BytesIO()
        qr_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        # Create file in Frappe
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": f"qr_code_{item_doc.name}.png",
            "content": base64.b64encode(img_buffer.getvalue()).decode(),
            "decode": True,
            "is_private": 0,
            "attached_to_doctype": "Item",
            "attached_to_name": item_doc.name
        })
        file_doc.insert()
        
        # Update item with QR code URL
        item_doc.custom_qr_image = file_doc.file_url
        item_doc.save()
        
        return file_doc.file_url
        
    except Exception as e:
        frappe.log_error(f"Error generating QR code for {item_doc.name}: {str(e)}")
        return None

@frappe.whitelist()
def generate_qr_codes_bulk(item_codes):
    """
    Generate QR codes for multiple items in bulk
    """
    if isinstance(item_codes, str):
        import json
        item_codes = json.loads(item_codes)
    
    success_count = 0
    for item_code in item_codes:
        try:
            item_doc = frappe.get_doc("Item", item_code)
            if not item_doc.custom_qr_image:
                generate_qr_code_for_item(item_doc)
                success_count += 1
        except Exception as e:
            frappe.log_error(f"Error processing {item_code}: {str(e)}")
    
    return {"success_count": success_count, "total": len(item_codes)}