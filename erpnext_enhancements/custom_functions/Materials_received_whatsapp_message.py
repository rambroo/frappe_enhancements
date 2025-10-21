import frappe
from frappe import _
from frappe.utils import nowdate, get_fullname
import json

# HARDCODED CONFIGURATION
# If you don't create the Settings DocType, these hardcoded values will be used
HARDCODED_ROLES = []  # Example: ["Purchase Manager", "Stock Manager", "RM"]
HARDCODED_TEMPLATE = None  # Example: "Material Receipt Notification" or leave None for default message


def send_material_receipt_notifications(doc, method=None):
    """
    Send WhatsApp notifications when materials are received via Purchase Receipt or Stock Entry.
    This function is triggered on document submission.
    
    Args:
        doc: The Purchase Receipt or Stock Entry document
        method: The event method (after_submit)
    """
    
    # Only process for Purchase Receipt or Stock Entry (Material Receipt type)
    if doc.doctype == "Stock Entry" and doc.stock_entry_type != "Material Receipt":
        return
    
    try:
        # Collect all unique recipients with their details
        recipients = get_all_recipients(doc)
        
        if not recipients:
            # Log failure with detailed information
            log_notification_result(
                success=False,
                doc=doc,
                recipients=[],
                error_message="No recipients found. Check:\n- Sales Order has Sales Team members\n- Sales Person is linked to Employee\n- Employee is linked to User\n- User has mobile number and is enabled"
            )
            return
        
        # Send WhatsApp message to each recipient
        success_list = []
        failed_list = []
        
        for recipient in recipients:
            try:
                send_whatsapp_to_recipient(doc, recipient)
                success_list.append(recipient)
            except Exception as e:
                recipient['error'] = str(e)
                failed_list.append(recipient)
        
        # Log final result
        log_notification_result(
            success=len(failed_list) == 0,
            doc=doc,
            recipients=recipients,
            success_list=success_list,
            failed_list=failed_list
        )
        
        frappe.db.commit()
        
    except Exception as e:
        # Log critical error
        log_notification_result(
            success=False,
            doc=doc,
            recipients=[],
            error_message=f"Critical Error: {str(e)}\n\n{frappe.get_traceback()}"
        )


def log_notification_result(success, doc, recipients, success_list=None, failed_list=None, error_message=None):
    """
    Log the final result of notification process - either success or failure.
    Only creates ONE error log with complete details.
    """
    if success:
        # SUCCESS LOG
        title = f"✅ Material Receipt WhatsApp - Success ({doc.name})"
        
        message = f"""
{'='*80}
WHATSAPP NOTIFICATION SENT SUCCESSFULLY
{'='*80}

Document Details:
- Type: {doc.doctype}
- Name: {doc.name}
- Date: {doc.posting_date if hasattr(doc, 'posting_date') else nowdate()}
- Supplier: {doc.supplier if hasattr(doc, 'supplier') else 'N/A'}
- Items: {len(doc.items)}

{'='*80}
RECIPIENTS ({len(success_list)}):
{'='*80}
"""
        
        for idx, recipient in enumerate(success_list, 1):
            message += f"""
{idx}. Name: {recipient['name']}
   User: {recipient['user']}
   Mobile: {recipient['mobile']}
   Source: {recipient['source']}
   Status: ✅ Message Sent
"""
        
        message += f"\n{'='*80}\n"
        message += f"Total Messages Sent: {len(success_list)}\n"
        message += f"{'='*80}\n"
        
    else:
        # FAILURE LOG
        title = f"❌ Material Receipt WhatsApp - Failed ({doc.name})"
        
        message = f"""
{'='*80}
WHATSAPP NOTIFICATION FAILED
{'='*80}

Document Details:
- Type: {doc.doctype}
- Name: {doc.name}
- Date: {doc.posting_date if hasattr(doc, 'posting_date') else nowdate()}
- Supplier: {doc.supplier if hasattr(doc, 'supplier') else 'N/A'}
- Items: {len(doc.items)}

"""
        
        if error_message:
            message += f"""
{'='*80}
ERROR DETAILS:
{'='*80}
{error_message}

"""
        
        if recipients:
            message += f"""
{'='*80}
RECIPIENTS FOUND ({len(recipients)}):
{'='*80}
"""
            for idx, recipient in enumerate(recipients, 1):
                message += f"""
{idx}. Name: {recipient['name']}
   User: {recipient['user']}
   Mobile: {recipient['mobile']}
   Source: {recipient['source']}
"""
            
            if failed_list:
                message += f"""
{'='*80}
FAILED TO SEND ({len(failed_list)}):
{'='*80}
"""
                for idx, recipient in enumerate(failed_list, 1):
                    message += f"""
{idx}. Name: {recipient['name']}
   Mobile: {recipient['mobile']}
   Error: {recipient.get('error', 'Unknown error')}
"""
            
            if success_list:
                message += f"""
{'='*80}
SUCCESSFULLY SENT ({len(success_list)}):
{'='*80}
"""
                for idx, recipient in enumerate(success_list, 1):
                    message += f"""
{idx}. Name: {recipient['name']} - Mobile: {recipient['mobile']}
"""
        else:
            message += f"""
{'='*80}
NO RECIPIENTS FOUND
{'='*80}

Possible Reasons:
1. Sales Order does not have Sales Team members
2. Sales Person is not linked to Employee
3. Employee is not linked to User  
4. User does not have mobile number
5. User is disabled

Item Details:
"""
            for idx, item in enumerate(doc.items, 1):
                message += f"""
{idx}. Item: {item.item_code}
   Sales Order: {item.sales_order if hasattr(item, 'sales_order') and item.sales_order else 'Not Linked'}
   Material Request: {item.material_request if hasattr(item, 'material_request') and item.material_request else 'Not Linked'}
   Purchase Order: {item.purchase_order if hasattr(item, 'purchase_order') and item.purchase_order else 'Not Linked'}
"""
        
        message += f"\n{'='*80}\n"
    
    frappe.log_error(title=title, message=message)


def get_all_recipients(doc):
    """
    Collect all unique recipients who should receive the notification.
    Returns a list of dicts with user details and their role/source.
    """
    recipients_dict = {}  # Use dict to avoid duplicates by mobile number
    
    # 1. Get recipients from Sales Team
    sales_team_recipients = get_sales_team_recipients(doc)
    for recipient in sales_team_recipients:
        if recipient['mobile']:
            recipients_dict[recipient['mobile']] = recipient
    
    # 2. Get recipient from Material Request
    mr_recipient = get_material_request_recipient(doc)
    if mr_recipient and mr_recipient['mobile']:
        if mr_recipient['mobile'] in recipients_dict:
            recipients_dict[mr_recipient['mobile']]['source'] += f", {mr_recipient['source']}"
        else:
            recipients_dict[mr_recipient['mobile']] = mr_recipient
    
    # 3. Get document creator
    creator_recipient = get_creator_recipient(doc)
    if creator_recipient and creator_recipient['mobile']:
        if creator_recipient['mobile'] in recipients_dict:
            recipients_dict[creator_recipient['mobile']]['source'] += f", {creator_recipient['source']}"
        else:
            recipients_dict[creator_recipient['mobile']] = creator_recipient
    
    # 4. Get customer contact (if linked)
    customer_recipient = get_customer_contact(doc)
    if customer_recipient and customer_recipient['mobile']:
        if customer_recipient['mobile'] in recipients_dict:
            recipients_dict[customer_recipient['mobile']]['source'] += f", {customer_recipient['source']}"
        else:
            recipients_dict[customer_recipient['mobile']] = customer_recipient
    
    # 5. Get role-based recipients
    role_recipients = get_role_based_recipients(doc)
    for recipient in role_recipients:
        if recipient['mobile']:
            if recipient['mobile'] in recipients_dict:
                recipients_dict[recipient['mobile']]['source'] += f", {recipient['source']}"
            else:
                recipients_dict[recipient['mobile']] = recipient
    
    return list(recipients_dict.values())


def get_sales_team_recipients(doc):
    """
    Get all sales persons from linked Sales Orders, Quotations, or Sales Invoices.
    """
    recipients = []
    sales_orders = set()
    quotations = set()
    sales_invoices = set()
    
    # Get linked sales documents from items
    for item in doc.get("items", []):
        # Check what fields exist in the item table
        
        # For Purchase Receipt Item
        if doc.doctype == "Purchase Receipt":
            # Check if item has sales_order field
            if hasattr(item, 'sales_order') and item.sales_order:
                sales_orders.add(item.sales_order)
            
            # Try to get sales order from Purchase Order Item
            if hasattr(item, 'purchase_order') and item.purchase_order:
                try:
                    if frappe.db.has_column("Purchase Order Item", "sales_order"):
                        po_sales_orders = frappe.db.sql("""
                            SELECT DISTINCT poi.sales_order
                            FROM `tabPurchase Order Item` poi
                            WHERE poi.parent = %s 
                            AND poi.sales_order IS NOT NULL
                            AND poi.sales_order != ''
                        """, item.purchase_order, as_dict=1)
                        for row in po_sales_orders:
                            if row.sales_order:
                                sales_orders.add(row.sales_order)
                except:
                    pass
            
            # Try to get from Material Request Item
            if hasattr(item, 'material_request') and item.material_request and hasattr(item, 'material_request_item') and item.material_request_item:
                try:
                    if frappe.db.has_column("Material Request Item", "sales_order"):
                        mr_so = frappe.db.get_value(
                            "Material Request Item",
                            item.material_request_item,
                            "sales_order"
                        )
                        if mr_so:
                            sales_orders.add(mr_so)
                except:
                    pass
        
        # For Stock Entry Detail
        elif doc.doctype == "Stock Entry":
            if hasattr(item, 'material_request') and item.material_request and hasattr(item, 'material_request_item') and item.material_request_item:
                try:
                    if frappe.db.has_column("Material Request Item", "sales_order"):
                        mr_so = frappe.db.get_value(
                            "Material Request Item",
                            item.material_request_item,
                            "sales_order"
                        )
                        if mr_so:
                            sales_orders.add(mr_so)
                except:
                    pass
        
        # Check for other sales document links
        if hasattr(item, 'quotation') and item.quotation:
            quotations.add(item.quotation)
        if hasattr(item, 'sales_invoice') and item.sales_invoice:
            sales_invoices.add(item.sales_invoice)
    
    # Collect sales team members from all linked sales documents
    all_sales_docs = []
    
    for so in sales_orders:
        all_sales_docs.append(("Sales Order", so))
    for quot in quotations:
        all_sales_docs.append(("Quotation", quot))
    for si in sales_invoices:
        all_sales_docs.append(("Sales Invoice", si))
    
    # Get sales team members from each document
    for doctype, docname in all_sales_docs:
        try:
            sales_team = frappe.get_all(
                "Sales Team",
                filters={"parent": docname, "parenttype": doctype},
                fields=["sales_person", "parent"]
            )
            
            for st in sales_team:
                if st.sales_person:
                    recipient = get_user_from_sales_person(st.sales_person, doctype, docname)
                    if recipient:
                        recipients.append(recipient)
        except:
            pass
    
    return recipients


def get_user_from_sales_person(sales_person, source_doctype, source_docname):
    """
    Get user details from Sales Person via Employee link.
    """
    try:
        # Get employee linked to sales person
        employee = frappe.db.get_value("Sales Person", sales_person, "employee")
        if not employee:
            return None
        
        # Get user linked to employee
        user = frappe.db.get_value("Employee", employee, "user_id")
        if not user:
            return None
        
        # Get user details
        user_details = frappe.db.get_value(
            "User",
            user,
            ["name", "mobile_no", "phone", "full_name", "enabled"],
            as_dict=1
        )
        
        if not user_details or not user_details.enabled:
            return None
        
        mobile = user_details.mobile_no or user_details.phone
        if not mobile:
            return None
        
        return {
            "user": user_details.name,
            "name": user_details.full_name or user_details.name,
            "mobile": mobile,
            "source": f"Sales Team ({source_doctype})",
            "sales_person": sales_person
        }
    except:
        return None


def get_material_request_recipient(doc):
    """
    Get the user who requested the material via Material Request.
    """
    try:
        material_requests = set()
        
        # Collect all material requests from items
        for item in doc.get("items", []):
            if hasattr(item, 'material_request') and item.material_request:
                material_requests.add(item.material_request)
        
        if not material_requests:
            return None
        
        # Get the first material request's owner (creator)
        for mr in material_requests:
            requester = None
            
            # Check if requested_by field exists
            if frappe.db.has_column("Material Request", "requested_by"):
                requester = frappe.db.get_value("Material Request", mr, "requested_by")
            
            # If not, use owner field
            if not requester:
                requester = frappe.db.get_value("Material Request", mr, "owner")
            
            if requester:
                user_details = frappe.db.get_value(
                    "User",
                    requester,
                    ["name", "mobile_no", "phone", "full_name", "enabled"],
                    as_dict=1
                )
                
                if user_details and user_details.enabled:
                    mobile = user_details.mobile_no or user_details.phone
                    
                    if mobile:
                        return {
                            "user": user_details.name,
                            "name": user_details.full_name or user_details.name,
                            "mobile": mobile,
                            "source": "Material Request Creator"
                        }
        
        return None
    except:
        return None


def get_creator_recipient(doc):
    """
    Get the user who created the Purchase Receipt or Stock Entry.
    """
    try:
        creator = doc.owner
        if not creator:
            return None
        
        user_details = frappe.db.get_value(
            "User",
            creator,
            ["name", "mobile_no", "phone", "full_name", "enabled"],
            as_dict=1
        )
        
        if not user_details or not user_details.enabled:
            return None
        
        mobile = user_details.mobile_no or user_details.phone
        if not mobile:
            return None
        
        return {
            "user": user_details.name,
            "name": user_details.full_name or user_details.name,
            "mobile": mobile,
            "source": f"{doc.doctype} Creator"
        }
    except:
        return None


def get_customer_contact(doc):
    """
    Get customer contact details from linked Sales Orders.
    Finds the primary contact or any contact with mobile number.
    """
    try:
        customers = set()
        
        # Get customers from linked Sales Orders
        for item in doc.get("items", []):
            # From Purchase Receipt Item
            if doc.doctype == "Purchase Receipt":
                # Direct sales order link
                if hasattr(item, 'sales_order') and item.sales_order:
                    customer = frappe.db.get_value("Sales Order", item.sales_order, "customer")
                    if customer:
                        customers.add(customer)
                
                # Via Purchase Order
                if hasattr(item, 'purchase_order') and item.purchase_order:
                    try:
                        if frappe.db.has_column("Purchase Order Item", "sales_order"):
                            po_sales_orders = frappe.db.sql("""
                                SELECT DISTINCT poi.sales_order
                                FROM `tabPurchase Order Item` poi
                                WHERE poi.parent = %s 
                                AND poi.sales_order IS NOT NULL
                            """, item.purchase_order, as_dict=1)
                            
                            for row in po_sales_orders:
                                if row.sales_order:
                                    customer = frappe.db.get_value("Sales Order", row.sales_order, "customer")
                                    if customer:
                                        customers.add(customer)
                    except:
                        pass
                
                # Via Material Request Item
                if hasattr(item, 'material_request_item') and item.material_request_item:
                    try:
                        if frappe.db.has_column("Material Request Item", "sales_order"):
                            mr_so = frappe.db.get_value(
                                "Material Request Item",
                                item.material_request_item,
                                "sales_order"
                            )
                            if mr_so:
                                customer = frappe.db.get_value("Sales Order", mr_so, "customer")
                                if customer:
                                    customers.add(customer)
                    except:
                        pass
            
            # From Stock Entry
            elif doc.doctype == "Stock Entry":
                if hasattr(item, 'material_request_item') and item.material_request_item:
                    try:
                        if frappe.db.has_column("Material Request Item", "sales_order"):
                            mr_so = frappe.db.get_value(
                                "Material Request Item",
                                item.material_request_item,
                                "sales_order"
                            )
                            if mr_so:
                                customer = frappe.db.get_value("Sales Order", mr_so, "customer")
                                if customer:
                                    customers.add(customer)
                    except:
                        pass
        
        if not customers:
            return None
        
        # Get contact for the first customer found
        for customer in customers:
            customer_name = frappe.db.get_value("Customer", customer, "customer_name")
            
            # Try to get primary contact first
            contact_name = frappe.db.get_value(
                "Dynamic Link",
                {
                    "link_doctype": "Customer",
                    "link_name": customer,
                    "parenttype": "Contact"
                },
                "parent"
            )
            
            if contact_name:
                # Get contact details
                contact_details = frappe.db.get_value(
                    "Contact",
                    contact_name,
                    ["name", "mobile_no", "phone", "first_name", "last_name"],
                    as_dict=1
                )
                
                if contact_details:
                    mobile = contact_details.mobile_no or contact_details.phone
                    
                    if mobile:
                        contact_full_name = f"{contact_details.first_name or ''} {contact_details.last_name or ''}".strip()
                        if not contact_full_name:
                            contact_full_name = contact_name
                        
                        return {
                            "user": f"Customer: {customer}",
                            "name": f"{customer_name} ({contact_full_name})",
                            "mobile": mobile,
                            "source": "Customer Contact",
                            "customer": customer,
                            "customer_name": customer_name
                        }
        
        return None
    except Exception as e:
        return None


def get_role_based_recipients(doc):
    """
    Get users with specific roles.
    First checks Settings DocType, if not found uses hardcoded roles.
    """
    recipients = []
    configured_roles = []
    
    try:
        # Try to get roles from Settings DocType
        if frappe.db.exists("DocType", "Material Receipt Notification Settings"):
            settings = frappe.get_single("Material Receipt Notification Settings")
            
            if hasattr(settings, 'notification_roles') and settings.notification_roles:
                configured_roles = [row.role for row in settings.notification_roles if row.role]
        
        # If no roles configured in settings, use hardcoded roles
        if not configured_roles:
            configured_roles = HARDCODED_ROLES
        
        # If still no roles, return empty list
        if not configured_roles:
            return []
        
        # Get users with these roles
        users_with_roles = frappe.db.sql("""
            SELECT DISTINCT u.name, u.mobile_no, u.phone, u.full_name
            FROM `tabUser` u
            INNER JOIN `tabHas Role` hr ON hr.parent = u.name
            WHERE hr.role IN %(roles)s
            AND u.enabled = 1
            AND (u.mobile_no IS NOT NULL OR u.phone IS NOT NULL)
        """, {"roles": configured_roles}, as_dict=1)
        
        for user in users_with_roles:
            mobile = user.mobile_no or user.phone
            if mobile:
                recipients.append({
                    "user": user.name,
                    "name": user.full_name or user.name,
                    "mobile": mobile,
                    "source": f"Role-Based ({', '.join(configured_roles)})"
                })
    except:
        pass
    
    return recipients


def send_whatsapp_to_recipient(doc, recipient):
    """
    Send WhatsApp message to a specific recipient with personalized content.
    """
    # Build the message
    message = build_message(doc, recipient)
    
    # Get template name
    template_name = get_whatsapp_template_name()
    
    # Send WhatsApp message using your existing system
    frappe.call(
        "erpnext_enhancements.api.whatsapp_reminders.whatsapp.send_manual_whatsapp_message",
        doctype=doc.doctype,
        docname=doc.name,
        phone_number=recipient['mobile'],
        message=message,
        template_name=template_name if template_name else None
    )


def build_message(doc, recipient):
    """
    Build personalized WhatsApp message for material receipt.
    """
    today = nowdate()
    
    # Get template if exists
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
            # Clean simple HTML
            message = message.replace("<div>", "").replace("</div>", "\n")
            message = message.replace("<p>", "").replace("</p>", "\n")
            message = message.replace("&nbsp;", " ").strip()
    
    # If no template or template not found, use default message
    if not message:
        message = build_default_message(doc, recipient)
    
    # Replace variables
    message = replace_message_variables(message, doc, recipient, today)
    
    return message


def build_default_message(doc, recipient):
    """
    Build default message template if no custom template is configured.
    """
    # Get item details
    items_text = ""
    
    for idx, item in enumerate(doc.get("items", [])[:5], 1):
        qty = item.qty if hasattr(item, 'qty') else item.transfer_qty if hasattr(item, 'transfer_qty') else 0
        uom = item.uom if hasattr(item, 'uom') else item.stock_uom if hasattr(item, 'stock_uom') else ""
        items_text += f"{idx}. {item.item_name or item.item_code}: {qty} {uom}\n"
    
    if len(doc.get("items", [])) > 5:
        items_text += f"... and {len(doc.items) - 5} more items\n"
    
    # Get linked document info with customer details
    linked_docs_text = get_linked_documents_with_customer_text(doc)
    
    # Get supplier name (for Purchase Receipt)
    supplier_text = ""
    if doc.doctype == "Purchase Receipt" and hasattr(doc, 'supplier'):
        supplier_text = f"Supplier: {doc.supplier}\n"
    
    # Build message
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


def get_linked_documents_with_customer_text(doc):
    """
    Get text of linked sales documents with customer details for display in message.
    Shows customer info only if there are sales-related documents.
    """
    linked_docs = []
    sales_orders = []
    quotations = []
    sales_invoices = []
    material_requests = []
    purchase_orders = []
    customers_info = {}
    
    # Collect all linked documents
    for item in doc.get("items", []):
        if hasattr(item, 'sales_order') and item.sales_order:
            if item.sales_order not in sales_orders:
                sales_orders.append(item.sales_order)
                # Get customer from sales order
                try:
                    customer = frappe.db.get_value("Sales Order", item.sales_order, "customer")
                    if customer and customer not in customers_info:
                        customers_info[customer] = get_customer_info(customer)
                except:
                    pass
        
        if hasattr(item, 'quotation') and item.quotation:
            if item.quotation not in quotations:
                quotations.append(item.quotation)
                # Get customer from quotation
                try:
                    customer = frappe.db.get_value("Quotation", item.quotation, "party_name")
                    if customer and customer not in customers_info:
                        customers_info[customer] = get_customer_info(customer)
                except:
                    pass
        
        if hasattr(item, 'sales_invoice') and item.sales_invoice:
            if item.sales_invoice not in sales_invoices:
                sales_invoices.append(item.sales_invoice)
                # Get customer from sales invoice
                try:
                    customer = frappe.db.get_value("Sales Invoice", item.sales_invoice, "customer")
                    if customer and customer not in customers_info:
                        customers_info[customer] = get_customer_info(customer)
                except:
                    pass
        
        if hasattr(item, 'material_request') and item.material_request:
            if item.material_request not in material_requests:
                material_requests.append(item.material_request)
        
        if hasattr(item, 'purchase_order') and item.purchase_order:
            if item.purchase_order not in purchase_orders:
                purchase_orders.append(item.purchase_order)
    
    # Build the text
    result = "Against:\n"
    
    # Show sales documents
    if sales_orders:
        result += f"Sales Order: {', '.join(sales_orders)}\n"
    
    if quotations:
        result += f"Quotation: {', '.join(quotations)}\n"
    
    if sales_invoices:
        result += f"Sales Invoice: {', '.join(sales_invoices)}\n"
    
    # Show customer details only if there are sales documents
    if customers_info:
        for customer, info in customers_info.items():
            result += f"Customer: {info['customer_name']}\n"
            if info['contact_name'] and info['mobile']:
                result += f"Customer Contact: {info['contact_name']} - {info['mobile']}\n"
    
    # Show purchase documents
    if purchase_orders:
        result += f"Purchase Order: {', '.join(purchase_orders)}\n"
    
    if material_requests:
        result += f"Material Request: {', '.join(material_requests)}\n"
    
    # If nothing is linked, return empty string
    if result == "Against:\n":
        return ""
    
    return result


def get_customer_info(customer):
    """
    Get customer name and primary contact details.
    Returns dict with customer_name, contact_name, and mobile.
    """
    info = {
        "customer_name": customer,
        "contact_name": None,
        "mobile": None
    }
    
    try:
        # Get customer name
        customer_name = frappe.db.get_value("Customer", customer, "customer_name")
        if customer_name:
            info["customer_name"] = customer_name
        
        # Get primary contact
        contact_name = frappe.db.get_value(
            "Dynamic Link",
            {
                "link_doctype": "Customer",
                "link_name": customer,
                "parenttype": "Contact"
            },
            "parent"
        )
        
        if contact_name:
            contact_details = frappe.db.get_value(
                "Contact",
                contact_name,
                ["mobile_no", "phone", "first_name", "last_name"],
                as_dict=1
            )
            
            if contact_details:
                mobile = contact_details.mobile_no or contact_details.phone
                if mobile:
                    contact_full_name = f"{contact_details.first_name or ''} {contact_details.last_name or ''}".strip()
                    info["contact_name"] = contact_full_name if contact_full_name else contact_name
                    info["mobile"] = mobile
    except:
        pass
    
    return info


def replace_message_variables(message, doc, recipient, today):
    """
    Replace all variables in the message template.
    """
    # Get first item details
    first_item = doc.items[0] if doc.items else None
    
    # Collect all linked document IDs
    sales_orders = []
    quotations = []
    material_requests = []
    purchase_orders = []
    
    for item in doc.get("items", []):
        if hasattr(item, 'sales_order') and item.sales_order:
            sales_orders.append(item.sales_order)
        if hasattr(item, 'quotation') and item.quotation:
            quotations.append(item.quotation)
        if hasattr(item, 'material_request') and item.material_request:
            material_requests.append(item.material_request)
        if hasattr(item, 'purchase_order') and item.purchase_order:
            purchase_orders.append(item.purchase_order)
    
    # Build replacements dictionary
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
        "{sales_order}": ", ".join(set(sales_orders)) if sales_orders else "N/A",
        "{quotation}": ", ".join(set(quotations)) if quotations else "N/A",
        "{material_request}": ", ".join(set(material_requests)) if material_requests else "N/A",
        "{purchase_order}": ", ".join(set(purchase_orders)) if purchase_orders else "N/A",
        "{customer}": recipient.get('customer', 'N/A'),
        "{customer_name}": recipient.get('customer_name', 'N/A'),
    }
    
    # Add first item details
    if first_item:
        replacements["{first_item}"] = first_item.item_name or first_item.item_code
        replacements["{first_item_qty}"] = str(first_item.qty if hasattr(first_item, 'qty') else first_item.transfer_qty if hasattr(first_item, 'transfer_qty') else 0)
        replacements["{first_item_uom}"] = first_item.uom if hasattr(first_item, 'uom') else first_item.stock_uom if hasattr(first_item, 'stock_uom') else ""
    
    # Perform replacements
    for key, val in replacements.items():
        message = message.replace(key, str(val))
    
    return message


def get_whatsapp_template_name():
    """
    Get the configured WhatsApp template name for material receipts.
    """
    try:
        # Check if settings exist
        if frappe.db.exists("DocType", "Material Receipt Notification Settings"):
            settings = frappe.get_single("Material Receipt Notification Settings")
            if hasattr(settings, 'whatsapp_template') and settings.whatsapp_template:
                return settings.whatsapp_template
    except:
        pass
    
    # Return hardcoded template or None
    return HARDCODED_TEMPLATE

