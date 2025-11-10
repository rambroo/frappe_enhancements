import frappe

@frappe.whitelist()
def get(**kwargs):
    company = kwargs.get("company")
    from_date = kwargs.get("from_date")
    to_date = kwargs.get("to_date")
    page = int(kwargs.get("page", 1))
    page_size = int(kwargs.get("page_size", 50))

    if not company or not from_date or not to_date:
        return {
            "page": page,
            "page_size": page_size,
            "total": 0,
            "results": []
        }

    start = (page - 1) * page_size

    # ✅ Count total records
    total_query = """
        SELECT COUNT(*)
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.company = %s
        AND si.posting_date BETWEEN %s AND %s
        AND si.docstatus = 1
    """
    total = frappe.db.sql(total_query, (company, from_date, to_date))[0][0]

    # ✅ Fetch paginated results
    data_query = """
        SELECT
            sii.item_code,
            sii.item_name,
            sii.qty,
            sii.base_amount,
            si.posting_date
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE si.company = %s
        AND si.posting_date BETWEEN %s AND %s
        AND si.docstatus = 1
        ORDER BY si.posting_date DESC
        LIMIT %s OFFSET %s
    """

    results = frappe.db.sql(
        data_query,
        (company, from_date, to_date, page_size, start),
        as_dict=True,
    )

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "results": results,
    }
