# File: apps/erpnext_enhancements/erpnext_enhancements/api/po_preview.py
import frappe
from frappe import _

@frappe.whitelist()
def render_po_review_template(purchase_order):
    po = frappe.get_doc("Purchase Order", purchase_order)

    header_info = {
        "po_id": po.name,
        "date": po.transaction_date,
        "vendor": po.supplier,
        "warehouse": po.set_warehouse or (po.items[0].warehouse if po.items else None),
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

        purchase_items.append({
            "item_name": item.item_name,
            "sku_code": item.item_code,
            "qty": item.qty,
            "unit": item.uom,
            "purchase_price_excl_tax": item.rate,
            "purchase_price_incl_tax": item.amount,
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

        advance_payment = frappe.db.sql("""
            SELECT SUM(per.allocated_amount) AS paid_amount
            FROM `tabPayment Entry Reference` per
            JOIN `tabPayment Entry` pe ON pe.name = per.parent
            WHERE per.reference_doctype = 'Sales Order'
            AND per.reference_name = %s
            AND pe.docstatus = 1
        """, (so.name,), as_dict=1)[0]

        credit_limit = frappe.db.get_value(
            "Customer Credit Limit",
            {"parent": so.customer},
            "credit_limit"
        ) or 0


        # Sum both item-level discounts and order-level discount
        item_discount_total = sum((item.discount_amount or 0) for item in so.items)
        order_discount = so.discount_amount or 0

        sales_total_discount += (item_discount_total + order_discount)

        sales_details.append({
            "order_id": so.name,
            "customer": so.customer,
            "salesman": salesperson,
            "influencer": so.sales_partner,
            "commission_value": so.commission_rate,
            "advance_amount": advance_payment.paid_amount or 0,
            "credit_limit": credit_limit,
            "overall_discount": order_discount,
            "delivery_date": so.delivery_date
        })


        sales_total_discount += so.discount_amount or 0
    total_discount=sales_total_discount + purchase_total_discount

    html = frappe.render_template("erpnext_enhancements/templates/includes/po_review_modal_template.html", {
        "header": header_info,
        "purchase_items": purchase_items,
        "sales_details": sales_details,
        "purchase_total_discount": round(purchase_total_discount, 2),
        "sales_total_discount": round(sales_total_discount, 2),
        "total_discount":round(total_discount,2)
    })

    return html
