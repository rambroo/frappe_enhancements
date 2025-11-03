# import frappe

# def submit_all_drafts(doctype_name):
#     # Fetch all draft documents
    # documents = frappe.get_all(doctype_name, filters=[
    #         ["name", "not like", "%PINV%"],
    #         ["is_return", "=", 0]
    #     ], pluck="name")
#     print(f"Found {len(documents)} draft {doctype_name} records to submit.")

#     count = 0  # Counter to track submitted records

#     for doc_name in documents:
#         try:
#             doc = frappe.get_doc(doctype_name, doc_name)
#             doc.submit()
#             print(f"Submitted: {doc_name}")

#             count += 1

#             # Commit every 100 submissions
#             if count % 100 == 0:
#                 frappe.db.commit()
#                 print(f"Committed after {count} submissions.")

#         except Exception as e:
#             print(f"Error submitting {doc_name}: {e}")

#     # Final commit
#     if count % 100 != 0:
#         # frappe.db.commit()
#         print(f"Final commit after total {count} submissions.")

# # Change this to use with a different Doctype
# doctype_to_process = "Purchase Invoice"  # Example Doctype, change as needed

# # Run the function
# submit_all_drafts(doctype_to_process)


# import frappe
# from frappe.model.workflow import apply_workflow

# def submit_all_with_workflow(doctype_name, workflow_action):
#     # Fetch all draft documents (docstatus = 0)
#     documents = frappe.get_all(doctype_name, filters=[
#             ["name", "not like", "%PINV%"],
#             ["is_return", "=", 0]
#         ], pluck="name")
#     print(f"Found {len(documents)} draft {doctype_name} records to process.")

#     count = 0

#     for doc_name in documents:
#         try:
#             doc = frappe.get_doc(doctype_name, doc_name)

#             # Apply the workflow action (e.g., "Submit", "Approve")
#             apply_workflow(doc, workflow_action)
#             print(f"{doc_name} → action applied: {workflow_action}")

#             count += 1

#             # Commit every 100
#             if count % 100 == 0:
#                 frappe.db.commit()
#                 print(f"Committed after {count} transitions.")

#         except Exception as e:
#             print(f"Error processing {doc_name}: {e}")

#     # Final commit
#     if count % 100 != 0:
#         frappe.db.commit()
#         print(f"Final commit after total {count} transitions.")

# # Set your workflow action name (not state name!)
# doctype_to_process = "Purchase Invoice"  # Change this to your target Doctype
# workflow_action = "Submit"  # This must match your workflow transition button/action

# submit_all_with_workflow(doctype_to_process, workflow_action)
