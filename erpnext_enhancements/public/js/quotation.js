// /home/micronext/frappe-bench/apps/erpnext_enhancements/erpnext_enhancements/public/js/quotation.js

frappe.ui.form.on('Quotation', {
    refresh: function(frm) {
        applyCustomItemSearch(frm);
    },
    
    onload: function(frm) {
        // Pre-load the custom search function
        applyCustomItemSearch(frm);
    }
});

function applyCustomItemSearch(frm) {
    if (frm.fields_dict['items'] && frm.fields_dict['items'].grid) {
        const grid_field = frm.fields_dict['items'].grid.get_field('item_code');
        
        if (grid_field && !grid_field._custom_search_applied) {
            // Add debouncing to reduce API calls
            let search_timeout;
            
            grid_field.get_query = function(doc, cdt, cdn) {
                return {
                    query: "erpnext_enhancements.api.item_search.custom_item_search",
                    filters: {},
                    // Add caching and pagination
                    page_length: 20, // Reduce initial results
                    debounce: 300    // Wait 300ms before searching
                };
            };
            
            // Mark as applied to avoid multiple applications
            grid_field._custom_search_applied = true;
            
            // Add custom event handler for better UX
            $(grid_field.input).on('input', function() {
                clearTimeout(search_timeout);
                const search_val = this.value;
                
                search_timeout = setTimeout(function() {
                    if (search_val.length >= 2) { // Only search after 2 characters
                        grid_field.awesomplete.evaluate();
                    }
                }, 300);
            });
        }
    }
}

// Optimize child table rendering
frappe.ui.form.on('Quotation Item', {
    form_render: function(frm, cdt, cdn) {
        // Only apply if not already applied
        if (!frm._custom_search_initialized) {
            applyCustomItemSearch(frm);
            frm._custom_search_initialized = true;
        }
    },
    
    item_code: function(frm, cdt, cdn) {
        // Add any additional logic when item is selected
        // This runs after item selection, so it's fast
    }
});

// Add keyboard shortcuts for power users
$(document).on('keydown', '.grid-row-open .frappe-control[data-fieldname="item_code"] input', function(e) {
    // Ctrl+Space to trigger search
    if (e.ctrlKey && e.keyCode === 32) {
        e.preventDefault();
        $(this).trigger('input');
    }
});