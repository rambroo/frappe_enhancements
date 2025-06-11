# File: apps/erpnext_enhancements/erpnext_enhancements/install.py

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def after_install():
    """Called after app installation"""
    create_custom_fields_for_purchase_order()

def create_custom_fields_for_purchase_order():
    """Create custom fields for Purchase Order"""
    
    custom_fields = {
        "Purchase Order": [
            {
                "fieldname": "remarks",
                "label": "Remarks",
                "fieldtype": "Text",
                "insert_after": "terms",
                "description": "Additional remarks for purchase order (e.g., Cash on Delivery, Special Instructions)",
                "translatable": 1,
                "no_copy": 0,
                "print_hide": 0,
                "allow_in_quick_entry": 0,
                "reqd": 0,
                "bold": 0,
                "collapsible": 0,
                "hidden": 0,
                "read_only": 0,
                "in_list_view": 0,
                "in_standard_filter": 0,
                "in_global_search": 0,
                "permlevel": 0
            }
        ]
    }
    
    try:
        create_custom_fields(custom_fields, ignore_validate=True)
        frappe.db.commit()
        print("✅ Custom field 'remarks' added to Purchase Order successfully!")
    except Exception as e:
        print(f"❌ Error creating custom field: {str(e)}")
        frappe.log_error(f"Error creating custom field: {str(e)}", "Custom Field Creation Error")