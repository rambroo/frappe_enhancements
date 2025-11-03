import frappe

@frappe.whitelist()
def get_brand_discounts(brand_list):
    if not brand_list:
        return []

    # Ensure brand_list is a Python list
    if isinstance(brand_list, str):
        import json
        brand_list = json.loads(brand_list)

    # Step 1: Fetch pricing rules that apply on "Brand"
    pricing_rules = frappe.get_all(
        "Pricing Rule",
        filters={"apply_on": "Brand", "selling": 1},
        fields=["name", "custom_default_discount_percentage","discount_percentage"]
    )

    if not pricing_rules:
        return []

    # Extract pricing rule names
    pricing_rule_names = [rule["name"] for rule in pricing_rules]

    # Step 2: Fetch brands linked to the pricing rules
    brand_rows = frappe.get_all(
        "Pricing Rule Brand",
        filters={"parent": ["in", pricing_rule_names]},
        fields=["parent", "brand"]
    )

    if not brand_rows:
        return []

    # Step 3: Map brands to their discount percentages
    brand_discounts = []
    pricing_rule_map = {rule["name"]: rule["custom_default_discount_percentage"] for rule in pricing_rules}
    pricing_rule_map1 = {rule["name"]: rule["discount_percentage"] for rule in pricing_rules}

    for row in brand_rows:
        brand_discounts.append({
            "brand": row["brand"],
            "custom_default_discount_percentage": pricing_rule_map[row["parent"]],
            "discount_percentage": pricing_rule_map1[row["parent"]]
        })

    return brand_discounts
