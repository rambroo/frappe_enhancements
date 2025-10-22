import frappe
from frappe import _
from frappe.utils import nowdate, get_fullname
import json

# HARDCODED CONFIGURATION
HARDCODED_ROLES = []
HARDCODED_TEMPLATE = None


def send_material_receipt_notifications(doc, method=None):
    """
    Optimized: Send WhatsApp notifications when materials are received.
    Reduced database queries and improved efficiency.
    """
    if doc.doctype == "Stock Entry" and doc.stock_entry_type != "Material Receipt":
        return
    
    try:
        recipients = get_all_recipients_optimized(doc)
        
        if not recipients:
            log_notification_result(
                success=False,
                doc=doc,
                recipients=[],
                error_message="No recipients found. Check configuration and user settings."
            )
            return
        
        success_list = []
        failed_list = []
        
        for recipient in recipients:
            try:
                send_whatsapp_to_recipient(doc, recipient)
                success_list.append(recipient)
            except Exception as e:
                recipient['error'] = str(e)
                failed_list.append(recipient)
        
        log_notification_result(
            success=len(failed_list) == 0,
            doc=doc,
            recipients=recipients,
            success_list=success_list,
            failed_list=failed_list
        )
        
        frappe.db.commit()
        
    except Exception as e:
        log_notification_result(
            success=False,
            doc=doc,
            recipients=[],
            error_message=f"Critical Error: {str(e)}\n\n{frappe.get_traceback()}"
        )


def get_all_recipients_optimized(doc):
    """
    OPTIMIZED: Collect all recipients with minimal database queries.
    Uses bulk queries and caching to reduce load.
    """
    recipients_dict = {}
    
    # Extract all linked document IDs upfront (single loop)
    linked_docs = extract_linked_documents(doc)
    
    # Batch fetch all data at once
    all_data = batch_fetch_recipient_data(doc, linked_docs)
    
    # Process sales team recipients
    for recipient in all_data['sales_team']:
        if recipient['mobile']:
            if recipient['mobile'] in recipients_dict:
                recipients_dict[recipient['mobile']]['source'] += f", {recipient['source']}"
            else:
                recipients_dict[recipient['mobile']] = recipient
    
    # Process material request recipients
    for recipient in all_data['material_request']:
        if recipient['mobile']:
            if recipient['mobile'] in recipients_dict:
                recipients_dict[recipient['mobile']]['source'] += f", {recipient['source']}"
            else:
                recipients_dict[recipient['mobile']] = recipient
    
    # Process creator
    if all_data['creator'] and all_data['creator']['mobile']:
        mobile = all_data['creator']['mobile']
        if mobile in recipients_dict:
            recipients_dict[mobile]['source'] += f", {all_data['creator']['source']}"
        else:
            recipients_dict[mobile] = all_data['creator']
    
    # Process customer contacts
    for recipient in all_data['customers']:
        if recipient['mobile']:
            if recipient['mobile'] in recipients_dict:
                recipients_dict[recipient['mobile']]['source'] += f", {recipient['source']}"
            else:
                recipients_dict[recipient['mobile']] = recipient
    
    # Process role-based recipients
    for recipient in all_data['roles']:
        if recipient['mobile']:
            if recipient['mobile'] in recipients_dict:
                recipients_dict[recipient['mobile']]['source'] += f", {recipient['source']}"
            else:
                recipients_dict[recipient['mobile']] = recipient
    
    return list(recipients_dict.values())


def extract_linked_documents(doc):
    """
    OPTIMIZED: Extract all linked document IDs in a single pass.
    """
    linked = {
        'sales_orders': set(),
        'quotations': set(),
        'sales_invoices': set(),
        'material_requests': set(),
        'purchase_orders': set(),
        'material_request_items': set(),
        'customers': set()
    }
    
    for item in doc.get("items", []):
        # Sales Orders
        if hasattr(item, 'sales_order') and item.sales_order:
            linked['sales_orders'].add(item.sales_order)
        
        # Quotations
        if hasattr(item, 'quotation') and item.quotation:
            linked['quotations'].add(item.quotation)
        
        # Sales Invoices
        if hasattr(item, 'sales_invoice') and item.sales_invoice:
            linked['sales_invoices'].add(item.sales_invoice)
        
        # Material Requests
        if hasattr(item, 'material_request') and item.material_request:
            linked['material_requests'].add(item.material_request)
        
        # Material Request Items
        if hasattr(item, 'material_request_item') and item.material_request_item:
            linked['material_request_items'].add(item.material_request_item)
        
        # Purchase Orders
        if hasattr(item, 'purchase_order') and item.purchase_order:
            linked['purchase_orders'].add(item.purchase_order)
    
    return linked


def batch_fetch_recipient_data(doc, linked_docs):
    """
    OPTIMIZED: Fetch all recipient data in bulk queries.
    Reduces individual queries to batch operations.
    """
    result = {
        'sales_team': [],
        'material_request': [],
        'creator': None,
        'customers': [],
        'roles': []
    }
    
    # 1. Fetch Sales Team members (one query per doctype)
    if linked_docs['sales_orders']:
        result['sales_team'].extend(
            fetch_sales_team_bulk(linked_docs['sales_orders'], "Sales Order")
        )
    if linked_docs['quotations']:
        result['sales_team'].extend(
            fetch_sales_team_bulk(linked_docs['quotations'], "Quotation")
        )
    if linked_docs['sales_invoices']:
        result['sales_team'].extend(
            fetch_sales_team_bulk(linked_docs['sales_invoices'], "Sales Invoice")
        )
    
    # 2. Fetch additional Sales Orders from Purchase Orders (single query)
    if doc.doctype == "Purchase Receipt" and linked_docs['purchase_orders']:
        additional_sos = fetch_sales_orders_from_purchase_orders(linked_docs['purchase_orders'])
        if additional_sos:
            result['sales_team'].extend(
                fetch_sales_team_bulk(additional_sos, "Sales Order")
            )
            linked_docs['sales_orders'].update(additional_sos)
    
    # 3. Fetch Sales Orders from Material Request Items (single query)
    if linked_docs['material_request_items']:
        mr_sales_orders = fetch_sales_orders_from_mr_items(linked_docs['material_request_items'])
        if mr_sales_orders:
            result['sales_team'].extend(
                fetch_sales_team_bulk(mr_sales_orders, "Sales Order")
            )
            linked_docs['sales_orders'].update(mr_sales_orders)
    
    # 4. Fetch Material Request creators (single query)
    if linked_docs['material_requests']:
        result['material_request'] = fetch_material_request_creators_bulk(
            linked_docs['material_requests']
        )
    
    # 5. Fetch document creator
    result['creator'] = fetch_user_details(doc.owner, f"{doc.doctype} Creator")
    
    # 6. Fetch customers and contacts (batch query)
    if linked_docs['sales_orders']:
        result['customers'] = fetch_customer_contacts_bulk(
            linked_docs['sales_orders']
        )
    
    # 7. Fetch role-based recipients (single query)
    result['roles'] = fetch_role_based_recipients_bulk()
    
    return result


def fetch_sales_team_bulk(doc_ids, doctype):
    """
    OPTIMIZED: Fetch all sales team members in one query with joins.
    """
    if not doc_ids:
        return []
    
    try:
        # Single query with all joins
        data = frappe.db.sql("""
            SELECT DISTINCT
                u.name as user,
                u.full_name,
                COALESCE(u.mobile_no, u.phone) as mobile,
                st.sales_person,
                st.parent as source_doc
            FROM `tabSales Team` st
            INNER JOIN `tabSales Person` sp ON sp.name = st.sales_person
            INNER JOIN `tabEmployee` emp ON emp.name = sp.employee
            INNER JOIN `tabUser` u ON u.name = emp.user_id
            WHERE st.parent IN %(docs)s
            AND st.parenttype = %(doctype)s
            AND u.enabled = 1
            AND (u.mobile_no IS NOT NULL OR u.phone IS NOT NULL)
        """, {"docs": list(doc_ids), "doctype": doctype}, as_dict=1)
        
        recipients = []
        for row in data:
            if row.mobile:
                recipients.append({
                    "user": row.user,
                    "name": row.full_name or row.user,
                    "mobile": row.mobile,
                    "source": f"Sales Team ({doctype})",
                    "sales_person": row.sales_person
                })
        
        return recipients
    except:
        return []


def fetch_sales_orders_from_purchase_orders(po_ids):
    """
    OPTIMIZED: Fetch linked sales orders from purchase orders in one query.
    """
    if not po_ids:
        return set()
    
    try:
        if not frappe.db.has_column("Purchase Order Item", "sales_order"):
            return set()
        
        results = frappe.db.sql("""
            SELECT DISTINCT sales_order
            FROM `tabPurchase Order Item`
            WHERE parent IN %(pos)s
            AND sales_order IS NOT NULL
            AND sales_order != ''
        """, {"pos": list(po_ids)}, as_dict=1)
        
        return {row.sales_order for row in results if row.sales_order}
    except:
        return set()


def fetch_sales_orders_from_mr_items(mr_item_ids):
    """
    OPTIMIZED: Fetch sales orders from material request items in one query.
    """
    if not mr_item_ids:
        return set()
    
    try:
        if not frappe.db.has_column("Material Request Item", "sales_order"):
            return set()
        
        results = frappe.db.sql("""
            SELECT DISTINCT sales_order
            FROM `tabMaterial Request Item`
            WHERE name IN %(items)s
            AND sales_order IS NOT NULL
            AND sales_order != ''
        """, {"items": list(mr_item_ids)}, as_dict=1)
        
        return {row.sales_order for row in results if row.sales_order}
    except:
        return set()


def fetch_material_request_creators_bulk(mr_ids):
    """
    OPTIMIZED: Fetch material request creators in one query.
    """
    if not mr_ids:
        return []
    
    try:
        # Check if requested_by field exists
        has_requested_by = frappe.db.has_column("Material Request", "requested_by")
        
        if has_requested_by:
            query = """
                SELECT DISTINCT
                    COALESCE(mr.requested_by, mr.owner) as user,
                    u.full_name,
                    COALESCE(u.mobile_no, u.phone) as mobile
                FROM `tabMaterial Request` mr
                INNER JOIN `tabUser` u ON u.name = COALESCE(mr.requested_by, mr.owner)
                WHERE mr.name IN %(mrs)s
                AND u.enabled = 1
                AND (u.mobile_no IS NOT NULL OR u.phone IS NOT NULL)
            """
        else:
            query = """
                SELECT DISTINCT
                    mr.owner as user,
                    u.full_name,
                    COALESCE(u.mobile_no, u.phone) as mobile
                FROM `tabMaterial Request` mr
                INNER JOIN `tabUser` u ON u.name = mr.owner
                WHERE mr.name IN %(mrs)s
                AND u.enabled = 1
                AND (u.mobile_no IS NOT NULL OR u.phone IS NOT NULL)
            """
        
        data = frappe.db.sql(query, {"mrs": list(mr_ids)}, as_dict=1)
        
        recipients = []
        for row in data:
            if row.mobile:
                recipients.append({
                    "user": row.user,
                    "name": row.full_name or row.user,
                    "mobile": row.mobile,
                    "source": "Material Request Creator"
                })
        
        return recipients
    except:
        return []


def fetch_user_details(user_id, source):
    """
    OPTIMIZED: Fetch single user details.
    """
    if not user_id:
        return None
    
    try:
        user = frappe.db.get_value(
            "User",
            user_id,
            ["name", "mobile_no", "phone", "full_name", "enabled"],
            as_dict=1
        )
        
        if not user or not user.enabled:
            return None
        
        mobile = user.mobile_no or user.phone
        if not mobile:
            return None
        
        return {
            "user": user.name,
            "name": user.full_name or user.name,
            "mobile": mobile,
            "source": source
        }
    except:
        return None


def fetch_customer_contacts_bulk(sales_order_ids):
    """
    OPTIMIZED: Fetch customer contacts from sales orders in one query.
    """
    if not sales_order_ids:
        return []
    
    try:
        # Single query with all joins
        data = frappe.db.sql("""
            SELECT DISTINCT
                so.customer,
                c.customer_name,
                con.name as contact_name,
                CONCAT(COALESCE(con.first_name, ''), ' ', COALESCE(con.last_name, '')) as contact_full_name,
                COALESCE(con.mobile_no, con.phone) as mobile
            FROM `tabSales Order` so
            INNER JOIN `tabCustomer` c ON c.name = so.customer
            LEFT JOIN `tabDynamic Link` dl ON dl.link_name = so.customer 
                AND dl.link_doctype = 'Customer' 
                AND dl.parenttype = 'Contact'
            LEFT JOIN `tabContact` con ON con.name = dl.parent
            WHERE so.name IN %(sos)s
            AND (con.mobile_no IS NOT NULL OR con.phone IS NOT NULL)
        """, {"sos": list(sales_order_ids)}, as_dict=1)
        
        recipients = []
        seen_customers = set()
        
        for row in data:
            if row.customer in seen_customers:
                continue
            
            if row.mobile:
                seen_customers.add(row.customer)
                contact_name = row.contact_full_name.strip() if row.contact_full_name else row.contact_name
                
                recipients.append({
                    "user": f"Customer: {row.customer}",
                    "name": f"{row.customer_name} ({contact_name})" if contact_name else row.customer_name,
                    "mobile": row.mobile,
                    "source": "Customer Contact",
                    "customer": row.customer,
                    "customer_name": row.customer_name
                })
        
        return recipients
    except:
        return []


def fetch_role_based_recipients_bulk():
    """
    OPTIMIZED: Fetch role-based recipients in one query.
    """
    configured_roles = []
    
    try:
        if frappe.db.exists("DocType", "Material Receipt Notification Settings"):
            settings = frappe.get_single("Material Receipt Notification Settings")
            if hasattr(settings, 'notification_roles') and settings.notification_roles:
                configured_roles = [row.role for row in settings.notification_roles if row.role]
        
        if not configured_roles:
            configured_roles = HARDCODED_ROLES
        
        if not configured_roles:
            return []
        
        data = frappe.db.sql("""
            SELECT DISTINCT 
                u.name as user,
                u.full_name,
                COALESCE(u.mobile_no, u.phone) as mobile
            FROM `tabUser` u
            INNER JOIN `tabHas Role` hr ON hr.parent = u.name
            WHERE hr.role IN %(roles)s
            AND u.enabled = 1
            AND (u.mobile_no IS NOT NULL OR u.phone IS NOT NULL)
        """, {"roles": configured_roles}, as_dict=1)
        
        recipients = []
        for row in data:
            if row.mobile:
                recipients.append({
                    "user": row.user,
                    "name": row.full_name or row.user,
                    "mobile": row.mobile,
                    "source": f"Role-Based ({', '.join(configured_roles)})"
                })
        
        return recipients
    except:
        return []


def send_whatsapp_to_recipient(doc, recipient):
    """Send WhatsApp message to a specific recipient."""
    message = build_message(doc, recipient)
    template_name = get_whatsapp_template_name()
    
    frappe.call(
        "erpnext_enhancements.api.whatsapp_reminders.whatsapp.send_manual_whatsapp_message",
        doctype=doc.doctype,
        docname=doc.name,
        phone_number=recipient['mobile'],
        message=message,
        template_name=template_name if template_name else None
    )


def build_message(doc, recipient):
    """Build personalized WhatsApp message."""
    template_name = get_whatsapp_template_name()
    message = ""
    
    if template_name:
        template_text = frappe.db.get_value(
            "WhatsApp Message Template",
            template_name,
            "template_text"
        )
        if template_text:
            message = template_text
            message = message.replace("<div>", "").replace("</div>", "\n")
            message = message.replace("<p>", "").replace("</p>", "\n")
            message = message.replace("&nbsp;", " ").strip()
    
    if not message:
        message = build_default_message(doc, recipient)
    
    message = replace_message_variables(message, doc, recipient)
    
    return message


def build_default_message(doc, recipient):
    """Build default message template."""
    items_text = ""
    
    for idx, item in enumerate(doc.get("items", [])[:5], 1):
        qty = item.qty if hasattr(item, 'qty') else item.transfer_qty if hasattr(item, 'transfer_qty') else 0
        uom = item.uom if hasattr(item, 'uom') else item.stock_uom if hasattr(item, 'stock_uom') else ""
        items_text += f"{idx}. {item.item_name or item.item_code}: {qty} {uom}\n"
    
    if len(doc.get("items", [])) > 5:
        items_text += f"... and {len(doc.items) - 5} more items\n"
    
    linked_docs_text = get_linked_documents_text_cached(doc)
    
    supplier_text = ""
    if doc.doctype == "Purchase Receipt" and hasattr(doc, 'supplier'):
        supplier_text = f"Supplier: {doc.supplier}\n"
    
    message = f"""Dear {recipient['name']},

Materials have been received successfully!

{supplier_text}Document: {doc.name}
Date: {doc.posting_date if hasattr(doc, 'posting_date') else nowdate()}

{linked_docs_text}

Items Received:
{items_text}
Total Items: {len(doc.items)}

Thank you!"""
    
    return message


def get_linked_documents_text_cached(doc):
    """
    OPTIMIZED: Get linked documents text using already extracted data.
    """
    linked = extract_linked_documents(doc)
    result = "Against:\n"
    
    if linked['sales_orders']:
        result += f"Sales Order: {', '.join(linked['sales_orders'])}\n"
    
    if linked['quotations']:
        result += f"Quotation: {', '.join(linked['quotations'])}\n"
    
    if linked['sales_invoices']:
        result += f"Sales Invoice: {', '.join(linked['sales_invoices'])}\n"
    
    if linked['purchase_orders']:
        result += f"Purchase Order: {', '.join(linked['purchase_orders'])}\n"
    
    if linked['material_requests']:
        result += f"Material Request: {', '.join(linked['material_requests'])}\n"
    
    if result == "Against:\n":
        return ""
    
    return result


def replace_message_variables(message, doc, recipient):
    """Replace all variables in the message template."""
    linked = extract_linked_documents(doc)
    first_item = doc.items[0] if doc.items else None
    today = nowdate()
    
    replacements = {
        "{recipient_name}": recipient['name'],
        "{name}": recipient['name'],
        "{user_name}": recipient['name'],
        "{mobile}": recipient['mobile'],
        "{document_type}": doc.doctype,
        "{document_name}": doc.name,
        "{doc_name}": doc.name,
        "{posting_date}": str(doc.posting_date if hasattr(doc, 'posting_date') else today),
        "{today}": today,
        "{supplier}": doc.supplier if hasattr(doc, 'supplier') else "N/A",
        "{supplier_name}": doc.supplier_name if hasattr(doc, 'supplier_name') else doc.supplier if hasattr(doc, 'supplier') else "N/A",
        "{total_items}": str(len(doc.items)),
        "{item_count}": str(len(doc.items)),
        "{sales_order}": ", ".join(linked['sales_orders']) if linked['sales_orders'] else "N/A",
        "{quotation}": ", ".join(linked['quotations']) if linked['quotations'] else "N/A",
        "{material_request}": ", ".join(linked['material_requests']) if linked['material_requests'] else "N/A",
        "{purchase_order}": ", ".join(linked['purchase_orders']) if linked['purchase_orders'] else "N/A",
        "{customer}": recipient.get('customer', 'N/A'),
        "{customer_name}": recipient.get('customer_name', 'N/A'),
    }
    
    if first_item:
        replacements["{first_item}"] = first_item.item_name or first_item.item_code
        replacements["{first_item_qty}"] = str(first_item.qty if hasattr(first_item, 'qty') else first_item.transfer_qty if hasattr(first_item, 'transfer_qty') else 0)
        replacements["{first_item_uom}"] = first_item.uom if hasattr(first_item, 'uom') else first_item.stock_uom if hasattr(first_item, 'stock_uom') else ""
    
    for key, val in replacements.items():
        message = message.replace(key, str(val))
    
    return message


def get_whatsapp_template_name():
    """Get the configured WhatsApp template name."""
    try:
        if frappe.db.exists("DocType", "Material Receipt Notification Settings"):
            settings = frappe.get_single("Material Receipt Notification Settings")
            if hasattr(settings, 'whatsapp_template') and settings.whatsapp_template:
                return settings.whatsapp_template
    except:
        pass
    
    return HARDCODED_TEMPLATE


def log_notification_result(success, doc, recipients, success_list=None, failed_list=None, error_message=None):
    """Log the final result of notification process."""
    if success:
        title = f"✅ Material Receipt WhatsApp - Success ({doc.name})"
        message = f"""{'='*80}
WHATSAPP NOTIFICATION SENT SUCCESSFULLY
{'='*80}

Document: {doc.doctype} - {doc.name}
Date: {doc.posting_date if hasattr(doc, 'posting_date') else nowdate()}
Supplier: {doc.supplier if hasattr(doc, 'supplier') else 'N/A'}
Items: {len(doc.items)}

Recipients ({len(success_list) if success_list else 0}):
"""
        if success_list:
            for idx, r in enumerate(success_list, 1):
                message += f"{idx}. {r.get('name', 'Unknown')} ({r.get('mobile', 'Unknown')}) - {r.get('source', '')}\n"

    else:
        title = f"❌ Material Receipt WhatsApp - Failed ({doc.name})"
        message = f"""{'='*80}
WHATSAPP NOTIFICATION FAILED
{'='*80}

Document: {doc.doctype} - {doc.name}

{error_message if error_message else 'Unknown error occurred'}
"""
        if failed_list:
            message += f"\nFailed Recipients ({len(failed_list)}):\n"
            for idx, r in enumerate(failed_list, 1):
                name = r.get('name') or r.get('user') or 'Unknown'
                mobile = r.get('mobile') or 'Unknown'
                source = r.get('source') or 'Unknown'
                err = r.get('error') or ''
                message += f"{idx}. {name} ({mobile}) - {source}"
                if err:
                    message += f" - Error: {err}"
                message += "\n"

    # Persist log using frappe logging utilities for visibility in Desk > Error Log
    try:
        frappe.log_error(message, title)
    except Exception:
        # Fallback to printing if frappe logging fails (useful during development)
        try:
            print(title)
            print(message)
        except Exception:
            pass
