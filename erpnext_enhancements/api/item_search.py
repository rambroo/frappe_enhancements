# Add this to your custom app's Python file (e.g., in a utils.py file)

import frappe

@frappe.whitelist()
def custom_item_search(doctype, txt, searchfield, start, page_len, filters):
    """
    Custom search function for Item lookup that searches across multiple terms
    in item_code, item_name, and barcode fields
    """
    # Split the search text into individual words
    terms = txt.split() if txt else []
    
    # If no search terms, return standard query
    if not terms:
        return frappe.db.sql("""
            SELECT DISTINCT item.name, item.item_name
            FROM `tabItem` item
            WHERE item.disabled = 0
            LIMIT %s, %s
        """, (start, page_len))

    # Construct the SQL query with AND conditions for each term
    # Each term should match at least one of: item_code, item_name, or barcode
    conditions = []
    for term in terms:
        # Escape the term to prevent SQL injection
        escaped_term = frappe.db.escape(f'%{term}%')
        conditions.append(f"(item.item_code LIKE {escaped_term} OR item.item_name LIKE {escaped_term} OR barcode.barcode LIKE {escaped_term})")

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Execute the query and get results as tuples
    query = f"""
        SELECT DISTINCT item.name, item.item_name
        FROM `tabItem` item
        LEFT JOIN `tabItem Barcode` barcode ON barcode.parent = item.name
        WHERE item.disabled = 0 AND ({where_clause})
        ORDER BY 
            CASE 
                WHEN item.item_code LIKE %s THEN 1
                WHEN item.item_name LIKE %s THEN 2
                ELSE 3
            END,
            item.item_name
        LIMIT %s, %s
    """
   
    # Add parameters for ORDER BY LIKE conditions and LIMIT
    first_term = f'%{terms[0]}%' if terms else '%'
    results = frappe.db.sql(query, (first_term, first_term, start, page_len))
    
    return results