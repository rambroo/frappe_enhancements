import frappe

@frappe.whitelist()
def get_uoms(item_code):
    if not frappe.has_permission("Item", "read"):
        frappe.throw("Not permitted", frappe.PermissionError)

    item = frappe.get_doc("Item", item_code)
    uoms = [{"uom": u.uom, "conversion_factor": u.conversion_factor} for u in item.uoms]
    
    return uoms
