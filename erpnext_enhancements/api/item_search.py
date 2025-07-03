import frappe
import time

@frappe.whitelist()
def custom_item_search(doctype, txt, searchfield, start, page_len, filters):
    """
    Enhanced search function for Item lookup with priority-based search
    Priority order: 
    1. Exact custom_sku_code match (highest priority)
    2. Exact item_code match
    3. Exact item_name match 
    4. Partial item_code match
    5. Partial item_name match
    6. Partial custom_sku_code match (lowest priority)
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

    # Split search text into terms for partial matching
    terms = search_text.split()
    
    # Construct conditions for partial item_name matching (all terms must match)
    name_conditions = []
    name_params = []
    
    for term in terms:
        name_conditions.append("item.item_name LIKE %s")
        name_params.append(f'%{term}%')
    
    name_where_clause = " AND ".join(name_conditions) if name_conditions else "1=1"
    
    # Construct conditions for partial item_code matching (all terms must match)
    code_conditions = []
    code_params = []
    
    for term in terms:
        code_conditions.append("item.item_code LIKE %s")
        code_params.append(f'%{term}%')
    
    code_where_clause = " AND ".join(code_conditions) if code_conditions else "1=1"
    
    # Construct conditions for partial custom_sku_code matching (all terms must match)
    sku_conditions = []
    sku_params = []
    
    for term in terms:
        sku_conditions.append("item.custom_sku_code LIKE %s")
        sku_params.append(f'%{term}%')
    
    sku_where_clause = " AND ".join(sku_conditions) if sku_conditions else "1=1"
    
    # Enhanced query with your specified priority ordering
    query = f"""
        SELECT DISTINCT item.name, item.item_name, COALESCE(item.custom_sku_code, '') as custom_sku_code
        FROM `tabItem` item
        WHERE item.disabled = 0 
        AND (
            item.custom_sku_code = %s              -- 1. Exact custom_sku_code match
            OR item.item_code = %s                 -- 2. Exact item_code match
            OR item.item_name = %s                 -- 3. Exact item_name match
            OR ({code_where_clause})               -- 4. Partial item_code match
            OR ({name_where_clause})               -- 5. Partial item_name match
            OR (item.custom_sku_code IS NOT NULL AND {sku_where_clause})  -- 6. Partial custom_sku_code match
        )
        ORDER BY 
            CASE 
                WHEN item.custom_sku_code = %s THEN 1      -- 1. Exact custom_sku_code (highest priority)
                WHEN item.item_code = %s THEN 2            -- 2. Exact item_code
                WHEN item.item_name = %s THEN 3            -- 3. Exact item_name
                WHEN ({code_where_clause}) THEN 4          -- 4. Partial item_code
                WHEN ({name_where_clause}) THEN 5          -- 5. Partial item_name
                WHEN item.custom_sku_code IS NOT NULL AND ({sku_where_clause}) THEN 6  -- 6. Partial custom_sku_code (lowest priority)
                ELSE 7
            END,
            LENGTH(COALESCE(item.item_name, '')),          -- Shorter names first within same priority
            item.item_name                                 -- Alphabetical within same length
        LIMIT %s, %s
    """
   
    # Prepare parameters in the correct order:
    # WHERE clause: exact_sku + exact_code + exact_name + partial_code_params + partial_name_params + partial_sku_params
    # ORDER BY clause: exact_sku + exact_code + exact_name + partial_code_params + partial_name_params + partial_sku_params
    # LIMIT clause: start + page_len
    query_params = (
        [search_text, search_text, search_text] +  # WHERE clause exact matches
        code_params +                              # WHERE partial code matching
        name_params +                              # WHERE partial name matching  
        sku_params +                               # WHERE partial SKU matching
        [search_text, search_text, search_text] +  # ORDER BY exact matches
        code_params +                              # ORDER BY partial code matching
        name_params +                              # ORDER BY partial name matching
        sku_params +                               # ORDER BY partial SKU matching
        [start, page_len]                          # Pagination
    )
    
    results = frappe.db.sql(query, query_params)
    
    return results

    
@frappe.whitelist()
def debounced_item_search(doctype, txt, searchfield, start, page_len, filters):
    """
    Debounced version of custom_item_search - optimized for performance
    """
    # Call the main search function directly without logging
    return custom_item_search(doctype, txt, searchfield, start, page_len, filters)