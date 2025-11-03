import frappe

def update_submit_permission():
    print("Fetching all Doctypes...")  
    roles_to_update = ["Warehouse Manager"]
    reference_role = "System Manager"

    # Get all Doctypes in the system
    all_doctypes = frappe.get_all("DocType", pluck="name")
    print(f"Total Doctypes found: {len(all_doctypes)}")

    if not all_doctypes:
        print("❌ No Doctypes found!")
        return "❌ No Doctypes found!"

    for doctype in all_doctypes:
        # Get System Manager's Submit permission for this Doctype
        sys_mgr_perm = frappe.db.get_value("Custom DocPerm", 
                                           {"role": reference_role, "parent": doctype}, 
                                           "submit")

        if sys_mgr_perm is None:
            print(f"⚠️ No Submit permission found for {reference_role} in {doctype}. Skipping...")
            continue

        for role in roles_to_update:
            print(f"Updating Submit permission for {role} in {doctype} to {sys_mgr_perm}...")

            # Update submit permission for the role
            frappe.db.set_value("Custom DocPerm", 
                                {"role": role, "parent": doctype}, 
                                "submit", sys_mgr_perm)

    frappe.db.commit()
    print("✅ Submit permissions updated successfully for all Doctypes.")
    return "✅ Submit permissions updated successfully for all Doctypes."

# Run function
update_submit_permission()
