import frappe
from frappe import _

@frappe.whitelist()
def create_followup(reference_type, reference_name, reason, assigned_to, assigned_to_name, notes, time, due_date, quotation_status, todo_status=None):
    """
    Creates a ToDo for any document and adds a follow-up entry in its custom_follow_up_table.
    
    Args:
        reference_type: DocType (e.g., "Quotation", "Sales Order", "Opportunity")
        reference_name: Document ID
        reason: Follow-up reason
        assigned_to: User to assign the task to (email)
        assigned_to_name: Full name of assigned user
        notes: Follow-up notes
        time: Follow-up time (datetime string)
        due_date: Due date for follow-up
        quotation_status: Status for document follow-up table (Yet to start, Completed, Cancelled)
        todo_status: Status for ToDo (Open, Closed, Cancelled) - defaults to "Open"
    """

    try:
        current_user = frappe.session.user
        current_user_name = frappe.utils.get_fullname(current_user)

        # Set default statuses if not provided
        if not todo_status:
            todo_status = "Open"
        if not quotation_status:
            quotation_status = "Yet to start"

        # Log the received statuses for debugging
        frappe.log_error(
            f"Received reference_type: {reference_type}, reference_name: {reference_name}, "
            f"todo_status: {todo_status}, quotation_status: {quotation_status}", 
            "Follow-up Status Debug"
        )

        # --- Step 1: Create ToDo ---
        todo = frappe.get_doc({
            "doctype": "ToDo",
            "reference_type": reference_type,
            "reference_name": reference_name,
            "allocated_to": assigned_to,
            "description": notes or "Auto Follow-up",
            "priority": "Medium",
            "status": todo_status,
            "date": due_date,
            "assigned_by": current_user,
            "custom_follow_up": 1
        })
        todo.insert(ignore_permissions=True)

        # --- Step 2: Update Document's follow-up table ---
        doc = frappe.get_doc(reference_type, reference_name)

        followup_entry = {
            "reason": reason,
            "time": time,
            "due_date": due_date,
            "assigned_to": assigned_to,
            "assigned_to_name": assigned_to_name,
            "notes": notes,
            "status": quotation_status,  # Parsable: Yet to start, Completed, Cancelled
            "assigned_by": current_user,
            "assigned_by_name": current_user_name,
            "custom_todo_id": todo.name
        }

        # Append to custom_follow_up_table (assuming all doctypes use the same child table name)
        doc.append("custom_follow_up_table", followup_entry)
        doc.flags.ignore_validate = True  # Skip validation if needed
        doc.save(ignore_permissions=True)

        frappe.db.commit()

        return {
            "status": "success",
            "message": _("Follow-up created successfully for {0}.").format(reference_type),
            "todo_id": todo.name,
            "reference_type": reference_type,
            "reference_name": reference_name,
            "todo_status": todo_status,
            "document_status": quotation_status
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Follow-up Creation Failed")
        frappe.throw(_("An error occurred while creating the follow-up: {0}").format(str(e)))