# /home/micronext/frappe-bench/apps/erpnext_enhancements/erpnext_enhancements/api/item_search.py

import frappe
import time

@frappe.whitelist()
def custom_item_search(doctype, txt, searchfield, start, page_len, filters):
    """
    Custom search function for Item lookup that searches across multiple terms
    in item_code, item_name, and custom_sku_code fields
    Priority order: exact custom_sku_code > exact item_code > partial custom_sku_code > partial item_code > item_name
    """
    # Split the search text into individual words
    terms = txt.split() if txt else []
    
    # If no search terms, return standard query
    if not terms:
        return frappe.db.sql("""
            SELECT DISTINCT item.name, item.item_name, COALESCE(item.custom_sku_code, '') as custom_sku_code
            FROM `tabItem` item
            WHERE item.disabled = 0
            LIMIT %s, %s
        """, (start, page_len))

    # Construct the SQL query with AND conditions for each term
    # Each term should match at least one of: custom_sku_code, item_code, or item_name
    conditions = []
    for term in terms:
        # Escape the term to prevent SQL injection
        escaped_term = frappe.db.escape(f'%{term}%')
        conditions.append(f"(item.custom_sku_code LIKE {escaped_term} OR item.item_code LIKE {escaped_term} OR item.item_name LIKE {escaped_term})")
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    # Execute the query with priority ordering - now including custom_sku_code in SELECT
    query = f"""
        SELECT DISTINCT item.name, item.item_name, COALESCE(item.custom_sku_code, '') as custom_sku_code
        FROM `tabItem` item
        WHERE item.disabled = 0 AND ({where_clause})
        ORDER BY 
            CASE 
                WHEN item.custom_sku_code = %s THEN 1
                WHEN item.item_code = %s THEN 2
                WHEN item.custom_sku_code LIKE %s THEN 3
                WHEN item.item_code LIKE %s THEN 4
                WHEN item.item_name LIKE %s THEN 5
                ELSE 6
            END,
            item.custom_sku_code,
            item.item_code,
            item.item_name
        LIMIT %s, %s
    """
   
    # Add parameters for ORDER BY conditions and LIMIT
    first_term = terms[0] if terms else ''
    first_term_wildcard = f'%{first_term}%' if terms else '%'
    results = frappe.db.sql(query, (first_term, first_term, first_term_wildcard, first_term_wildcard, first_term_wildcard, start, page_len))
    
    return results

@frappe.whitelist()
def debounced_item_search(doctype, txt, searchfield, start, page_len, filters):
    """
    Debounced version of custom_item_search - same functionality but optimized for debounced calls
    """
    # Add a small delay to ensure this is called after debouncing
    # This helps prevent any race conditions
    start_time = time.time()
    
    # Call the main search function
    results = custom_item_search(doctype, txt, searchfield, start, page_len, filters)
    
    # Log search performance for monitoring
    end_time = time.time()
    search_duration = end_time - start_time
    
    # Only log if search takes longer than 100ms (potential performance issue)
    if search_duration > 0.1:
        frappe.log_error(
            f"Slow item search: {search_duration:.3f}s for query '{txt}'",
            "Item Search Performance"
        )
    
    return results































# # /home/micronext/frappe-bench/apps/erpnext_enhancements/erpnext_enhancements/api/item_search.py

# import frappe
# import time

# @frappe.whitelist()
# def custom_item_search(doctype, txt, searchfield, start, page_len, filters):
#     """
#     Custom search function for Item lookup that searches across multiple terms
#     in item_code, item_name, and custom_sku_code fields
#     Priority order: exact custom_sku_code > exact item_code > partial custom_sku_code > partial item_code > item_name
#     """
#     # Split the search text into individual words
#     terms = txt.split() if txt else []
    
#     # If no search terms, return standard query
#     if not terms:
#         return frappe.db.sql("""
#             SELECT DISTINCT item.name, item.item_name
#             FROM `tabItem` item
#             WHERE item.disabled = 0
#             LIMIT %s, %s
#         """, (start, page_len))

#     # Construct the SQL query with AND conditions for each term
#     # Each term should match at least one of: custom_sku_code, item_code, or item_name
#     conditions = []
#     for term in terms:
#         # Escape the term to prevent SQL injection
#         escaped_term = frappe.db.escape(f'%{term}%')
#         conditions.append(f"(item.custom_sku_code LIKE {escaped_term} OR item.item_code LIKE {escaped_term} OR item.item_name LIKE {escaped_term})")
    
#     where_clause = " AND ".join(conditions) if conditions else "1=1"
    
#     # Execute the query with priority ordering
#     query = f"""
#         SELECT DISTINCT item.name, item.item_name
#         FROM `tabItem` item
#         WHERE item.disabled = 0 AND ({where_clause})
#         ORDER BY 
#             CASE 
#                 WHEN item.custom_sku_code = %s THEN 1
#                 WHEN item.item_code = %s THEN 2
#                 WHEN item.custom_sku_code LIKE %s THEN 3
#                 WHEN item.item_code LIKE %s THEN 4
#                 WHEN item.item_name LIKE %s THEN 5
#                 ELSE 6
#             END,
#             item.custom_sku_code,
#             item.item_code,
#             item.item_name
#         LIMIT %s, %s
#     """
   
#     # Add parameters for ORDER BY conditions and LIMIT
#     first_term = terms[0] if terms else ''
#     first_term_wildcard = f'%{first_term}%' if terms else '%'
#     results = frappe.db.sql(query, (first_term, first_term, first_term_wildcard, first_term_wildcard, first_term_wildcard, start, page_len))
    
#     return results

# @frappe.whitelist()
# def debounced_item_search(doctype, txt, searchfield, start, page_len, filters):
#     """
#     Debounced version of custom_item_search - same functionality but optimized for debounced calls
#     """
#     # Add a small delay to ensure this is called after debouncing
#     # This helps prevent any race conditions
#     start_time = time.time()
    
#     # Call the main search function
#     results = custom_item_search(doctype, txt, searchfield, start, page_len, filters)
    
#     # Log search performance for monitoring
#     end_time = time.time()
#     search_duration = end_time - start_time
    
#     # Only log if search takes longer than 100ms (potential performance issue)
#     if search_duration > 0.1:
#         frappe.log_error(
#             f"Slow item search: {search_duration:.3f}s for query '{txt}'",
#             "Item Search Performance"
#         )
    
#     return results



# import frappe

# @frappe.whitelist()
# def custom_item_search(doctype, txt, searchfield, start, page_len, filters):
#     """
#     Custom search function for Item lookup that searches across multiple terms
#     in item_code, item_name, custom_sku_code, and barcode fields
#     Priority order: custom_sku_code > item_code > item_name > barcode
#     """
#     # Split the search text into individual words
#     terms = txt.split() if txt else []
    
#     # If no search terms, return standard query
#     if not terms:
#         return frappe.db.sql("""
#             SELECT DISTINCT item.name, item.item_name
#             FROM `tabItem` item
#             WHERE item.disabled = 0
#             LIMIT %s, %s
#         """, (start, page_len))

#     # Construct the SQL query with AND conditions for each term
#     # Each term should match at least one of: custom_sku_code, item_code, item_name, or barcode
#     conditions = []
#     for term in terms:
#         # Escape the term to prevent SQL injection
#         escaped_term = frappe.db.escape(f'%{term}%')
#         conditions.append(f"(item.custom_sku_code LIKE {escaped_term} OR item.item_code LIKE {escaped_term} OR item.item_name LIKE {escaped_term} OR barcode.barcode LIKE {escaped_term})")

#     where_clause = " AND ".join(conditions) if conditions else "1=1"

#     # Execute the query with priority ordering
#     # Priority: custom_sku_code (1) > item_code (2) > item_name (3) > barcode (4)
#     query = f"""
#         SELECT DISTINCT item.name, item.item_name
#         FROM `tabItem` item
#         LEFT JOIN `tabItem Barcode` barcode ON barcode.parent = item.name
#         WHERE item.disabled = 0 AND ({where_clause})
#         ORDER BY 
#             CASE 
#                 WHEN item.custom_sku_code LIKE %s THEN 1
#                 WHEN item.item_code LIKE %s THEN 2
#                 WHEN item.item_name LIKE %s THEN 3
#                 ELSE 4
#             END,
#             item.custom_sku_code,
#             item.item_code,
#             item.item_name
#         LIMIT %s, %s
#     """
   
#     # Add parameters for ORDER BY LIKE conditions and LIMIT
#     first_term = f'%{terms[0]}%' if terms else '%'
#     results = frappe.db.sql(query, (first_term, first_term, first_term, start, page_len))
    
#     return results