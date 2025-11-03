import frappe

@frappe.whitelist()
def get_assigned_users(doctype, docname):
    assigned_users = frappe.get_all("ToDo", 
        filters={"reference_type": doctype, "reference_name": docname, "status": ["in", ["Open", "Closed"]]}, 
        fields=["allocated_to"]
    )
    return [user["allocated_to"] for user in assigned_users]
