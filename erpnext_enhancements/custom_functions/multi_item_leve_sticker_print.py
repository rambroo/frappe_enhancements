import frappe
import base64
from frappe.utils.pdf import get_pdf
import math

@frappe.whitelist()
def download_multiple_item_stickers(item_codes):
    """
    Generate PDF with multiple QR codes arranged in fixed layout (10 items per page)
    Uses existing custom_qr_image field from Item doctype with enhanced logic
    """
    try:
        if isinstance(item_codes, str):
            import json
            item_codes = json.loads(item_codes)
        
        # Fixed layout: 10 items per page
        items_per_page = 10
        
        # Get item data with QR codes and enhanced logic
        item_data = []
        for item_code in item_codes:
            item_doc = frappe.get_doc("Item", item_code)
            
            # Check if QR image exists
            if item_doc.custom_qr_image:
                # Get enhanced item data with all logic
                enhanced_data = get_enhanced_item_data(item_doc)
                item_data.append(enhanced_data)
        
        if not item_data:
            frappe.throw("No QR codes found for the selected items. Please ensure the custom_qr_image field is populated.")
        
        # Generate HTML with QR codes in fixed layout
        html_content = generate_enhanced_layout_html(item_data, items_per_page)
        
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

def get_enhanced_item_data(item_doc):
    """
    Get enhanced item data with all the logic from print format
    """
    try:
        # Basic item data
        item_data = {
            'item_code': item_doc.name,
            'item_name': item_doc.item_name or item_doc.name,
            'qr_url': item_doc.custom_qr_image,
            'is_tile': False,
            'category_type': 'general'
        }
        
        # Check if it's a tile item
        custom_category = (item_doc.custom_category or '').lower()
        custom_category_material = (item_doc.custom_category_material or '').lower()
        
        if custom_category in ['tiles', 'tile'] or custom_category_material in ['tiles', 'tile']:
            item_data['is_tile'] = True
            item_data['category_type'] = 'tile'
            
            # Get tile-specific data
            item_data.update({
                'length_mm': item_doc.custom_length_mm or '',
                'breadth_mm': item_doc.custom_breadh_mm or '',
                'tile_shape': item_doc.custom_tile_shape or '',
                'shade': item_doc.custom_shade or ''
            })
            
            # Get brand description
            if item_doc.brand:
                try:
                    brand_doc = frappe.get_doc("Brand", item_doc.brand)
                    item_data['brand_description'] = brand_doc.description or ''
                except:
                    item_data['brand_description'] = ''
            else:
                item_data['brand_description'] = ''
        else:
            # Check if it's fitting/sanitary
            category_combined = f"{custom_category} {custom_category_material}"
            if 'fitting' in category_combined or 'sanitary' in category_combined:
                item_data['category_type'] = 'fitting_sanitary'
        
        # Get pricing information
        item_data['price_info'] = get_enhanced_pricing(item_doc)
        
        return item_data
        
    except Exception as e:
        frappe.log_error(f"Error getting enhanced data for {item_doc.name}: {str(e)}")
        return {
            'item_code': item_doc.name,
            'item_name': item_doc.item_name or item_doc.name,
            'qr_url': item_doc.custom_qr_image,
            'is_tile': False,
            'category_type': 'general',
            'price_info': {'display_price': 'Price Not Available', 'unit': ''}
        }

def get_enhanced_pricing(item_doc):
    """
    Get enhanced pricing with all the logic from print format
    """
    try:
        # Get base rate from Item Price
        base_rate = frappe.db.get_value(
            "Item Price", 
            {"item_code": item_doc.name, "price_list": "Standard Selling"}, 
            "price_list_rate"
        ) or 0
        
        # Include tax (18%)
        rate_incl_tax = base_rate * 1.18
        
        if not item_doc.custom_category or item_doc.custom_category.lower() not in ['tiles', 'tile']:
            # For non-tile items, simple MRP display
            return {
                'display_price': f"MRP: {rate_incl_tax:.0f}",
                'unit': ''
            }
        
        # For tile items, complex pricing logic
        length_mm = float(item_doc.custom_length_mm or 0)
        breadth_mm = float(item_doc.custom_breadh_mm or 0)
        
        # Get UOM conversion data
        uom_data = {}
        for uom in item_doc.uoms:
            uom_data[uom.uom] = float(uom.conversion_factor or 0)
        
        # Apply the complex pricing logic
        handled = False
        price_info = {'display_price': 'Price calculation error', 'unit': ''}
        
        # First: Check if Sqft UOM is available
        if 'Sqft' in uom_data and uom_data['Sqft'] > 0:
            conversion = uom_data['Sqft']
            
            if conversion <= 0.970:
                price_info = {
                    'display_price': f"Price: {rate_incl_tax:.0f}",
                    'unit': f"/{item_doc.stock_uom}"
                }
                handled = True
            elif conversion > 0.970:
                rate_per_sqft = rate_incl_tax / conversion
                price_info = {
                    'display_price': f"Price: {rate_per_sqft:.0f}",
                    'unit': "/Sqft"
                }
                handled = True
        
        # Fallback logic if Sqft logic didn't trigger
        if not handled:
            if length_mm <= 300 or breadth_mm <= 300:
                price_info = {
                    'display_price': f"Price: {rate_incl_tax:.0f}",
                    'unit': f"/{item_doc.stock_uom}"
                }
            elif length_mm > 300 and breadth_mm > 300:
                if 'Sqft' in uom_data and uom_data['Sqft'] > 0:
                    conversion = uom_data['Sqft']
                    rate_per_sqft = rate_incl_tax / conversion
                    price_info = {
                        'display_price': f"Price: {rate_per_sqft:.0f}",
                        'unit': "/Sqft"
                    }
                else:
                    price_info = {
                        'display_price': "Price: Sqft not set",
                        'unit': ""
                    }
            else:
                if 'Sqft' in uom_data and uom_data['Sqft'] > 0:
                    conversion = uom_data['Sqft']
                    rate_per_sqft = rate_incl_tax / conversion
                    price_info = {
                        'display_price': f"Price: {rate_per_sqft:.0f}",
                        'unit': "/Sqft"
                    }
                else:
                    price_info = {
                        'display_price': "Price: Unknown size",
                        'unit': ""
                    }
        
        return price_info
        
    except Exception as e:
        frappe.log_error(f"Error getting pricing for {item_doc.name}: {str(e)}")
        return {'display_price': 'Price Not Available', 'unit': ''}

def generate_enhanced_layout_html(item_data, items_per_page=10):
    """
    Generate HTML with enhanced layout matching print format logic
    """
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="pdfkit-page-width" content="210mm"/>
        <meta name="pdfkit-page-height" content="297mm"/>
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
            
            /* Label container similar to print format */
            .label-container {{
                width: 100%;
                height: 40mm;
                display: flex;
                border: 1px solid #ddd;
                border-radius: 3px;
                padding: 2mm;
                margin-bottom: 4mm;
                background-color: #fafafa;
                box-sizing: border-box;
            }}
            
            /* QR section */
            .qr-section {{
                width: 36mm;
                height: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin-right: 4mm;
            }}
            
            .qr-section img {{
                width: 29mm;
                height: 29mm;
                object-fit: contain;
                border: 1px solid #ccc;
                border-radius: 2px;
            }}
            
            /* Text section */
            .text-section {{
                flex: 1;
                display: flex;
                flex-direction: column;
                justify-content: center;
                padding-left: 2mm;
            }}
            
            .label-title {{
                font-size: 12pt;
                font-weight: bold;
                color: #333;
                margin-bottom: 2mm;
            }}
            
            .label-id {{
                font-size: 10pt;
                font-weight: bold;
                margin-bottom: 1mm;
            }}
            
            .label-text {{
                font-size: 9pt;
                margin-bottom: 1mm;
                color: #666;
            }}
            
            .label-size {{
                font-size: 9pt;
                margin-bottom: 1mm;
            }}
            
            .label-price {{
                font-size: 10pt;
                font-weight: bold;
                color: #2e7d32;
                margin-top: 1mm;
            }}
        </style>
    </head>
    <body>
    """
    
    # Split item data into pages
    pages = [item_data[i:i + items_per_page] for i in range(0, len(item_data), items_per_page)]
    
    for page_index, page_items in enumerate(pages):
        html += '<div class="page">'
        
        for item in page_items:
            qr_url = item['qr_url']
            if not qr_url.startswith('http'):
                site_url = frappe.utils.get_url()
                qr_url = site_url + item['qr_url']
            
            html += f"""
            <div class="label-container">
                <div class="qr-section">
                    <img src="{qr_url}" alt="QR Code" onerror="this.style.display='none'" />
                </div>
                <div class="text-section">
                    <div class="label-title">THE SRINATH COLLECTIVE</div>
                    <div class="label-id">ID: {frappe.utils.escape_html(item['item_code'])}</div>
            """
            
            # Add category-specific content
            if item['is_tile']:
                # Tile-specific layout
                size_info = f"{item.get('length_mm', '')}X{item.get('breadth_mm', '')} {item.get('tile_shape', '')} {item.get('shade', '')}"
                html += f"""
                    <div class="label-size">Size: {frappe.utils.escape_html(size_info)}</div>
                """
                if item.get('brand_description'):
                    html += f"""
                    <div class="label-text">Code: {frappe.utils.escape_html(item['brand_description'])}</div>
                    """
            else:
                # Non-tile layout
                html += f"""
                    <div class="label-text">{frappe.utils.escape_html(item['item_name'])}</div>
                """
            
            # Add price information
            price_info = item.get('price_info', {})
            html += f"""
                    <div class="label-price">{frappe.utils.escape_html(price_info.get('display_price', 'Price Not Available'))}{frappe.utils.escape_html(price_info.get('unit', ''))}</div>
                </div>
            </div>
            """
        
        html += '</div>'
    
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