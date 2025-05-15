import requests
import frappe
import os
from frappe.utils import get_site_path, today, getdate, add_days, nowdate

def handle_whatsapp_notification(doc, method):
    frappe.log_error("Entered handle_whatsapp_notification", f"DocType: {doc.doctype}, Name: {doc.name}")

    settings = frappe.get_single("WhatsApp Settings")
    if not settings.enabled:
        frappe.log_error("WhatsApp Disabled", "Settings.disabled = True")
        return

    # Find matching DocType configuration
    matching_doctypes = [d for d in settings.whatsapp_doctypes 
                         if d.enable_whatsapp and d.table_doctype.strip() == doc.doctype]
    
    if not matching_doctypes:
        frappe.log_error("DocType not enabled for WhatsApp", doc.doctype)
        return
    
    doctype_setting = matching_doctypes[0]
    
    # Get phone number based on the selected phone_field
    if not doctype_setting.phone_field:
        frappe.log_error("No phone field configured", f"{doc.doctype} - {doc.name}")
        return
        
    receiver_id = get_phone_number(doc, doctype_setting.phone_field)
    
    if not receiver_id:
        frappe.log_error("No mobile number found", f"{doc.doctype} - {doc.name}, Field: {doctype_setting.phone_field}")
        return

    message = f"{doc.doctype} *{doc.name}* has been submitted."
    if hasattr(doc, "grand_total"):
        message += f"\nTotal Amount: ₹{doc.grand_total}"
    elif hasattr(doc, "total"):
        message += f"\nTotal Amount: ₹{doc.total}"

    message += "\n\nPlease see attached document."

    frappe.log_error("Sending WhatsApp", {
        "receiver": receiver_id,
        "message": message,
        "doctype": doc.doctype,
        "docname": doc.name
    })

    send_whatsapp_message_with_attachment(receiver_id, message, doc.doctype, doc.name)

# Helper function to get phone number from a document based on selected field
def get_phone_number(doc, phone_field):
    """
    Get phone number from document based on field path.
    Supports direct fields or dot notation for linked documents.
    
    Example:
    - "contact_mobile" - direct field
    - "supplier.mobile_no" - field from linked document
    """
    if not phone_field:
        return None
        
    parts = phone_field.strip().split('.')
    
    # Direct field on the document
    if len(parts) == 1:
        return getattr(doc, parts[0], None)
    
    # Handle linked document (e.g., supplier.mobile_no)
    try:
        # Get the linked document (e.g., "supplier")
        link_fieldname = parts[0]
        target_fieldname = parts[1]
        
        if not hasattr(doc, link_fieldname) or not getattr(doc, link_fieldname):
            return None
            
        link_doctype = doc.meta.get_field(link_fieldname).options
        link_docname = getattr(doc, link_fieldname)
        
        linked_doc = frappe.get_doc(link_doctype, link_docname)
        return getattr(linked_doc, target_fieldname, None)
        
    except Exception as e:
        frappe.log_error(f"Error getting phone number: {str(e)}", 
                        f"Path: {phone_field}, DocType: {doc.doctype}, Name: {doc.name}")
        return None

def send_whatsapp_message_with_attachment(receiver_id, message, doctype, docname, print_format="Standard"):
    """
    Send a WhatsApp message with a document PDF attachment
    """
    settings = frappe.get_single("WhatsApp Settings")

    # Step 1: Generate PDF
    try:
        pdf_content = frappe.get_print(doctype, docname, print_format=print_format, as_pdf=True)
        filename = f"{docname}.pdf"
        file_path = os.path.join(get_site_path('public', 'files'), filename)

        with open(file_path, "wb") as f:
            f.write(pdf_content)

        frappe.log_error("PDF created successfully", {"file_path": file_path})

    except Exception as e:
        frappe.log_error("PDF generation failed", str(e))
        frappe.throw("Failed to generate PDF for WhatsApp message")

    # Step 2: Send PDF as attachment to WhatsApp via BotMasterSender
    url = "https://api.botmastersender.com/api/v2/?action=send"
    files = {
        'uploadFile': open(file_path, 'rb')
    }
    data = {
        'senderId': settings.sender_id,
        'authToken': settings.auth_token,
        'messageText': message,
        'receiverId': "91" + receiver_id
    }

    response = requests.post(url, data=data, files=files)

    if response.status_code == 200:
        frappe.msgprint("WhatsApp message with PDF sent!")
    else:
        frappe.throw(f"Failed to send message. Status: {response.status_code}, Response: {response.text}")

def send_po_notification(doc, method):
    """
    Send notification when a Purchase Order is submitted
    """
    supplier = frappe.get_doc("Supplier", doc.supplier)
    receiver_id = supplier.get("mobile_no")

    if not receiver_id:
        frappe.log_error(f"No WhatsApp number set for Supplier {doc.supplier}", "PO Notification Failed")
        return

    # Check if the PO has payment schedule
    payment_details = ""
    if hasattr(doc, 'payment_schedule') and doc.payment_schedule:
        payment_details = "\n\nPayment Schedule:"
        for idx, installment in enumerate(doc.payment_schedule, 1):
            payment_details += f"\n{idx}. ₹{installment.payment_amount} due on {installment.due_date}"

    message = (f"Dear {doc.supplier_name},\n\n"
              f"Purchase Order {doc.name} has been submitted.\n"
              f"Total Amount: ₹{doc.grand_total}{payment_details}\n\n"
              f"Please see attached document for details.")
              
    send_whatsapp_message_with_attachment(receiver_id, message, "Purchase Order", doc.name)






















    # def send_po_due_reminders():
    # """
    # Scheduled function to check and send reminders for upcoming and due PO payments
    # """
    # # Find Purchase Orders with payment schedules having due dates coming up or already due
    # today_date = getdate(today())
    # upcoming_threshold = add_days(today_date, 5)  # Send reminders 5 days before due date as well
    
    # # Get all POs with payment schedules
    # pos = frappe.get_all("Purchase Order", 
    #                    filters={"docstatus": 1, "status": ["not in", ["Cancelled", "Closed"]]},
    #                    fields=["name", "supplier", "supplier_name", "grand_total"])
    
    # for po in pos:
    #     po_doc = frappe.get_doc("Purchase Order", po.name)
        
    #     # Check if payment schedule exists (payment terms have been applied)
    #     if not hasattr(po_doc, 'payment_schedule') or not po_doc.payment_schedule:
    #         continue
            
    #     for installment in po_doc.payment_schedule:
    #         due_date = getdate(installment.due_date)
            
    #         # Check if this installment is due today, overdue, or coming up within threshold
    #         if (due_date <= today_date) or (due_date <= upcoming_threshold):
    #             # Get supplier contact details
    #             supplier = frappe.get_doc("Supplier", po.supplier)
    #             mobile_no = supplier.mobile_no if hasattr(supplier, 'mobile_no') else None
                
    #             if not mobile_no:
    #                 frappe.log_error(f"No mobile number found for supplier {po.supplier}", "PO Due Reminder Failed")
    #                 continue
                
    #             # Create appropriate message based on due status
    #             if due_date < today_date:
    #                 status = "OVERDUE"
    #             elif due_date == today_date:
    #                 status = "DUE TODAY"
    #             else:
    #                 days_remaining = (due_date - today_date).days
    #                 status = f"DUE IN {days_remaining} DAYS"
                
    #             message = (f"Dear {po.supplier_name},\n\n"
    #                       f"Payment Reminder: {status}\n"
    #                       f"Purchase Order: {po.name}\n"
    #                       f"Installment Amount: ₹{installment.payment_amount}\n"
    #                       f"Due Date: {installment.due_date}\n\n"
    #                       f"Please arrange payment at your earliest convenience.\n"
    #                       f"Thank you for your business.")
                
    #             send_whatsapp_message_with_attachment(mobile_no, message, "Purchase Order", po.name)
                
    #             # Log this reminder to the PO's comment section
    #             frappe.get_doc({
    #                 "doctype": "Comment",
    #                 "comment_type": "Info",
    #                 "reference_doctype": "Purchase Order", 
    #                 "reference_name": po.name,
    #                 "content": f"Payment reminder sent on {nowdate()} for installment due on {installment.due_date}"
    #             }).insert(ignore_permissions=True)
                
    #             # Also create a timeline entry
    #             po_doc.add_comment("Info", 
    #                              f"Payment reminder sent for ₹{installment.payment_amount} due on {installment.due_date}")
