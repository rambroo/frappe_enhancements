import frappe
from frappe import _

@frappe.whitelist()
def create_followup(reference_type, reference_name, reason, assigned_to, assigned_to_name, 
                    notes, time, due_date, quotation_status, assigned_by=None, todo_status=None):
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
        assigned_by: User who is assigning the task (email) - defaults to current user if not provided
        todo_status: Status for ToDo (Open, Closed, Cancelled) - defaults to "Open"
    """

    try:
        # Use provided assigned_by or fall back to current user
        if not assigned_by:
            assigned_by = frappe.session.user
        
        # Get the full name for assigned_by
        assigned_by_name = frappe.utils.get_fullname(assigned_by)

        # Set default statuses if not provided
        if not todo_status:
            todo_status = "Open"
        if not quotation_status:
            quotation_status = "Yet to start"

        # Log the received data for debugging
        frappe.log_error(
            f"Type: {reference_type}, Name: {reference_name}, "
            f"ToDo: {todo_status}, Doc: {quotation_status}, By: {assigned_by}", 
            "Follow-up Debug"
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
            "assigned_by": assigned_by,
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
            "assigned_by": assigned_by,
            "assigned_by_name": assigned_by_name,
            "custom_todo_id": todo.name
        }

        # Append to custom_follow_up_table
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
            "document_status": quotation_status,
            "assigned_by": assigned_by,
            "assigned_by_name": assigned_by_name
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Follow-up Creation Failed")
        frappe.throw(_("An error occurred while creating the follow-up: {0}").format(str(e)))