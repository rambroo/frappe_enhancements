// Client Script for Quotation doctype
// Add this as a Client Script in Frappe with DocType: "Quotation"

frappe.ui.form.on('Quotation', {
    refresh: function(frm) {
        applyCustomItemSearch(frm);
    }
});

function applyCustomItemSearch(frm) {
    // Apply custom search to the item_code field in the quotation items child table
    // 'items' is typically the field name for quotation items child table
    // If your child table field name is different, replace 'items' with the correct field name
    
    if (frm.fields_dict['items'] && frm.fields_dict['items'].grid) {
        frm.fields_dict['items'].grid.get_field('item_code').get_query = function(doc, cdt, cdn) {
            return {
                query: "erpnext_enhancements.api.item_search.custom_item_search", // Replace with your actual path
                filters: {
                    // You can add additional filters here if needed
                    // For example, to filter by item group or other criteria
                }
            };
        };
    }
}

// Optional: If you want to apply this to existing rows as well
frappe.ui.form.on('Quotation Item', {
    form_render: function(frm, cdt, cdn) {
        // This ensures the custom search is applied even when editing existing rows
        applyCustomItemSearch(frm);
    }
});