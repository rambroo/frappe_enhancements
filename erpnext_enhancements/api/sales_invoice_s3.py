import frappe
from frappe.utils.pdf import get_pdf
from frappe.utils.file_manager import save_file
import base64


def on_submit(doc, method):
    # --- DEBUG POINT 1: Entry to Hook ---
    frappe.logger("sales_invoice_pdf_hook").info(f"on_submit hook triggered for Sales Invoice: {doc.name}")

    # Get settings from ERPNext Enhancement Settings
    settings = frappe.get_single("Erpnext Enhancement Settings")
    
    # Check if si_enable_attachment is enabled
    if not settings.get("si_enable_attachment"):
        frappe.logger("sales_invoice_pdf_hook").info(
            f"si_enable_attachment is disabled in ERPNext Enhancement Settings. Skipping PDF generation for SI: {doc.name}"
        )
        return

    # --- DEBUG POINT 1.5: Setting Enabled ---
    frappe.logger("sales_invoice_pdf_hook").info(
        f"si_enable_attachment is enabled in ERPNext Enhancement Settings. Proceeding with PDF generation for SI: {doc.name}"
    )

    # Queue background job instead of running inline
    frappe.enqueue(
        "erpnext_enhancements.api.sales_invoice_s3.generate_and_upload_sales_invoice_pdf",
        sales_invoice_id=doc.name,
        queue="long"  # or "default" if you don't use multiple queues
    )
    
    # --- DEBUG POINT 2: Job Queued Confirmation ---
    frappe.logger("sales_invoice_pdf_hook").info(
        f"Background job 'generate_and_upload_sales_invoice_pdf' queued for SI: {doc.name}"
    )


def generate_and_upload_sales_invoice_pdf(sales_invoice_id):
    """
    Generate PDF for Sales Invoice and upload to S3 in background
    """
    # Use a dedicated logger for the background job
    job_logger = frappe.logger("sales_invoice_pdf_job")
    job_logger.info(f"START: generate_and_upload_sales_invoice_pdf for SI ID: {sales_invoice_id}")

    try:
        # --- DEBUG POINT 3: Fetching Document ---
        doc = frappe.get_doc("Sales Invoice", sales_invoice_id)
        job_logger.info(f"SUCCESS: Fetched Sales Invoice document {doc.name}")

        # Double-check the settings (in case it was changed after submit)
        settings = frappe.get_single("Erpnext Enhancement Settings")
        if not settings.get("si_enable_attachment"):
            job_logger.info(f"si_enable_attachment is disabled. Aborting PDF generation for SI: {doc.name}")
            return

        # Get default print format
        print_format = frappe.db.get_value(
            "Property Setter",
            {"doc_type": "Sales Invoice", "property": "default_print_format"},
            "value"
        ) or "Standard"
        
        # --- DEBUG POINT 4: Print Format Used ---
        job_logger.info(f"Print Format selected for PDF: {print_format}")

        # Generate PDF
        pdf_html = frappe.get_print(doc.doctype, doc.name, print_format=print_format)
        pdf_content = get_pdf(pdf_html)
        
        # --- DEBUG POINT 5: PDF Generation Success ---
        job_logger.info(f"SUCCESS: PDF Content generated. Size: {len(pdf_content)} bytes.")

        # Encode Sales Invoice ID to base64
        encoded_id = base64.b64encode(doc.name.encode('utf-8')).decode('utf-8')
        
        # Remove special characters from customer name for safe filename
        safe_customer_name = doc.customer.replace('/', '_').replace('\\', '_').replace(' ', '_')
        
        # Name PDF - format: CustomerName_Base64EncodedID.pdf
        file_name = f"{safe_customer_name}_{encoded_id}.pdf"
        
        # --- DEBUG POINT 6: File Name Used ---
        job_logger.info(f"Target file name: {file_name} (Original ID: {doc.name}, Encoded ID: {encoded_id})")

        # Save to File → ensure directory exists first
        import os
        file_path = frappe.get_site_path("public", "files")
        os.makedirs(file_path, exist_ok=True)
        
        # --- DEBUG POINT 6.5: Directory Created ---
        job_logger.info(f"Ensured directory exists: {file_path}")

        # Save to File without linking to specific docname to avoid nested dirs
        _file = save_file(
            file_name,
            pdf_content,
            doc.doctype,
            doc.name,
            is_private=0
        )

        # --- DEBUG POINT 7: File Upload/Save Success ---
        job_logger.info(f"SUCCESS: File saved/uploaded. File URL: {_file.file_url}")
        
        # Update the custom_pdf_url field with the generated PDF URL
        frappe.db.set_value(
            "Sales Invoice",
            sales_invoice_id,
            "custom_pdf_url",
            _file.file_url,
            update_modified=False  # Don't update modified timestamp
        )
        frappe.db.commit()
        
        # --- DEBUG POINT 7.5: URL Saved to Custom Field ---
        job_logger.info(f"SUCCESS: PDF URL saved to custom_pdf_url field: {_file.file_url}")

    except frappe.DoesNotExistError:
        # Handle the specific case where the SI might have been deleted mid-process
        frappe.log_error(
            message=f"Sales Invoice {sales_invoice_id} not found during PDF generation.",
            title="Sales Invoice Missing for PDF Job"
        )
    except Exception as e:
        # --- DEBUG POINT 8: Catch-all Error Handling (with traceback) ---
        frappe.log_error(
            message=f"Error in Sales Invoice PDF generation for SI ID {sales_invoice_id}: {str(e)}",
            title="Sales Invoice PDF Generation Failed"
        )

    # --- DEBUG POINT 9: Job Completion/Exit ---
    job_logger.info(f"END: generate_and_upload_sales_invoice_pdf for SI ID: {sales_invoice_id}")