import requests
import frappe
import os
import tempfile
import re
import subprocess
from frappe.utils import get_site_path, add_days, nowdate, date_diff, formatdate
from frappe.utils.pdf import get_pdf


class WhatsAppHandler:
    """Centralized WhatsApp message handler"""
    
    def __init__(self):
        self.settings = frappe.get_single("WhatsApp Settings")
        self.api_url = "https://api.botmastersender.com/api/v2/?action=send"
    
    def is_enabled(self):
        """Check if WhatsApp is enabled and configured"""
        return (self.settings.enabled and 
                self.settings.sender_id and 
                self.settings.auth_token)
    
    def send_message(self, receiver_id, message, doctype=None, docname=None, 
                    pdf_content=None, fallback_to_text=True):
        """
        Unified method to send WhatsApp messages with or without PDF
        """
        if not self.is_enabled():
            frappe.log_error("WhatsApp not configured", "WhatsApp Settings")
            return False
        
        clean_receiver = self._clean_phone_number(receiver_id)
        if not clean_receiver:
            frappe.log_error(f"Invalid phone number: {receiver_id}", 
                           f"WhatsApp - {doctype} {docname}")
            return False
        
        # Try sending with PDF first if available
        if pdf_content:
            success = self._send_with_pdf(clean_receiver, message, docname, 
                                        pdf_content, doctype)
            if success:
                return True
        
        # Fallback to text-only if PDF fails or not available
        if fallback_to_text:
            return self._send_text_only(clean_receiver, message, doctype, docname)
        
        return False
    
    def _send_with_pdf(self, receiver_id, message, filename, pdf_content, doctype):
        """Send message with PDF attachment"""
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as temp_file:
            temp_file.write(pdf_content)
            temp_file_path = temp_file.name
        
        try:
            with open(temp_file_path, 'rb') as pdf_file:
                files = {'uploadFile': (f"{filename}.pdf", pdf_file, 'application/pdf')}
                data = {
                    'senderId': self.settings.sender_id,
                    'authToken': self.settings.auth_token,
                    'messageText': message,
                    'receiverId': f"91{receiver_id}"
                }
                
                response = requests.post(self.api_url, data=data, files=files, timeout=30)
                return self._handle_response(response, receiver_id, doctype, "PDF")
                
        except Exception as e:
            frappe.log_error(f"PDF sending failed: {str(e)}", 
                           f"WhatsApp Error - {doctype}")
            return False
        finally:
            try:
                os.unlink(temp_file_path)
            except:
                pass
    
    def _send_text_only(self, receiver_id, message, doctype, docname):
        """Send text-only message"""
        # Clean message for text-only sending
        clean_message = message.replace("Please see attached document.", 
                                      "Document details shared separately.")
        
        try:
            data = {
                'senderId': self.settings.sender_id,
                'authToken': self.settings.auth_token,
                'messageText': clean_message,
                'receiverId': f"91{receiver_id}"
            }
            
            response = requests.post(self.api_url, data=data, timeout=30)
            return self._handle_response(response, receiver_id, doctype, "Text")
            
        except Exception as e:
            frappe.log_error(f"Text sending failed: {str(e)}", 
                           f"WhatsApp Text Error - {doctype} {docname}")
            return False
    
    def _handle_response(self, response, receiver_id, doctype, msg_type):
        """Unified response handler for API calls"""
        if response.status_code != 200:
            frappe.log_error(f"API failed with status {response.status_code}: {response.text}", 
                           f"WhatsApp {msg_type} HTTP Error - {doctype}")
            return False
        
        try:
            response_data = response.json()
            if isinstance(response_data, list) and len(response_data) > 0:
                response_data = response_data[0]
            
            success_indicators = [
                response_data.get('status') == 'success' if isinstance(response_data, dict) else False,
                'success' in response.text.lower(),
                'sent' in response.text.lower(),
                response_data.get('result') == 'success' if isinstance(response_data, dict) else False
            ]
            
            if any(success_indicators):
                frappe.log_error(f"WhatsApp {msg_type} sent successfully to {receiver_id}", 
                               f"WhatsApp Success - {doctype}")
                return True
            else:
                frappe.log_error(f"API returned error: {response.text}", 
                               f"WhatsApp {msg_type} API Error - {doctype}")
                return False
                
        except ValueError:
            # Non-JSON response
            if 'success' in response.text.lower() or 'sent' in response.text.lower():
                frappe.log_error(f"WhatsApp {msg_type} sent successfully to {receiver_id}", 
                               f"WhatsApp Success - {doctype}")
                return True
            else:
                frappe.log_error(f"API returned non-JSON response: {response.text}", 
                               f"WhatsApp {msg_type} API Error - {doctype}")
                return False
    
    def _clean_phone_number(self, phone):
        """Clean and validate phone number"""
        if not phone:
            return None
        
        # Remove formatting
        phone = str(phone).strip()
        phone = re.sub(r'[^\d]', '', phone)  # Keep only digits
        
        # Remove country code
        if phone.startswith("91") and len(phone) == 12:
            phone = phone[2:]
        
        # Validate Indian mobile number
        if len(phone) == 10 and phone.isdigit() and phone[0] in ['6', '7', '8', '9']:
            return phone
        
        return None


class MessageTemplateHandler:
    """Handles message template processing and placeholder replacement"""
    
    @staticmethod
    def clean_html(text):
        """Remove HTML tags and entities from text"""
        if not text:
            return text
        
        try:
            # Remove HTML tags
            text = re.sub(r'<[^>]+>', '', text)
            
            # Replace common HTML entities
            html_entities = {
                '&nbsp;': ' ',
                '&amp;': '&',
                '&lt;': '<',
                '&gt;': '>',
                '&quot;': '"',
                '&#39;': "'"
            }
            
            for entity, replacement in html_entities.items():
                text = text.replace(entity, replacement)
            
            # Clean up whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            return text
            
        except Exception as e:
            frappe.log_error(f"Error cleaning HTML: {str(e)}", "WhatsApp HTML Cleanup")
            return text
    
    @staticmethod
    def build_message(doc, doctype_setting, is_reminder=False, target_date=None, trigger_event=None):
        """Build WhatsApp message using template or default format"""
        
        try:
            # Handle On Creation events
            if trigger_event == "On Creation":
                # Try custom template first for creation events
                if doctype_setting.custom_template:
                    template_doc = frappe.get_doc("WhatsApp Message Template", 
                                                doctype_setting.custom_template)
                    
                    if template_doc and template_doc.is_active and template_doc.template_text:
                        return MessageTemplateHandler._process_template(
                            template_doc.template_text, doc, target_date
                        )
                
                # Default creation message
                return MessageTemplateHandler._build_default_message(doc, is_reminder=False, target_date=target_date, trigger_event=trigger_event)

            # Handle On Update events
            if trigger_event == "On Update":
                # Try custom template first for update events
                if doctype_setting.custom_template:
                    template_doc = frappe.get_doc("WhatsApp Message Template", 
                                                doctype_setting.custom_template)
                    
                    if template_doc and template_doc.is_active and template_doc.template_text:
                        return MessageTemplateHandler._process_template(
                            template_doc.template_text, doc, target_date
                        )
                
                # Default update message
                return MessageTemplateHandler._build_default_message(doc, is_reminder=False, target_date=target_date, trigger_event=trigger_event)


            # Handle different trigger events
            if trigger_event == "Cancel":
                # Try custom template first for cancel events
                if doctype_setting.custom_template:
                    template_doc = frappe.get_doc("WhatsApp Message Template", 
                                                doctype_setting.custom_template)
                    
                    if template_doc and template_doc.is_active and template_doc.template_text:
                        return MessageTemplateHandler._process_template(
                            template_doc.template_text, doc, target_date
                        )
                
                # Default cancel message
                return f"{doc.doctype} *{doc.name}* has been cancelled."
            
            # Handle scheduled reminders
            if trigger_event == "Scheduled Reminder" or is_reminder:
                # Try reminder message field first
                if doctype_setting.reminder_message:
                    return MessageTemplateHandler._process_template(
                        doctype_setting.reminder_message, doc, target_date
                    )
                
                # Try custom template for reminders
                if doctype_setting.custom_template:
                    template_doc = frappe.get_doc("WhatsApp Message Template", 
                                                doctype_setting.custom_template)
                    
                    if template_doc and template_doc.is_active and template_doc.template_text:
                        return MessageTemplateHandler._process_template(
                            template_doc.template_text, doc, target_date
                        )
                
                # Default reminder message
                return MessageTemplateHandler._build_default_message(doc, is_reminder=True, target_date=target_date)
            
            # Handle Submit/Save events
            # Try custom template first
            if doctype_setting.custom_template:
                template_doc = frappe.get_doc("WhatsApp Message Template", 
                                            doctype_setting.custom_template)
                
                if template_doc and template_doc.is_active and template_doc.template_text:
                    return MessageTemplateHandler._process_template(
                        template_doc.template_text, doc, target_date
                    )
            
            # Default message for Submit/Save
            return MessageTemplateHandler._build_default_message(doc, is_reminder=False, target_date=target_date, trigger_event=trigger_event)
            
        except Exception as e:
            frappe.log_error(f"Error building message: {str(e)}", 
                           f"WhatsApp Template Error - {doc.doctype}")
            return MessageTemplateHandler._build_fallback_message(doc, is_reminder, target_date, trigger_event)


    
    @staticmethod
    def _process_template(template_text, doc, target_date=None):
        """Process template with placeholder replacement"""
        template_text = MessageTemplateHandler.clean_html(template_text)
        
        # Build placeholders dictionary
        placeholders = MessageTemplateHandler._build_placeholders(doc, target_date)
        
        # Replace placeholders
        message = template_text
        for placeholder, value in placeholders.items():
            message = message.replace(placeholder, str(value))
        
        # Handle dynamic field placeholders
        remaining_patterns = re.findall(r'\{([^}]+)\}', message)
        for pattern in remaining_patterns:
            if hasattr(doc, pattern):
                value = getattr(doc, pattern)
                if value:
                    # Format dates
                    if hasattr(value, 'strftime'):
                        try:
                            value = formatdate(value)
                        except:
                            value = str(value)
                    message = message.replace(f'{{{pattern}}}', str(value))
                else:
                    message = message.replace(f'{{{pattern}}}', "")
        
        return message
    
    @staticmethod
    def _build_placeholders(doc, target_date=None):
        """Build common placeholders dictionary"""
        placeholders = {
            '{doctype}': doc.doctype,
            '{name}': doc.name,
            '{doc_name}': doc.name,
            '{document_name}': doc.name,
        }
        
        # Amount placeholders
        amount = getattr(doc, "grand_total", None) or getattr(doc, "total", None)
        amount_str = f"₹{amount}" if amount else ""
        placeholders.update({
            '{amount}': amount_str,
            '{total}': amount_str,
            '{grand_total}': amount_str
        })
        
        # Date placeholders
        if target_date:
            placeholders.update({
                '{due_date}': str(target_date),
                '{target_date}': str(target_date),
                '{reminder_date}': str(target_date),
                '{formatted_date}': formatdate(target_date) if target_date else "",
                '{formatted_due_date}': formatdate(target_date) if target_date else ""
            })
            
            # Days calculation for reminders
            try:
                days_diff = date_diff(target_date, nowdate())
                placeholders.update({
                    '{days_remaining}': str(max(0, days_diff)),
                    '{days_left}': str(max(0, days_diff)),
                    '{day_text}': "day" if days_diff == 1 else "days" if days_diff > 1 else "today"
                })
            except:
                placeholders.update({
                    '{days_remaining}': "",
                    '{days_left}': "",
                    '{day_text}': ""
                })
        
        # Common document fields
        common_fields = ['customer', 'supplier', 'posting_date', 'due_date', 
                        'status', 'delivery_date', 'transaction_date']
        for field in common_fields:
            if hasattr(doc, field):
                value = getattr(doc, field)
                if value and hasattr(value, 'strftime'):
                    try:
                        placeholders[f'{{{field}}}'] = formatdate(value)
                    except:
                        placeholders[f'{{{field}}}'] = str(value)
                else:
                    placeholders[f'{{{field}}}'] = str(value) if value else ""
        
        return placeholders
    
    @staticmethod
    def _build_default_message(doc, is_reminder=False, target_date=None, trigger_event=None):
        """Build default message format"""
        if is_reminder or trigger_event == "Scheduled Reminder":
            if target_date:
                return f"Reminder: Your document {doc.name} is due on {target_date}."
            else:
                return f"Reminder: Your document {doc.name} requires attention."
        
        # Different messages based on trigger event
        # Different messages based on trigger event
        if trigger_event == "Submit":
            message = f"{doc.doctype} *{doc.name}* has been submitted."
        elif trigger_event == "Save":
            message = f"{doc.doctype} *{doc.name}* has been saved."
        elif trigger_event == "Cancel":
            message = f"{doc.doctype} *{doc.name}* has been cancelled."
        elif trigger_event == "On Creation":
            message = f"New {doc.doctype} *{doc.name}* has been created."
        elif trigger_event == "On Update":
            message = f"{doc.doctype} *{doc.name}* has been updated."
        else:
            message = f"{doc.doctype} *{doc.name}* has been processed."
        
        amount = getattr(doc, "grand_total", None) or getattr(doc, "total", None)
        if amount:
            message += f"\nTotal Amount: ₹{amount}"
        # Add PDF note only for non-cancel events when PDF is attached
        # Note: This is optional - you might want to pass attach_print parameter here
        # For now, keeping the existing behavior
        # Add PDF note only for non-cancel events
        if trigger_event != "Cancel":
            message += "\n\nPlease see attached document."
        
        return message
    
    @staticmethod
    def _build_fallback_message(doc, is_reminder=False, target_date=None, trigger_event=None):
        """Build basic fallback message"""
        if is_reminder or trigger_event == "Scheduled Reminder":
            if target_date:
                return f"Reminder: Document {doc.name} due on {target_date}."
            else:
                return f"Reminder: Document {doc.name} requires attention."
        
        if trigger_event == "Cancel":
            return f"{doc.doctype} {doc.name} has been cancelled."
        elif trigger_event == "Submit":
            return f"{doc.doctype} {doc.name} has been submitted."
        elif trigger_event == "Save":
            return f"{doc.doctype} {doc.name} has been saved."
        elif trigger_event == "On Creation":
            return f"New {doc.doctype} {doc.name} has been created."
        elif trigger_event == "On Update":
            return f"{doc.doctype} {doc.name} has been updated."
        else:
            return f"{doc.doctype} {doc.name} has been processed."
        

class PDFGenerator:
    """Handles PDF generation with multiple fallback methods"""
    
    @staticmethod
    def generate_pdf(doctype, docname, print_format="Standard"):
        """Generate PDF with fallback methods"""
        # Check if document is cancelled
        try:
            doc = frappe.get_doc(doctype, docname)
            if hasattr(doc, 'docstatus') and doc.docstatus == 2:
                frappe.log_error(f"Cannot generate PDF for cancelled document {docname}", 
                               f"PDF Generation - {doctype}")
                return None
        except Exception as e:
            frappe.log_error(f"Error checking document status: {str(e)}", 
                           f"PDF Generation - {doctype}")
            return None
        
        """Generate PDF using working wkhtmltopdf"""
        
        try:
            # Check if document is cancelled
            doc = frappe.get_doc(doctype, docname)
            if hasattr(doc, 'docstatus') and doc.docstatus == 2:
                return None
        except Exception as e:
            frappe.log_error(f"Error checking document: {str(e)}", f"PDF - {doctype}")
            return None
        
        try:
            # Use the working method that was working before
            html_content = frappe.get_print(doctype, docname, print_format=print_format or "Standard")
            
            # Use minimal wkhtmltopdf options
            from frappe.utils.pdf import get_pdf
            pdf_content = get_pdf(html_content, {
                'page-size': 'A4',
                'encoding': 'UTF-8'
            })
            
            if pdf_content:
                frappe.log_error("PDF generated successfully", f"PDF Success - {doctype}")
                return pdf_content
            
        except Exception as e:
            frappe.log_error(f"PDF generation failed: {str(e)}", f"PDF Error - {doctype}")
        
        
        # Try different PDF generation methods
        methods = [
            PDFGenerator._try_weasyprint,
            PDFGenerator._try_wkhtmltopdf_minimal,
            PDFGenerator._try_frappe_default
        ]
        
        for method in methods:
            try:
                pdf_content = method(doctype, docname, print_format)
                if pdf_content:
                    return pdf_content
            except Exception as e:
                frappe.log_error(f"PDF method failed: {str(e)}", 
                               f"PDF Generation - {doctype}")
                continue
        
        frappe.log_error("All PDF generation methods failed", 
                        f"PDF Generation Failed - {doctype}")
        return None
    
    @staticmethod
    def _try_weasyprint(doctype, docname, print_format):
        """Try WeasyPrint method"""
        default_format = PDFGenerator._get_default_print_format(doctype)
        html_content = frappe.get_print(doctype, docname, print_format=default_format)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', 
                                       delete=False, encoding='utf-8') as html_file:
            html_file.write(html_content)
            html_file_path = html_file.name
        
        pdf_file_path = html_file_path.replace('.html', '.pdf')
        
        try:
            subprocess.run(['weasyprint', html_file_path, pdf_file_path], 
                         check=True, capture_output=True, text=True)
            
            with open(pdf_file_path, 'rb') as pdf_file:
                pdf_content = pdf_file.read()
            
            frappe.log_error("PDF generated using WeasyPrint", 
                           f"PDF Success - {doctype}")
            return pdf_content
            
        finally:
            try:
                os.unlink(html_file_path)
                if os.path.exists(pdf_file_path):
                    os.unlink(pdf_file_path)
            except:
                pass
    
    @staticmethod
    def _try_wkhtmltopdf_minimal(doctype, docname, print_format):
        """Try wkhtmltopdf with minimal options"""
        html_content = frappe.get_print(doctype, docname, print_format=print_format)
        pdf_content = get_pdf(html_content, {
            'page-size': 'A4',
            'encoding': "UTF-8",
            'quiet': None
        })
        frappe.log_error("PDF generated using wkhtmltopdf", f"PDF Success - {doctype}")
        return pdf_content
    
    @staticmethod
    def _try_frappe_default(doctype, docname, print_format):
        """Try Frappe's default PDF generation"""
        pdf_content = frappe.get_print(doctype, docname, print_format="Standard", as_pdf=True)
        frappe.log_error("PDF generated using Frappe default", f"PDF Success - {doctype}")
        return pdf_content
    
    @staticmethod
    def _get_default_print_format(doctype):
        """Get default print format for doctype"""
        default_format = frappe.db.get_value("Property Setter", {
            "doctype_or_field": "DocType",
            "doc_type": doctype,
            "property": "default_print_format"
        }, "value")
        return default_format or "Standard"


def get_phone_number(doc, phone_field):
    """Get phone number from document with support for linked fields"""
    if not phone_field:
        return None
    
    parts = phone_field.strip().split('.')
    
    # Direct field
    if len(parts) == 1:
        phone = getattr(doc, parts[0], None)
        return WhatsAppHandler()._clean_phone_number(phone)
    
    # Linked field (e.g., supplier.mobile_no)
    if len(parts) == 2:
        try:
            link_fieldname, target_fieldname = parts
            link_docname = getattr(doc, link_fieldname, None)
            
            if not link_docname:
                return None
            
            link_field = doc.meta.get_field(link_fieldname)
            if not link_field or not link_field.options:
                return None
            
            linked_doc = frappe.get_doc(link_field.options, link_docname)
            phone = getattr(linked_doc, target_fieldname, None)
            return WhatsAppHandler()._clean_phone_number(phone)
            
        except Exception as e:
            frappe.log_error(f"Error getting phone number: {str(e)}", 
                           f"Phone Field Error - {doc.doctype}")
            return None
    
    return None


def send_scheduled_whatsapp_reminders():
    """Main function to send scheduled WhatsApp reminders"""
    settings = frappe.get_single("WhatsApp Settings")
    if not settings.enabled:
        frappe.log_error("WhatsApp reminders skipped", "WhatsApp Settings disabled")
        return

    # Get all scheduled reminder configurations
    scheduled_configs = [
        config for config in settings.whatsapp_doctypes
        if (config.schedule_enabled and 
            config.enable_whatsapp and
            config.trigger_event == "Scheduled Reminder" and
            config.date_field)
    ]

    for doctype_config in scheduled_configs:
        try:
            process_scheduled_whatsapp_reminder(doctype_config)
        except Exception as e:
            error_msg = f"Scheduler failed for {doctype_config.table_doctype}: {str(e)}"
            frappe.log_error(error_msg, f"WhatsApp Scheduler Error")
            continue



def process_scheduled_whatsapp_reminder(config):
    """Process scheduled reminders for a specific doctype configuration"""
    date_field = config.date_field
    
    # Calculate target date based on trigger timing
    if config.trigger_timing == "Days Before":
        target_date = add_days(nowdate(), config.days_before or 0)
    elif config.trigger_timing == "Days After":
        target_date = add_days(nowdate(), -(config.days_after or 0))
    else:
        # Default to current date for immediate scheduled reminders
        target_date = nowdate()
    
    filters = {f"{date_field}": target_date}
    
    # Exclude cancelled documents for submittable doctypes
    submittable_doctypes = ["Purchase Order", "Sales Order", 
                           "Purchase Invoice", "Sales Invoice", 
                           "Delivery Note", "Purchase Receipt"]
    
    if config.table_doctype in submittable_doctypes:
        filters["docstatus"] = ["!=", 2]
    
    docs = frappe.get_all(
        config.table_doctype, 
        filters=filters, 
        fields=["name", "docstatus"] if config.table_doctype in submittable_doctypes else ["name"]
    )

    whatsapp_handler = WhatsAppHandler()
    success_count = error_count = 0

    for d in docs:
        try:
            # Skip cancelled documents
            if hasattr(d, 'docstatus') and d.docstatus == 2:
                continue
                
            doc = frappe.get_doc(config.table_doctype, d.name)
            
            if hasattr(doc, 'docstatus') and doc.docstatus == 2:
                continue
            
            phone = get_phone_number_enhanced(doc, config.phone_field)
            if not phone:
                error_count += 1
                continue

            # Build message for scheduled reminder
            message = MessageTemplateHandler.build_message(
                doc, config, 
                is_reminder=True, 
                target_date=target_date,
                trigger_event="Scheduled Reminder"
            )
            
            # Try with PDF attachment
            # Generate PDF only if attach_print is enabled
            pdf_content = None
            if config.attach_print:
                pdf_content = PDFGenerator.generate_pdf(doc.doctype, doc.name)
            # pdf_content = PDFGenerator.generate_pdf(doc.doctype, doc.name)


            
            if whatsapp_handler.send_message(phone, message, doc.doctype, doc.name, 
                                           pdf_content, fallback_to_text=True):
                success_count += 1
            else:
                error_count += 1
                
        except Exception as e:
            frappe.log_error(f"Failed to process reminder for {d.name}: {str(e)}", 
                           f"WhatsApp Reminder Error")
            error_count += 1

    # Log summary
    if success_count > 0 or error_count > 0:
        frappe.log_error(
            f"Reminders processed - Success: {success_count}, Errors: {error_count}", 
            f"WhatsApp Reminder Summary - {config.table_doctype}"
        )



def handle_whatsapp_notification_submit(doc, method):
    """Handle WhatsApp notification for submitted documents"""
    _handle_whatsapp_notification(doc, method, "Submit")


def handle_whatsapp_notification_save(doc, method):
    """Handle WhatsApp notification for saved documents (before_save)"""
    _handle_whatsapp_notification(doc, method, "Save")


def handle_whatsapp_notification_cancel(doc, method):
    """Handle WhatsApp notification for cancelled documents"""
    _handle_whatsapp_notification(doc, method, "Cancel")

def handle_whatsapp_notification_creation(doc, method):
    """Handle WhatsApp notification for newly created documents"""
    _handle_whatsapp_notification(doc, method, "On Creation")


def handle_whatsapp_notification_update(doc, method):
    """Handle WhatsApp notification for updated documents (excluding new documents)"""
    # Skip if this is a new document
    if doc.is_new():
        return
    _handle_whatsapp_notification(doc, method, "On Update")



def _handle_whatsapp_notification(doc, method, trigger_event):
    """Unified WhatsApp notification handler"""
    try:
        settings = frappe.get_single("WhatsApp Settings")
        if not settings.enabled:
            return

        # Find matching DocType configurations for this trigger event
        matching_configs = [
            d for d in settings.whatsapp_doctypes 
            if (d.enable_whatsapp and 
                d.table_doctype.strip() == doc.doctype and
                d.trigger_event == trigger_event and
                d.trigger_timing == "Immediate")  # Only immediate triggers for doc events
        ]
        
        if not matching_configs:
            return

        whatsapp_handler = WhatsAppHandler()
        
        for doctype_setting in matching_configs:
            try:
                _process_whatsapp_config(doc, doctype_setting, whatsapp_handler)
            except Exception as e:
                frappe.log_error(
                    f"Config processing failed for {doctype_setting.table_doctype}: {str(e)}", 
                    f"WhatsApp Config Error - {doc.doctype}"
                )
                continue

    except Exception as e:
        frappe.log_error(f"WhatsApp notification failed: {str(e)}", 
                        f"DocType: {doc.doctype}, Name: {doc.name}")


def _process_whatsapp_config(doc, doctype_setting, whatsapp_handler):
    """
    Modified to handle multiple assigned users
    Process individual WhatsApp configuration
    """
    if not doctype_setting.phone_field:
        frappe.log_error("No phone field configured", f"{doc.doctype} - {doc.name}")
        return
    
    # Check if this is an assigned_to field configuration
    if doctype_setting.phone_field.strip() == "assigned_to":
        # Handle multiple assignments
        assigned_phones = get_assigned_user_phone_numbers(doc)
        
        if not assigned_phones:
            frappe.log_error("No assigned users with phone numbers found", 
                           f"{doc.doctype} - {doc.name}")
            return
        
        # Build message once
        message = MessageTemplateHandler.build_message(
            doc, doctype_setting, 
            trigger_event=doctype_setting.trigger_event
        )
        
        # Generate PDF once (skip for cancel events)
        pdf_content = None
        if doctype_setting.trigger_event != "Cancel" and doctype_setting.attach_print:
            pdf_content = PDFGenerator.generate_pdf(doc.doctype, doc.name)
        
        # Send to all assigned users
        success_count = 0
        error_count = 0
        
        for assigned_user in assigned_phones:
            try:
                if whatsapp_handler.send_message(
                    assigned_user['phone'], message, doc.doctype, doc.name, 
                    pdf_content, fallback_to_text=True
                ):
                    success_count += 1
                    frappe.log_error(
                        f"WhatsApp sent to assigned user {assigned_user['user']}", 
                        f"Assignment Success - {doc.doctype}"
                    )
                else:
                    error_count += 1
                    frappe.log_error(
                        f"WhatsApp failed for assigned user {assigned_user['user']}", 
                        f"Assignment Error - {doc.doctype}"
                    )
            except Exception as send_error:
                error_count += 1
                frappe.log_error(
                    f"Error sending to {assigned_user['user']}: {str(send_error)}", 
                    f"Assignment Send Error - {doc.doctype}"
                )
        
        # Log summary
        frappe.log_error(
            f"Assignment notifications: {success_count} sent, {error_count} failed", 
            f"Assignment Summary - {doc.doctype}"
        )
        
        return
    
    # Handle single phone number (existing functionality)
    phone = get_phone_number_enhanced(doc, doctype_setting.phone_field)
    if not phone:
        frappe.log_error("No mobile number found", f"{doc.doctype} - {doc.name}")
        return

    # Build message based on trigger event
    message = MessageTemplateHandler.build_message(
        doc, doctype_setting, 
        trigger_event=doctype_setting.trigger_event
    )
    
    # Generate PDF and send (skip PDF for cancel events)
    pdf_content = None
    if doctype_setting.trigger_event != "Cancel" and doctype_setting.attach_print:
        pdf_content = PDFGenerator.generate_pdf(doc.doctype, doc.name)
    
    whatsapp_handler.send_message(
        phone, message, doc.doctype, doc.name, 
        pdf_content, fallback_to_text=True
    )



# Utility functions
def test_whatsapp_connection():
    """Test WhatsApp API connection"""
    whatsapp_handler = WhatsAppHandler()
    
    if not whatsapp_handler.is_enabled():
        return {"status": "error", "message": "WhatsApp settings not configured"}
    
    test_message = "Test message from Frappe system."
    test_number = "1234567890"  # Replace with actual test number
    
    result = whatsapp_handler.send_message(test_number, test_message, 
                                         "Test", "Test", fallback_to_text=True)
    
    return {
        "status": "success" if result else "error",
        "message": "Test message sent" if result else "Test message failed"
    }


def send_whatsapp_without_pdf(receiver_id, message, doctype, docname):
    """Emergency fallback - send without PDF"""
    whatsapp_handler = WhatsAppHandler()
    
    if not whatsapp_handler.is_enabled():
        return False
    
    # Clean message and add document reference
    text_message = message.replace("Please see attached document.", "")
    text_message += f"\n\nDocument: {docname}"
    
    return whatsapp_handler.send_message(receiver_id, text_message, doctype, 
                                       docname, pdf_content=None, fallback_to_text=True)


# Backward compatibility functions
def send_whatsapp_message_with_attachment(receiver_id, message, doctype, docname, 
                                        print_format="Standard", fallback_to_text=False):
    """Backward compatibility wrapper"""
    whatsapp_handler = WhatsAppHandler()
    pdf_content = PDFGenerator.generate_pdf(doctype, docname, print_format)
    return whatsapp_handler.send_message(receiver_id, message, doctype, docname, 
                                       pdf_content, fallback_to_text)

def get_phone_number_enhanced(doc, phone_field):
    """
    Enhanced phone number getter that supports:
    1. Regular fields (mobile_no, customer.mobile_no)
    2. User fields (owner, modified_by, assigned_to)
    3. Custom user references
    """
    if not phone_field:
        return None
    
    phone_field = phone_field.strip()
    
    # Check if it's a user-based field
    user_fields = [
        'owner',           # Document creator
        'modified_by',     # Last person who modified
        'assigned_to',     # Assigned user (special handling via ToDo)
        'created_by',      # Alternative field name
        'approved_by',     # Approval workflows
        'submitted_by'     # Submission user
    ]
    
    # Handle user-based fields
    if phone_field in user_fields:
        return get_user_phone_number(doc, phone_field)
    
    # Handle user field with custom suffix (e.g., "owner.mobile_no")
    if '.' in phone_field:
        parts = phone_field.split('.')
        if len(parts) == 2 and parts[0] in user_fields:
            # This is a user field, get user's phone
            return get_user_phone_number(doc, parts[0])
    
    # Handle regular fields (existing functionality)
    return get_phone_number(doc, phone_field)


def get_user_phone_number(doc, user_field):
    """
    Get phone number from a User document based on user field
    Handles special case for assigned_to field which uses ToDo doctype
    Modified to handle multiple assignments
    """
    try:
        # Special handling for assigned_to field - now returns multiple numbers
        if user_field == "assigned_to":
            assigned_phones = get_assigned_user_phone_numbers(doc)
            if assigned_phones:
                # For backward compatibility, return the first phone number
                # But log that multiple assignments were found
                if len(assigned_phones) > 1:
                    frappe.log_error(
                        f"Multiple assignments found ({len(assigned_phones)}), using first one. "
                        f"Consider using get_assigned_user_phone_numbers() for full list.", 
                        f"Multiple Assignment Warning - {doc.doctype}"
                    )
                return assigned_phones[0]['phone']
            return None
        
        # Handle regular user fields (existing functionality)
        username = getattr(doc, user_field, None)
        if not username:
            return None
        
        # Get User document
        user_doc = frappe.get_doc("User", username)
        
        # Try multiple phone fields in User doctype
        phone_fields_to_try = [
            'mobile_no',      # Standard mobile field
            'phone',          # Alternative phone field
            'cell_number',    # Some customizations use this
            'whatsapp_number' # Custom WhatsApp field if you have one
        ]
        
        for field in phone_fields_to_try:
            if hasattr(user_doc, field):
                phone = getattr(user_doc, field)
                if phone:
                    cleaned_phone = WhatsAppHandler()._clean_phone_number(phone)
                    if cleaned_phone:
                        return cleaned_phone
        
        # Log if no phone found
        frappe.log_error(
            f"No phone number found for user {username}", 
            f"User Phone Lookup - {doc.doctype}"
        )
        return None
        
    except Exception as e:
        frappe.log_error(
            f"Error getting user phone for {user_field}: {str(e)}", 
            f"User Phone Error - {doc.doctype}"
        )
        return None
    

def get_assigned_user_phone_numbers(doc):
    """
    Get phone numbers for ALL assigned users from ToDo doctype
    Returns a list of phone numbers for all assigned users
    """
    try:
        # Find all active ToDo entries for this document
        todo_filters = {
            "reference_type": doc.doctype,
            "reference_name": doc.name,
            "status": "Open"  # Only get active assignments
        }
        
        # Get ALL assignments (removed limit=1)
        todos = frappe.get_all(
            "ToDo",
            filters=todo_filters,
            fields=["allocated_to"],
            order_by="creation desc"
        )
        
        if not todos:
            # Try without status filter in case assignments are closed but still relevant
            todos = frappe.get_all(
                "ToDo",
                filters={
                    "reference_type": doc.doctype,
                    "reference_name": doc.name
                },
                fields=["allocated_to"],
                order_by="creation desc"
            )
        
        if not todos:
            frappe.log_error(
                f"No assignments found for {doc.doctype} {doc.name}", 
                f"Assignment Phone Lookup - {doc.doctype}"
            )
            return []
        
        phone_numbers = []
        processed_users = set()  # Avoid duplicates if same user has multiple todos
        
        for todo in todos:
            if not todo.allocated_to or todo.allocated_to in processed_users:
                continue
                
            processed_users.add(todo.allocated_to)
            
            try:
                # Get User document for the assigned user
                user_doc = frappe.get_doc("User", todo.allocated_to)
                
                # Try multiple phone fields in User doctype
                phone_fields_to_try = [
                    'mobile_no',      # Standard mobile field
                    'phone',          # Alternative phone field
                    'cell_number',    # Some customizations use this
                    'whatsapp_number' # Custom WhatsApp field if you have one
                ]
                
                user_phone = None
                for field in phone_fields_to_try:
                    if hasattr(user_doc, field):
                        phone = getattr(user_doc, field)
                        if phone:
                            cleaned_phone = WhatsAppHandler()._clean_phone_number(phone)
                            if cleaned_phone:
                                user_phone = cleaned_phone
                                break
                
                if user_phone:
                    phone_numbers.append({
                        'phone': user_phone,
                        'user': todo.allocated_to
                    })
                    frappe.log_error(
                        f"Found phone for assigned user {todo.allocated_to}: {user_phone}", 
                        f"Assignment Phone Success - {doc.doctype}"
                    )
                else:
                    frappe.log_error(
                        f"No phone number found for assigned user {todo.allocated_to}", 
                        f"Assignment Phone Lookup - {doc.doctype}"
                    )
                    
            except Exception as user_error:
                frappe.log_error(
                    f"Error processing user {todo.allocated_to}: {str(user_error)}", 
                    f"Assignment User Error - {doc.doctype}"
                )
                continue
        
        frappe.log_error(
            f"Found {len(phone_numbers)} phone numbers for {len(processed_users)} assigned users", 
            f"Assignment Summary - {doc.doctype}"
        )
        
        return phone_numbers
        
    except Exception as e:
        frappe.log_error(
            f"Error getting assigned users' phones: {str(e)}", 
            f"Assignment Phone Error - {doc.doctype}"
        )
        return []

