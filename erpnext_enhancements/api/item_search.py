import frappe
import re
from functools import lru_cache
from typing import List, Dict, Any, Optional, Union

# Cache for field validation to avoid repeated lookups
@lru_cache(maxsize=1)
def get_valid_item_fields():
    """Get valid Item doctype fields from database metadata"""
    try:
        item_meta = frappe.get_meta("Item")
        return {field.fieldname for field in item_meta.fields} | {'name', 'creation', 'modified', 'owner', 'modified_by'}
    except Exception:
        # Fallback to hardcoded list if meta is not available
        return {
            'name', 'item_name', 'item_code', 'custom_sku_code', 'brand', 
            'standard_rate', 'image', 'max_discount', 'stock_uom', 'description',
            'item_group', 'disabled', 'has_variants', 'variant_of', 'creation',
            'modified', 'owner', 'modified_by'
        }

def parse_fields(fields: Union[str, List[str], None]) -> List[str]:
    """Parse and validate field list with proper error handling"""
    if not fields:
        return ['name', 'item_code', 'item_name', 'custom_sku_code', 'brand', 'standard_rate', 'image', 'max_discount', 'stock_uom']
    
    if isinstance(fields, str):
        try:
            # Try JSON parsing first
            import json
            field_list = json.loads(fields)
        except (json.JSONDecodeError, ValueError):
            # Fallback to comma-separated parsing
            field_list = [f.strip() for f in fields.split(',') if f.strip()]
    else:
        field_list = list(fields) if fields else []
    
    # Validate fields against Item doctype
    valid_fields = get_valid_item_fields()
    validated_fields = []
    
    for field in field_list:
        if field in valid_fields:
            validated_fields.append(field)
        else:
            frappe.log_error(f"Invalid field '{field}' requested in item search", "Item Search Warning")
    
    # Ensure essential fields are included for your specific use case
    essential_fields = ['name', 'item_code', 'item_name', 'custom_sku_code', 'brand', 'standard_rate', 'image', 'max_discount', 'stock_uom']
    for field in essential_fields:
        if field not in validated_fields:
            validated_fields.append(field)
    
    return validated_fields

def build_select_clause(field_list: List[str]) -> str:
    """Build SELECT clause with proper field mapping"""
    select_fields = []
    
    # Essential field mapping for clean output
    essential_mapping = {
        'name': 'item.name as name',
        'item_code': 'item.item_code as item_code', 
        'item_name': 'item.item_name as item_name',
        'custom_sku_code': "COALESCE(item.custom_sku_code, '') as custom_sku_code",
        'brand': 'item.brand as brand',
        'standard_rate': 'item.standard_rate as standard_rate',
        'image': 'item.image as image',
        'max_discount': 'item.max_discount as max_discount',
        'stock_uom': 'item.stock_uom as stock_uom'
    }
    
    # Add essential fields first to ensure they're always present
    for essential_field, essential_select in essential_mapping.items():
        if essential_field in field_list:
            select_fields.append(essential_select)
    
    # Add other requested fields
    for field in field_list:
        if field not in essential_mapping:
            select_fields.append(f"item.{field} as {field}")
    
    return "SELECT DISTINCT " + ", ".join(select_fields)

def build_search_conditions(terms: List[str]) -> Dict[str, Any]:
    """Build search conditions and parameters for different match types"""
    conditions = {}
    
    # Partial matching conditions for all terms
    def build_partial_conditions(field: str, terms: List[str]) -> tuple:
        conditions_list = [f"item.{field} LIKE %s" for _ in terms]
        params = [f'%{term}%' for term in terms]
        where_clause = " AND ".join(conditions_list) if conditions_list else "1=1"
        return where_clause, params
    
    # Build conditions for each field type
    conditions['name_where'], conditions['name_params'] = build_partial_conditions('item_name', terms)
    conditions['code_where'], conditions['code_params'] = build_partial_conditions('item_code', terms)
    conditions['sku_where'], conditions['sku_params'] = build_partial_conditions('custom_sku_code', terms)
    
    # Word boundary conditions for SKU (more precise matching)
    word_boundary_conditions = []
    word_boundary_params = []
    
    for term in terms:
        # Use word boundary regex for more precise matching
        word_boundary_conditions.append("item.custom_sku_code REGEXP %s")
        # Escape special regex characters and create word boundary pattern
        escaped_term = re.escape(term)
        word_boundary_params.append(f'(^|[^a-zA-Z0-9]){escaped_term}([^a-zA-Z0-9]|$)')
    
    conditions['word_boundary_where'] = " AND ".join(word_boundary_conditions) if word_boundary_conditions else "1=1"
    conditions['word_boundary_params'] = word_boundary_params
    
    return conditions

@frappe.whitelist()
def custom_item_search(doctype, txt, searchfield, start, page_len, filters, fields=None):
    """
    Enhanced search function for Item lookup with priority-based search
    
    Priority order: 
    1. Exact custom_sku_code match (highest priority)
    2. Exact item_code match
    3. Exact item_name match
    4. Word boundary match in custom_sku_code (complete words)
    5. Partial item_code match
    6. Partial item_name match
    7. Partial custom_sku_code match (lowest priority)
    
    Optimizations:
    - Reduced code duplication
    - Better parameter handling
    - Field validation with caching
    - More efficient query construction
    - Improved error handling
    """
    
    # Input validation and sanitization
    search_text = txt.strip() if txt and txt.strip() else ""
    start = max(0, int(start or 0))
    page_len = min(50, max(1, int(page_len or 20)))  # Limit page size for performance
    
    # Parse and validate fields
    field_list = parse_fields(fields)
    select_clause = build_select_clause(field_list)
    
    # Handle empty search - return basic results
    if not search_text:
        query = f"""
            {select_clause}
            FROM `tabItem` item
            WHERE item.disabled = 0
            ORDER BY item.item_name
            LIMIT %s, %s
        """
        try:
            results = frappe.db.sql(query, (start, page_len), as_dict=True)
            return results  # Return clean results without additional formatting
        except Exception as e:
            frappe.log_error(f"Database error in item search: {str(e)}", "Item Search Error")
            return []
    
    # Optimize search terms
    terms = [term.strip() for term in search_text.split() if term.strip()]
    if not terms:
        return []
    
    # Limit number of search terms to prevent performance issues
    terms = terms[:5]  # Limit to 5 terms maximum
    
    # Build search conditions
    conditions = build_search_conditions(terms)
    
    # Construct optimized query with proper indexing hints
    query = f"""
        {select_clause}
        FROM `tabItem` item USE INDEX (PRIMARY, modified)
        WHERE item.disabled = 0 
        AND (
            item.custom_sku_code = %s              -- 1. Exact custom_sku_code match
            OR item.item_code = %s                 -- 2. Exact item_code match  
            OR item.item_name = %s                 -- 3. Exact item_name match
            OR (item.custom_sku_code IS NOT NULL AND item.custom_sku_code != '' AND {conditions['word_boundary_where']})  -- 4. Word boundary match in SKU
            OR ({conditions['code_where']})        -- 5. Partial item_code match
            OR ({conditions['name_where']})        -- 6. Partial item_name match
            OR (item.custom_sku_code IS NOT NULL AND item.custom_sku_code != '' AND {conditions['sku_where']})  -- 7. Partial custom_sku_code match
        )
        ORDER BY 
            CASE 
                WHEN item.custom_sku_code = %s THEN 1      -- 1. Exact custom_sku_code (highest priority)
                WHEN item.item_code = %s THEN 2            -- 2. Exact item_code
                WHEN item.item_name = %s THEN 3            -- 3. Exact item_name
                WHEN item.custom_sku_code IS NOT NULL AND item.custom_sku_code != '' AND ({conditions['word_boundary_where']}) THEN 4  -- 4. Word boundary in SKU
                WHEN ({conditions['code_where']}) THEN 5   -- 5. Partial item_code
                WHEN ({conditions['name_where']}) THEN 6   -- 6. Partial item_name
                WHEN item.custom_sku_code IS NOT NULL AND item.custom_sku_code != '' AND ({conditions['sku_where']}) THEN 7  -- 7. Partial custom_sku_code
                ELSE 8
            END,
            LENGTH(COALESCE(item.item_name, '')),          -- Shorter names first within same priority
            item.item_name                                 -- Alphabetical within same length
        LIMIT %s, %s
    """
   
    # Prepare parameters efficiently
    exact_params = [search_text, search_text, search_text]
    order_params = [search_text, search_text, search_text]
    pagination_params = [start, page_len]
    
    query_params = (
        exact_params +                                      # WHERE clause exact matches
        conditions['word_boundary_params'] +                # WHERE word boundary matching
        conditions['code_params'] +                         # WHERE partial code matching
        conditions['name_params'] +                         # WHERE partial name matching  
        conditions['sku_params'] +                          # WHERE partial SKU matching
        order_params +                                      # ORDER BY exact matches
        conditions['word_boundary_params'] +                # ORDER BY word boundary matching
        conditions['code_params'] +                         # ORDER BY partial code matching
        conditions['name_params'] +                         # ORDER BY partial name matching
        conditions['sku_params'] +                          # ORDER BY partial SKU matching
        pagination_params                                   # Pagination
    )
    
    try:
        results = frappe.db.sql(query, query_params, as_dict=True)
        return results  # Return clean results without additional formatting
    except Exception as e:
        frappe.log_error(f"Database error in item search: {str(e)}", "Item Search Error")
        return []

@frappe.whitelist()
def debounced_item_search(doctype, txt, searchfield, start, page_len, filters, fields=None):
    """
    Debounced version of custom_item_search - optimized for real-time search
    
    Additional optimizations for debounced searches:
    - Reduced page size for faster response
    - Early termination for very short queries
    """
    
    # For debounced searches, use smaller page sizes for better responsiveness
    optimized_page_len = min(10, int(page_len or 10))
    
    # Skip very short queries to reduce server load
    search_text = txt.strip() if txt and txt.strip() else ""
    if search_text and len(search_text) < 2:
        return []
    
    return custom_item_search(doctype, txt, searchfield, start, optimized_page_len, filters, fields)

# Additional utility functions for maintenance

@frappe.whitelist()
def get_search_stats():
    """Get search performance statistics for monitoring"""
    try:
        stats = frappe.db.sql("""
            SELECT 
                COUNT(*) as total_items,
                COUNT(CASE WHEN custom_sku_code IS NOT NULL AND custom_sku_code != '' THEN 1 END) as items_with_sku,
                COUNT(CASE WHEN disabled = 0 THEN 1 END) as active_items
            FROM `tabItem`
        """, as_dict=True)[0]
        
        return stats
    except Exception as e:
        frappe.log_error(f"Error getting search stats: {str(e)}", "Search Stats Error")
        return {"error": "Unable to fetch statistics"}

@frappe.whitelist()  
def validate_search_indexes():
    """Validate that proper indexes exist for optimal search performance"""
    try:
        indexes = frappe.db.sql("""
            SHOW INDEX FROM `tabItem` 
            WHERE Column_name IN ('item_name', 'item_code', 'custom_sku_code', 'disabled')
        """, as_dict=True)
        
        return {
            "indexes_found": len(indexes),
            "indexes": indexes,
            "recommendations": [
                "Ensure index on (disabled, item_name) for default queries",
                "Consider index on (disabled, custom_sku_code) for SKU searches",
                "Monitor query performance with EXPLAIN"
            ]
        }
    except Exception as e:
        frappe.log_error(f"Error validating indexes: {str(e)}", "Index Validation Error")
        return {"error": "Unable to validate indexes"}