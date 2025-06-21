# /home/micronext/frappe-bench/apps/erpnext_enhancements/erpnext_enhancements/api/item_search.py
# Simplified, fast, and reliable version

import frappe
from frappe.utils import cstr

@frappe.whitelist()
def custom_item_search(doctype, txt, searchfield, start, page_len, filters):
    """
    Simple and fast custom search function for Item lookup
    """
    if not txt:
        return frappe.db.sql("""
            SELECT name, item_name
            FROM `tabItem`
            WHERE disabled = 0
            ORDER BY modified DESC
            LIMIT %s OFFSET %s
        """, (page_len, start))
    
    # Clean search text
    search_text = cstr(txt).strip()
    if not search_text:
        return []
    
    # Split into terms
    search_terms = [term.strip() for term in search_text.split() if term.strip()]
    if not search_terms:
        return []
    
    # For single term, do optimized search with exact, prefix, and contains matches
    if len(search_terms) == 1:
        term = search_terms[0]
        return frappe.db.sql("""
            SELECT DISTINCT i.name, i.item_name
            FROM `tabItem` i
            LEFT JOIN `tabItem Barcode` b ON b.parent = i.name
            WHERE i.disabled = 0 
            AND (
                i.item_code = %s
                OR i.item_code LIKE %s
                OR i.item_name LIKE %s
                OR i.item_code LIKE %s
                OR i.item_name LIKE %s
                OR b.barcode LIKE %s
            )
            ORDER BY 
                CASE 
                    WHEN i.item_code = %s THEN 1
                    WHEN i.item_code LIKE %s THEN 2
                    WHEN i.item_name LIKE %s THEN 3
                    ELSE 4
                END,
                i.item_name
            LIMIT %s OFFSET %s
        """, (
            term,           # exact match
            f'{term}%',     # prefix match item_code
            f'{term}%',     # prefix match item_name  
            f'%{term}%',    # contains match item_code
            f'%{term}%',    # contains match item_name
            f'%{term}%',    # barcode match
            term,           # for ORDER BY exact
            f'{term}%',     # for ORDER BY prefix item_code
            f'{term}%',     # for ORDER BY prefix item_name
            page_len, 
            start
        ))
    
    # For multiple terms, search items that match ALL terms
    else:
        # Build WHERE conditions for multiple terms
        where_conditions = []
        params = []
        
        for term in search_terms:
            where_conditions.append("""
                (i.item_code LIKE %s OR i.item_name LIKE %s)
            """)
            params.extend([f'%{term}%', f'%{term}%'])
        
        where_clause = " AND ".join(where_conditions)
        params.extend([page_len, start])
        
        return frappe.db.sql(f"""
            SELECT DISTINCT i.name, i.item_name
            FROM `tabItem` i
            WHERE i.disabled = 0 
            AND {where_clause}
            ORDER BY i.item_name
            LIMIT %s OFFSET %s
        """, params)

# Alternative simpler version without complex logic
@frappe.whitelist()
def simple_item_search(doctype, txt, searchfield, start, page_len, filters):
    """
    Very simple but fast item search
    """
    if not txt:
        return frappe.db.sql("""
            SELECT name, item_name FROM `tabItem` 
            WHERE disabled = 0 
            ORDER BY modified DESC 
            LIMIT %s OFFSET %s
        """, (page_len, start))
    
    search_text = cstr(txt).strip()
    if len(search_text) < 2:  # Don't search for single characters
        return []
    
    # Simple search across item_code and item_name
    return frappe.db.sql("""
        SELECT DISTINCT i.name, i.item_name
        FROM `tabItem` i
        WHERE i.disabled = 0 
        AND (
            i.item_code LIKE %s 
            OR i.item_name LIKE %s
            OR EXISTS (
                SELECT 1 FROM `tabItem Barcode` b 
                WHERE b.parent = i.name AND b.barcode LIKE %s
            )
        )
        ORDER BY 
            CASE 
                WHEN i.item_code LIKE %s THEN 1
                WHEN i.item_name LIKE %s THEN 2
                ELSE 3
            END,
            i.item_name
        LIMIT %s OFFSET %s
    """, (
        f'%{search_text}%',
        f'%{search_text}%', 
        f'%{search_text}%',
        f'{search_text}%',   # prefix match for ordering
        f'{search_text}%',   # prefix match for ordering
        page_len, 
        start
    ))