# /home/micronext/frappe-bench/apps/erpnext_enhancements/erpnext_enhancements/api/item_search.py

import frappe
import time

@frappe.whitelist()
def custom_item_search(doctype, txt, searchfield, start, page_len, filters):
    """
    Enhanced search function for Item lookup that searches in both item_code and item_name fields
    Priority order: 
    1. Exact item_code match (highest priority)
    2. Exact item_name match 
    3. Partial item_name match (lowest priority)
    This version maintains performance for large datasets (23k+ items)
    """
    # Clean the search text
    search_text = txt.strip() if txt and txt.strip() else ""
    
    # If no search terms, return standard query
    if not search_text:
        return frappe.db.sql("""
            SELECT DISTINCT item.name, item.item_name, COALESCE(item.custom_sku_code, '') as custom_sku_code
            FROM `tabItem` item
            WHERE item.disabled = 0
            ORDER BY item.item_name
            LIMIT %s, %s
        """, (start, page_len))

    # Split search text into terms for item_name partial matching
    terms = search_text.split()
    
    # Construct conditions for partial item_name matching (all terms must match)
    name_conditions = []
    name_params = []
    
    for term in terms:
        name_conditions.append("item.item_name LIKE %s")
        name_params.append(f'%{term}%')
    
    name_where_clause = " AND ".join(name_conditions) if name_conditions else "1=1"
    
    # Enhanced query with priority-based ordering
    query = f"""
        SELECT DISTINCT item.name, item.item_name, COALESCE(item.custom_sku_code, '') as custom_sku_code
        FROM `tabItem` item
        WHERE item.disabled = 0 
        AND (
            item.item_code = %s                    -- Exact item_code match
            OR item.item_name = %s                 -- Exact item_name match
            OR ({name_where_clause})               -- Partial item_name match
        )
        ORDER BY 
            CASE 
                WHEN item.item_code = %s THEN 1    -- Exact item_code match (highest priority)
                WHEN item.item_name = %s THEN 2    -- Exact item_name match
                ELSE 3                             -- Partial item_name matches (lowest priority)
            END,
            LENGTH(item.item_name),                -- Shorter names first within same priority
            item.item_name                         -- Alphabetical within same length
        LIMIT %s, %s
    """
   
    # Prepare parameters: 
    # exact_code + exact_name + partial_name_params + exact_code_again + exact_name_again + pagination
    query_params = (
        [search_text, search_text] +           # For WHERE clause (exact matches)
        name_params +                          # For partial name matching
        [search_text, search_text] +           # For ORDER BY clause (exact matches)
        [start, page_len]                      # For pagination
    )
    
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
    
    # Log if search takes longer than 50ms
    if search_duration > 0.05:
        frappe.log_error(
            f"Item search took {search_duration:.3f}s for query '{txt}' - Results include item_code exact match and item_name exact/partial match",
            "Item Search Performance"
        )
    
    return results