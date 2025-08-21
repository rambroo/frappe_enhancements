import frappe
from frappe import _

@frappe.whitelist()
def render_po_review_template(purchase_order, read_only):
    po = frappe.get_doc("Purchase Order", purchase_order)
    read_only = frappe.parse_json(read_only) if isinstance(read_only, str) else read_only

    # Get sales person from linked sales orders
    sales_persons = []
    for item in po.items:
        if item.sales_order:
            try:
                so = frappe.get_doc("Sales Order", item.sales_order)
                if so.sales_team:
                    for sales_member in so.sales_team:
                        if sales_member.sales_person and sales_member.sales_person not in sales_persons:
                            sales_persons.append(sales_member.sales_person)
            except Exception:
                continue
    
    # Format sales persons - join multiple with comma or show "-" if none
    custom_sales_person = ", ".join(sales_persons) if sales_persons else "-"

    header_info = {
        "po_id": po.name,
        "date": po.transaction_date,
        "vendor": f"{po.supplier} ({po.supplier_name})" if po.supplier_name else po.supplier,
        "warehouse": po.set_warehouse or (po.items[0].warehouse if po.items else None),
        "custom_sales_person": custom_sales_person,  # Now fetched from SO sales team
    }

    purchase_items = []
    sales_details = []
    sales_order_map = {}

    purchase_total_discount = 0
    sales_total_discount = 0

    for item in po.items:
        stock_qty = frappe.db.get_value("Bin", {
            "item_code": item.item_code,
            "warehouse": item.warehouse
        }, "actual_qty") or 0

        # Get purchase price (buying price) and selling price from Item master
        item_doc = frappe.get_doc("Item", item.item_code)
        purchase_price = item_doc.get("last_purchase_rate") or item.rate
        
        # Get selling price from Item Price or use standard_rate
        selling_price = frappe.db.get_value("Item Price", {
            "item_code": item.item_code,
            "price_list": "Standard Selling",
            "selling": 1
        }, "price_list_rate")
        
        if not selling_price:
            selling_price = item_doc.get("standard_rate") or 0

        purchase_items.append({
            "item_name": item.item_name,
            "sku_code": item.item_code,
            "qty": item.qty,
            "unit": item.uom,
            "purchase_price_excl_tax": item.rate,
            "purchase_price_incl_tax": item.amount,
            "purchase_price": purchase_price,  # New field
            "selling_price": selling_price,    # New field
            "selling_total": selling_price * item.qty,  # NEW: selling price * qty
            "discount": item.discount_percentage or 0,
            "warehouse": item.warehouse,
            "physical_stock": stock_qty,
        })

        purchase_total_discount += item.discount_amount

        if item.sales_order and item.sales_order not in sales_order_map:
            try:
                so = frappe.get_doc("Sales Order", item.sales_order)
                sales_order_map[item.sales_order] = so
            except Exception:
                continue

    for so_name, so in sales_order_map.items():
        salesperson = so.sales_team[0].sales_person if so.sales_team else None
        customer_sales_partner = frappe.db.get_value("Customer", so.customer, "default_sales_partner")

        advance_payment = frappe.db.sql("""
            SELECT COALESCE(SUM(per.allocated_amount), 0) AS paid_amount
            FROM `tabPayment Entry Reference` per
            JOIN `tabPayment Entry` pe ON pe.name = per.parent
            WHERE per.reference_doctype = 'Sales Order'
            AND per.reference_name = %s
            AND pe.docstatus = 1
            AND pe.payment_type = 'Receive'
            AND pe.party = %s
        """, (so.name, so.customer), as_dict=1)[0]
        
        credit_limit = so.custom_credit_limit_balance

        # Sum both item-level discounts and order-level discount
        item_discount_total = sum((item.discount_amount or 0) for item in so.items)
        order_discount = so.discount_amount or 0

        sales_total_discount += (item_discount_total + order_discount)
        
        # Fetch commission_rate from linked Sales Invoice
        commission_rate = None
        invoices = frappe.get_all("Sales Invoice", filters={
            "sales_order": so.name,
            "docstatus": 1
        }, fields=["name", "commission_rate"], order_by="posting_date desc")

        if invoices:
            commission_rate = invoices[0].commission_rate

        sales_details.append({
            "order_id": so.name,
            "customer": so.customer_name,
            "salesman": salesperson,
            "influencer": customer_sales_partner,
            "commission_value": commission_rate,
            "advance_amount": advance_payment.paid_amount or 0,
            "credit_limit": credit_limit,
            "overall_discount": order_discount,
            "delivery_date": so.delivery_date
        })

        sales_total_discount += so.discount_amount or 0
    
    total_discount=sales_total_discount + purchase_total_discount

    internal_remarks = po.get("custom_internal_remarks")
    custom_note = po.get("custom_note")
    custom_remarks= po.get("custom_remarks")

    html = frappe.render_template("erpnext_enhancements/templates/includes/po_review_modal_template.html", {
        "header": header_info,
        "purchase_items": purchase_items,
        "sales_details": sales_details,
        "purchase_total_discount": round(purchase_total_discount, 2),
        "sales_total_discount": round(sales_total_discount, 2),
        "total_discount": round(total_discount, 2),
        "custom_remarks": po.get("custom_remarks") or "",
        "custom_internal_remarks": po.get("custom_internal_remarks") or "",
        "custom_note": po.get("custom_note") or "",
        "read_only": read_only 

        
    })

    return html