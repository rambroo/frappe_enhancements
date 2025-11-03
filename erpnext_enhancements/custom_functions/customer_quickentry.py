import frappe

def validate_mobile_no(doc, method):
    # Ensure Mobile No is mandatory
    if not doc.mobile_no:
        frappe.throw("Mobile No is mandatory for Customer.")
    
    # Check if Mobile No is unique
    existing_customer = frappe.db.get_value("Customer", 
        {"mobile_no": doc.mobile_no, "name": ["!=", doc.name]}, "name"
    )
    if existing_customer:
        frappe.throw(f"Mobile No {doc.mobile_no} is already used by Customer: <b>{existing_customer}</b>.")

    # Add "custom_sales_person" to "sales_team" child table
    if doc.custom_sales_person:
        sales_person_exists = False
        for row in doc.sales_team:
            if row.sales_person == doc.custom_sales_person:
                sales_person_exists = True
                row.allocated_percentage = 100
                break
        if not sales_person_exists:
            doc.append("sales_team", {
                "sales_person": doc.custom_sales_person,
                "allocated_percentage": 100
            })

    # Create Notification Logs for Sales Team members
    for row in doc.sales_team:
        employee_id = frappe.db.get_value("Sales Person", row.sales_person, "employee")
        if employee_id:
            user_id = frappe.db.get_value("Employee", employee_id, "user_id")
            if user_id:
                frappe.get_doc({
                    "doctype": "Notification Log",
                    "for_user": user_id,
                    "type": "Alert",
                    "document_type": "Customer",
                    "document_name": doc.name,
                    "subject": f"<b>{doc.customer_name}</b> Assigned",
                    "email_content": f"A new customer <b>{doc.customer_name}</b> has been assigned to you.",
                    "from_user": frappe.session.user,
                }).insert(ignore_permissions=True)
