# apps/erpnext_enhancements/erpnext_enhancements/api/reports.py

import frappe
from frappe.desk.query_report import get_report_doc, get_report_result
from frappe.core.utils import ljust_list

@frappe.whitelist()
def get_paginated_report(report_name, filters=None, page=1, page_size=20):
    """
    Custom paginated report API with proper tuple handling
    """
    if not filters:
        filters = {}
    
    if isinstance(filters, str):
        filters = frappe.parse_json(filters)
    
    # Validate permissions
    report = get_report_doc(report_name)
    
    # Get full result from report
    res = get_report_result(report, filters) or []
    
    # Handle tuple unpacking properly using ljust_list (same as in source code)
    columns, result, message, chart, report_summary, skip_total_row = ljust_list(res, 6)
    
    # Convert columns to dict format if needed
    if columns:
        from frappe.desk.query_report import get_column_as_dict
        columns = [get_column_as_dict(col) for col in columns]
    
    # Pagination logic
    page = int(page)
    page_size = int(page_size)
    start = (page - 1) * page_size
    end = start + page_size
    
    total_records = len(result) if result else 0
    total_pages = (total_records + page_size - 1) // page_size if page_size > 0 else 0
    
    # Slice the results
    paginated_result = result[start:end] if result else []
    
    return {
        "columns": columns,
        "result": paginated_result,
        "message": message,
        "chart": chart,
        "report_summary": report_summary,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_records": total_records,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        }
    }