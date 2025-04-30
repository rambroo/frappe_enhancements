frappe.ui.form.on('Purchase Order', {
    refresh(frm) {
        if (!frm.is_new() && frm.doc.docstatus === 0) {
            frm.add_custom_button('Review Before Submit', () => {
                show_po_review_modal(frm);
            });
        }
    }
});

function show_po_review_modal(frm) {
    frappe.call({
        method: "erpnext_enhancements.api.po_preview.render_po_review_template",
        args: {
            purchase_order: frm.doc.name
        },
        callback: function(response) {
            const modal = new frappe.ui.Dialog({
                title: 'Review Purchase Order',
                size: 'extra-large',
                primary_action_label: 'Submit',
                primary_action: () => {
                    frm.save('Submit');
                    modal.hide();
                },
                primary_action_hidden: true,
                fields: [{
                    fieldtype: 'HTML',
                    fieldname: 'modal_html'
                }]
            });

            const html = response.message;
            modal.fields_dict.modal_html.$wrapper
                .css({ 'max-height': '60vh', 'overflow-y': 'auto' })
                .html(html);

            modal.$wrapper.find('.modal-body').on('scroll', function () {
                const scrollable = this;
                if (scrollable.scrollHeight - scrollable.scrollTop <= scrollable.clientHeight + 50) {
                    modal.set_primary_action_hidden(false);
                }
            });

            modal.show();
        }
    });
}
