import frappe
import base64
from frappe.utils.pdf import get_pdf
import math

@frappe.whitelist()
def download_multiple_item_stickers(item_codes):
    """
    Generate PDF with multiple QR codes arranged in fixed layout (10 items per page)
    Uses existing custom_qr_image field from Item doctype
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
            
            # Check if QR image exists
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
            frappe.throw("No QR codes found for the selected items. Please ensure the custom_qr_image field is populated.")
        
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

@frappe.whitelist()
def check_items_with_qr_codes(item_codes):
    """
    Check which items have QR codes attached
    """
    if isinstance(item_codes, str):
        import json
        item_codes = json.loads(item_codes)
    
    items_with_qr = []
    items_without_qr = []
    
    for item_code in item_codes:
        try:
            item_doc = frappe.get_doc("Item", item_code)
            if item_doc.custom_qr_image:
                items_with_qr.append(item_code)
            else:
                items_without_qr.append(item_code)
        except Exception as e:
            frappe.log_error(f"Error checking {item_code}: {str(e)}")
            items_without_qr.append(item_code)
    
    return {
        "items_with_qr": items_with_qr,
        "items_without_qr": items_without_qr,
        "total_with_qr": len(items_with_qr),
        "total_without_qr": len(items_without_qr)
    }