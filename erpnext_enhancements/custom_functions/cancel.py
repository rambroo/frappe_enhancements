# import frappe

# def cancel_and_delete_documents(doctype_name):
#     documents = frappe.get_all(doctype_name, pluck="name")
#     print(f"Found {len(documents)} {doctype_name} records to process.")

#     count = 0  # Counter to track how many records have been deleted

#     for doc_name in documents:
#         try:
#             doc = frappe.get_doc(doctype_name, doc_name)

#             if doc.docstatus == 1:
#                 doc.cancel()
#                 print(f"Cancelled: {doc_name}")
#                 doc.delete()
#                 print(f"Deleted: {doc_name}")
#             else:
#                 doc.delete()
#                 print(f"Deleted Draft: {doc_name}")

#             count += 1

#             # Commit every 100 records
#             if count % 100 == 0:
#                 frappe.db.commit()
#                 print(f"Committed after {count} deletions.")

#         except Exception as e:
#             print(f"Error processing {doc_name}: {e}")

#     # Final commit if there are remaining uncommitted deletions
#     if count % 100 != 0:
#         frappe.db.commit()
#         print(f"Final commit after total {count} deletions.")

# # Change this to use with a different Doctype
# doctype_to_process = "Sales Order"

# # Run the function
# cancel_and_delete_documents(doctype_to_process)





# import frappe

# def delete_draft_documents(doctype_name):
#     # Fetch only draft documents
#     documents = frappe.get_all(
#         doctype_name,
#         filters={"docstatus": 0},
#         pluck="name"
#     )
#     print(f"Found {len(documents)} draft {doctype_name} records to delete.")

#     count = 0

#     for doc_name in documents:
#         try:
#             doc = frappe.get_doc(doctype_name, doc_name)
#             doc.delete()
#             print(f"Deleted Draft: {doc_name}")
#             count += 1

#             if count % 100 == 0:
#                 frappe.db.commit()
#                 print(f"Committed after {count} deletions.")

#         except Exception as e:
#             print(f"Error deleting {doc_name}: {e}")

#     if count % 100 != 0:
#         frappe.db.commit()
#         print(f"Final commit after total {count} deletions.")

# # Change this to use with a different Doctype
# doctype_to_process = "Quotation"

# # Run the function
# delete_draft_documents(doctype_to_process)


# import frappe

# def cancel_and_delete_unpaid_purchase_invoices():
#     # Step 1: Get all submitted, non-return invoices excluding %PINV%
#     filtered_invoices = frappe.get_all(
#         "Purchase Invoice",
#         filters=[
#             ["name", "not like", "%PINV%"],
#             ["is_return", "=", 0],
#             ["docstatus", "=", 1]
#         ],
#         pluck="name"
#     )

#     if not filtered_invoices:
#         print("No matching purchase invoices found.")
#         return

#     # Step 2: Get invoice names that are linked to Payment Entries
#     invoice_names_with_payments = frappe.db.sql("""
#         SELECT DISTINCT per.reference_name
#         FROM `tabPayment Entry Reference` per
#         INNER JOIN `tabPayment Entry` pe ON per.parent = pe.name
#         WHERE per.reference_doctype = 'Purchase Invoice'
#           AND pe.docstatus = 1
#     """, as_list=True)

#     paid_invoices = {row[0] for row in invoice_names_with_payments}

#     # Step 3: Find unpaid invoices from filtered list
#     unpaid_invoices = [inv for inv in filtered_invoices if inv not in paid_invoices]

#     print(f"Found {len(unpaid_invoices)} unpaid purchase invoices to cancel and delete.")

#     # Step 4: Cancel and delete them
#     for name in unpaid_invoices:
#         try:
#             pi = frappe.get_doc("Purchase Invoice", name)
#             pi.cancel()
#             pi.delete()
#             print(f"Cancelled and deleted: {name}")
#         except Exception as e:
#             print(f"Failed to process {name}: {e}")

# # Run the function
# cancel_and_delete_unpaid_purchase_invoices()
