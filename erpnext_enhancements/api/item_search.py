# /home/micronext/frappe-bench/apps/erpnext_enhancements/erpnext_enhancements/api/item_search.py

import frappe
import time

@frappe.whitelist()
def custom_item_search(doctype, txt, searchfield, start, page_len, filters):
    """
    Optimized search function for Item lookup that searches only in item_name field
    Priority order: exact item_name match > partial item_name match
    This version is significantly faster for large datasets (23k+ items)
    """
    # Clean and split the search text into individual words
    terms = txt.strip().split() if txt and txt.strip() else []
    
    # If no search terms, return standard query
    if not terms:
        return frappe.db.sql("""
            SELECT DISTINCT item.name, item.item_name, COALESCE(item.custom_sku_code, '') as custom_sku_code
            FROM `tabItem` item
            WHERE item.disabled = 0
            ORDER BY item.item_name
            LIMIT %s, %s
        """, (start, page_len))

    # Construct the SQL query with AND conditions for each term
    # Each term must match the item_name field
    conditions = []
    params = []
    
    for term in terms:
        conditions.append("item.item_name LIKE %s")
        params.append(f'%{term}%')
    
    where_clause = " AND ".join(conditions)
    
    # Simple query focusing only on item_name
    query = f"""
        SELECT DISTINCT item.name, item.item_name, COALESCE(item.custom_sku_code, '') as custom_sku_code
        FROM `tabItem` item
        WHERE item.disabled = 0 AND ({where_clause})
        ORDER BY 
            CASE 
                WHEN item.item_name = %s THEN 1  -- Exact match gets highest priority
                ELSE 2                           -- Partial matches
            END,
            LENGTH(item.item_name),              -- Shorter names first within same priority
            item.item_name                       -- Alphabetical within same length
        LIMIT %s, %s
    """
   
    # Prepare parameters: search params + exact match param + pagination params
    full_search_text = ' '.join(terms)  # For exact match comparison
    query_params = params + [full_search_text, start, page_len]
    
    results = frappe.db.sql(query, query_params)
    
    return results

@frappe.whitelist()
def debounced_item_search(doctype, txt, searchfield, start, page_len, filters):
    """
    Debounced version of custom_item_search - optimized for performance monitoring
    """
    start_time = time.time()
    
    # Call the main search function
    results = custom_item_search(doctype, txt, searchfield, start, page_len, filters)
    
    # Log search performance for monitoring
    end_time = time.time()
    search_duration = end_time - start_time
    
    # Log if search takes longer than 50ms (lowered threshold since this should be much faster)
    if search_duration > 0.05:
        frappe.log_error(
            f"Item search took {search_duration:.3f}s for query '{txt}' - Consider adding database index on item_name",
            "Item Search Performance"
        )
    
    return results