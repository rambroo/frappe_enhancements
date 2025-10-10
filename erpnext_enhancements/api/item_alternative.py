# File: your_custom_app/your_module/api.py (or similar)

import frappe
from frappe import _

@frappe.whitelist()
def get_item_alternatives(item_code):
    """
    Fetch all alternative items for a given item code.
    Returns item details including product bundle components if applicable.
    """
    if not item_code:
        frappe.throw(_("Item Code is required"))
    
    # Step 1: Find direct alternatives
    direct_alternatives = frappe.get_all(
        "Item Alternative",
        filters={"item_code": item_code},
        fields=["item_code", "alternative_item_code", "two_way"]
    )
    
    # Step 2: Find two-way alternatives (where current item is alternative_item_code)
    reverse_alternatives = frappe.get_all(
        "Item Alternative",
        filters={
            "alternative_item_code": item_code,
            "two_way": 1
        },
        fields=["item_code", "alternative_item_code", "two_way"]
    )
    
    # Collect unique alternative codes
    alt_codes = set()
    for d in direct_alternatives:
        alt_codes.add(d.alternative_item_code)
    for d in reverse_alternatives:
        alt_codes.add(d.item_code)
    
    if not alt_codes:
        return {
            "items": [],
            "bundle_items": []
        }
    
    # Step 3: Fetch item details
    items = frappe.get_all(
        "Item",
        filters=[["name", "in", list(alt_codes)]],
        fields=[
            "name", "item_name", "description", 
            "standard_rate", "stock_uom", "image", "is_stock_item"
        ]
    )
    
    # Step 4: Fetch Item Prices for all items
    if items:
        item_names = [i.name for i in items]
        item_prices = frappe.get_all(
            "Item Price",
            filters=[
                ["item_code", "in", item_names],
                ["selling", "=", 1]
            ],
            fields=["item_code", "price_list_rate", "price_list", "currency"],
            order_by="creation desc"
        )
        
        # Create a price map (item_code -> price info)
        price_map = {}
        for price in item_prices:
            if price.item_code not in price_map:
                price_map[price.item_code] = {
                    "price": price.price_list_rate,
                    "price_list": price.price_list,
                    "currency": price.currency
                }
        
        # Add price information to items
        for item in items:
            if item.name in price_map:
                item.price = price_map[item.name]["price"]
                item.price_list = price_map[item.name]["price_list"]
                item.currency = price_map[item.name]["currency"]
            else:
                item.price = item.standard_rate or 0
                item.price_list = None
                item.currency = frappe.defaults.get_global_default("currency") or "INR"
    
    # Step 5: Fetch product bundle components for non-stock items
    bundle_names = [i.name for i in items if i.is_stock_item == 0]
    bundle_items = []
    
    if bundle_names:
        bundle_items = frappe.get_all(
            "Product Bundle Item",
            filters=[["parent", "in", bundle_names]],
            fields=["parent", "item_code", "qty"]
        )
    
    return {
        "items": items,
        "bundle_items": bundle_items
    }