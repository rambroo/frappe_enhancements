import frappe

@frappe.whitelist()
def search_rooms(search_term):
    """
    Search Room details with exact matches first,
    then names starting with the term, then containing the term.
    """
    # Escape single quotes in search term for SQL safety
    term = search_term.replace("'", "''")
    
    query = f"""
        SELECT name
        FROM `tabRoom details`
        WHERE name LIKE '%{term}%'
        ORDER BY
            CASE
                WHEN name = '{term}' THEN 1
                WHEN name LIKE '{term}%' THEN 2
                WHEN name LIKE '%{term}%' THEN 3
                ELSE 4
            END,
            name ASC
    """
    return frappe.db.sql(query, as_dict=True)
