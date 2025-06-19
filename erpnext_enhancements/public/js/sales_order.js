// Custom extension for Sales Order to add Brand field in Purchase Order creation dialog
// Place this file in: erpnext_enhancements/public/js/sales_order.js

frappe.ui.form.on("Sales Order", {
    refresh: function(frm) {
        // Override the make_purchase_order method to include brand
        if (frm.doc.docstatus === 1) {
            setTimeout(() => {
                // Find and override the existing make_purchase_order method
                if (frm.cscript.make_purchase_order) {
                    frm.cscript.original_make_purchase_order = frm.cscript.make_purchase_order;
                    frm.cscript.make_purchase_order = function() {
                        custom_make_purchase_order(frm);
                    };
                }
            }, 1000);
        }
    }
});

function custom_make_purchase_order(frm) {
    let pending_items = frm.doc.items.some((item) => {
        let pending_qty = flt(item.stock_qty) - flt(item.ordered_qty);
        return pending_qty > 0;
    });
    
    if (!pending_items) {
        frappe.throw({
            message: __("Purchase Order already created for all Sales Order items"),
            title: __("Note"),
        });
    }

    var dialog = new frappe.ui.Dialog({
        title: __("Select Items"),
        size: "large",
        fields: [
            {
                fieldtype: "Check",
                label: __("Against Default Supplier"),
                fieldname: "against_default_supplier",
                default: 0,
            },
            {
                fieldname: "items_for_po",
                fieldtype: "Table",
                label: __("Select Items"),
                columns: 10, // Explicitly set number of columns to show
                fields: [
                    {
                        fieldtype: "Data",
                        fieldname: "item_code",
                        label: __("Item"),
                        read_only: 1,
                        in_list_view: 1,
                        columns: 2, // Set column width
                    },
                    {
                        fieldtype: "Data",
                        fieldname: "item_name",
                        label: __("Item name"),
                        read_only: 1,
                        in_list_view: 1,
                        columns: 2,
                    },
                    {
                        fieldtype: "Float",
                        fieldname: "pending_qty",
                        label: __("Pending Qty"),
                        read_only: 1,
                        in_list_view: 1,
                        columns: 1,
                    },
                    {
                        fieldtype: "Link",
                        read_only: 1,
                        fieldname: "uom",
                        label: __("UOM"),
                        in_list_view: 1,
                        columns: 1,
                    },
                    {
                        fieldtype: "Link",
                        fieldname: "brand",
                        label: __("Brand"),
                        options: "Brand",
                        read_only: 1,
                        in_list_view: 1,
                        columns: 2,
                    },
                    {
                        fieldtype: "Data",
                        fieldname: "supplier",
                        label: __("Supplier"),
                        read_only: 1,
                        in_list_view: 1,
                        columns: 2,
                    }
                ],
            },
        ],
        primary_action_label: __("Create Purchase Order"),
        primary_action(args) {
            if (!args) return;

            let selected_items = dialog.fields_dict.items_for_po.grid.get_selected_children();
            if (selected_items.length == 0) {
                frappe.throw({
                    message: "Please select Items from the Table",
                    title: __("Items Required"),
                    indicator: "blue",
                });
            }

            dialog.hide();

            var method = args.against_default_supplier
                ? "make_purchase_order_for_default_supplier"
                : "make_purchase_order";
            return frappe.call({
                method: "erpnext.selling.doctype.sales_order.sales_order." + method,
                freeze_message: __("Creating Purchase Order ..."),
                args: {
                    source_name: frm.doc.name,
                    selected_items: selected_items,
                },
                freeze: true,
                callback: function (r) {
                    if (!r.exc) {
                        if (!args.against_default_supplier) {
                            frappe.model.sync(r.message);
                            frappe.set_route("Form", r.message.doctype, r.message.name);
                        } else {
                            frappe.route_options = {
                                sales_order: frm.doc.name,
                            };
                            frappe.set_route("List", "Purchase Order");
                        }
                    }
                },
            });
        },
    });

    dialog.fields_dict["against_default_supplier"].df.onchange = () => set_po_items_data(dialog, frm);

    function set_po_items_data(dialog, frm) {
        var against_default_supplier = dialog.get_value("against_default_supplier");
        var items_for_po = dialog.get_value("items_for_po");

        if (against_default_supplier) {
            let items_with_supplier = items_for_po.filter((item) => item.supplier);
            dialog.fields_dict["items_for_po"].df.data = items_with_supplier;
            dialog.get_field("items_for_po").refresh();
        } else {
            let po_items = [];
            
            // Get brand information for each item
            frm.doc.items.forEach((d) => {
                let ordered_qty = get_ordered_qty(d, frm.doc);
                let pending_qty = (flt(d.stock_qty) - ordered_qty) / flt(d.conversion_factor);
                if (pending_qty > 0) {
                    po_items.push({
                        doctype: "Sales Order Item",
                        name: d.name,
                        item_name: d.item_name,
                        item_code: d.item_code,
                        pending_qty: pending_qty,
                        uom: d.uom,
                        supplier: d.supplier,
                        brand: d.brand || '' // Add brand from Sales Order Item
                    });
                }
            });

            dialog.fields_dict["items_for_po"].df.data = po_items;
            dialog.get_field("items_for_po").refresh();
        }
    }

    function get_ordered_qty(item, so) {
        let ordered_qty = item.ordered_qty;
        if (so.packed_items && so.packed_items.length) {
            // calculate ordered qty based on packed items in case of product bundle
            let packed_items = so.packed_items.filter((pi) => pi.parent_detail_docname == item.name);
            if (packed_items && packed_items.length) {
                ordered_qty = packed_items.reduce((sum, pi) => sum + flt(pi.ordered_qty), 0);
                ordered_qty = ordered_qty / packed_items.length;
            }
        }
        return ordered_qty;
    }

    set_po_items_data(dialog, frm);
    dialog.get_field("items_for_po").grid.only_sortable();
    dialog.get_field("items_for_po").refresh();
    dialog.wrapper.find(".grid-heading-row .grid-row-check").click();
    dialog.show();
}