# File: apps/erpnext_enhancements/erpnext_enhancements/api/payment_preview.py
import frappe

@frappe.whitelist()
def render_payment_review_template(payment_entry):
    pe = frappe.get_doc("Payment Entry", payment_entry)

    # Main payment details
    payment_info = {
        "payment_entry_id": pe.name,
        "party_name": pe.party_name,
        "main_amount": pe.paid_amount if pe.payment_type == "Pay" else pe.received_amount,
        "reference_no": pe.reference_no,
        "reference_date": pe.reference_date,
        "remarks": pe.remarks,
        "posting_date": pe.posting_date,
        "payment_type": pe.payment_type,
        "company": pe.company,
        "mode_of_payment": pe.mode_of_payment,
        "party_type": pe.party_type,
        "status": pe.status,
        "paid_from": pe.paid_from,
        "paid_to": pe.paid_to,
        "paid_amount": pe.paid_amount,
        "received_amount": pe.received_amount,
        "difference_amount": pe.difference_amount,
        "total_allocated_amount": pe.total_allocated_amount,
        "unallocated_amount": pe.unallocated_amount
    }

    # Get party details if available
    party_details = {}
    if pe.party_type and pe.party:
        try:
            party_doc = frappe.get_doc(pe.party_type, pe.party)
            if pe.party_type == "Customer":
                party_details = {
                    "customer_group": getattr(party_doc, 'customer_group', None),
                    "territory": getattr(party_doc, 'territory', None),
                    "customer_type": getattr(party_doc, 'customer_type', None)
                }
            elif pe.party_type == "Supplier":
                party_details = {
                    "supplier_group": getattr(party_doc, 'supplier_group', None),
                    "supplier_type": getattr(party_doc, 'supplier_type', None)
                }
        except Exception:
            pass

    html = frappe.render_template("erpnext_enhancements/templates/includes/payment_review_modal_template.html", {
        "payment": payment_info,
        "party_details": party_details
    })

    return html