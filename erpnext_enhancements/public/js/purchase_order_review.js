frappe.ui.form.on('Purchase Order', {
    refresh(frm) {
        if (!frm.is_new()) {
            if (frm.doc.docstatus === 0) {
                // Draft state - show "Review Before Submit" button
                frm.add_custom_button('Review Before Submit', () => {
                    show_po_review_modal(frm, false); // false = editable mode
                });
            } else if (frm.doc.docstatus === 1) {
                // Submitted state - show "View Review" button
                frm.add_custom_button('View Review', () => {
                    show_po_review_modal(frm, true); // true = read-only mode
                });
            }
        }
    }
});

function show_po_review_modal(frm, isReadOnly = false) {
    frappe.call({
        method: "erpnext_enhancements.api.po_preview.render_po_review_template",
        args: {
            purchase_order: frm.doc.name,
            read_only: isReadOnly
        },  
        callback: function(response) {
            const modalConfig = {
                title: isReadOnly ? 'Purchase Order Review (Read Only)' : 'Review Purchase Order',
                size: 'extra-large',
                fields: [{
                    fieldtype: 'HTML',
                    fieldname: 'modal_html'
                }]
            };

            // Add submit functionality only for draft documents
            if (!isReadOnly) {
                modalConfig.primary_action_label = 'Submit';
                modalConfig.primary_action = () => {
                    // Collect updated data before submitting
                    const updatedData = collectUpdatedData();
                    
                    // Save the updated data if there are changes
                    if (updatedData.hasChanges) {
                        saveUpdatedData(frm, updatedData).then(() => {
                            frm.save('Submit');
                            modal.hide();
                        });
                    } else {
                        frm.save('Submit');
                        modal.hide();
                    }
                };
                modalConfig.primary_action_hidden = true;
            }

            const modal = new frappe.ui.Dialog(modalConfig);

            const html = response.message;
            modal.fields_dict.modal_html.$wrapper
                .css({ 'max-height': '60vh', 'overflow-y': 'auto' })
                .html(html);

            // Only add scroll behavior for submit button in draft mode
            if (!isReadOnly) {
                modal.$wrapper.find('.modal-body').on('scroll', function () {
                    const scrollable = this;
                    if (scrollable.scrollHeight - scrollable.scrollTop <= scrollable.clientHeight + 50) {
                        modal.set_primary_action_hidden(false);
                    }
                });
            }

            modal.show();
        }
    });
}

function collectUpdatedData() {
    const updatedData = {
        hasChanges: false,
        remarks: ''
    };

    // Collect remarks only
    const remarksTextarea = document.getElementById('po-remarks');
    if (remarksTextarea && remarksTextarea.value.trim()) {
        updatedData.remarks = remarksTextarea.value.trim();
        updatedData.hasChanges = true;
    }

    return updatedData;
}

function saveUpdatedData(frm, updatedData) {
    return new Promise((resolve, reject) => {
        // Update remarks in the current form
        if (updatedData.remarks) {
            frm.set_value('remarks', updatedData.remarks);
        }

        resolve();
    });
}


// frappe.ui.form.on('Purchase Order', {
//     refresh(frm) {
//         if (!frm.is_new() && frm.doc.docstatus === 0) {
//             frm.add_custom_button('Review Before Submit', () => {
//                 show_po_review_modal(frm);
//             });
//         }
//     }
// });

// function show_po_review_modal(frm) {
//     frappe.call({
//         method: "erpnext_enhancements.api.po_preview.render_po_review_template",
//         args: {
//             purchase_order: frm.doc.name
//         },  
//         callback: function(response) {
//             const modal = new frappe.ui.Dialog({
//                 title: 'Review Purchase Order',
//                 size: 'extra-large',
//                 primary_action_label: 'Submit',
//                 primary_action: () => {
//                     frm.save('Submit');
//                     modal.hide();
//                 },
//                 primary_action_hidden: true,
//                 fields: [{
//                     fieldtype: 'HTML',
//                     fieldname: 'modal_html'
//                 }]
//             });

//             const html = response.message;
//             modal.fields_dict.modal_html.$wrapper
//                 .css({ 'max-height': '60vh', 'overflow-y': 'auto' })
//                 .html(html);

//             modal.$wrapper.find('.modal-body').on('scroll', function () {
//                 const scrollable = this;
//                 if (scrollable.scrollHeight - scrollable.scrollTop <= scrollable.clientHeight + 50) {
//                     modal.set_primary_action_hidden(false);
//                 }
//             });

//             modal.show();
//         }
//     });
// }
