import frappe

def get_rename_map_for_dot_zero_items():
    """
    Creates a rename_map where item codes ending with ".0" are converted
    to strings without ".0".
    """
    rename_map = {}
    
    # Use SQL for faster performance and pattern matching
    # Direct SQL: much faster for large datasets
    results = frappe.db.sql("""
        SELECT item_code FROM `tabItem`
        WHERE item_code LIKE '%.0'
    """, as_dict=True)

    for row in results:
        code = row["item_code"]
        if code.endswith(".0"):
            new_code = code[:-2]
            rename_map[code] = new_code

    return rename_map

def rename_items(rename_map):
    """
    Renames item codes based on the provided rename_map.
    """
    for old_code, new_code in rename_map.items():
        try:
            if not frappe.db.exists("Item", new_code):
                frappe.rename_doc("Item", old_code, new_code, force=True)
                frappe.db.commit()
                print(f"Renamed: {old_code} → {new_code}")
            else:
                print(f"New item code already exists: {new_code} (Skipping rename of {old_code})")
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), f"Rename failed: {old_code} to {new_code}")

def auto_rename_dot_zero_items():
    rename_map = get_rename_map_for_dot_zero_items()
    print(f"{len(rename_map)} items to rename.")
    if rename_map:
        rename_items(rename_map)
    else:
        print("No item codes ending with '.0' found.")

# from erpnext_mxt.custom_functions.rename_item import auto_rename_dot_zero_items