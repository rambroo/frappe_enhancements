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
    def build_message(doc, doctype_setting, is_reminder=False, target_date=None):
        """Build WhatsApp message using template or default format"""
        try:
            # Try custom template first
            if doctype_setting.custom_template:
                template_doc = frappe.get_doc("WhatsApp Message Template", 
                                            doctype_setting.custom_template)
                
                if template_doc and template_doc.is_active and template_doc.template_text:
                    return MessageTemplateHandler._process_template(
                        template_doc.template_text, doc, target_date
                    )
            
            # Try reminder message field for reminders
            if is_reminder and doctype_setting.reminder_message:
                return MessageTemplateHandler._process_template(
                    doctype_setting.reminder_message, doc, target_date
                )
            
            # Default message
            return MessageTemplateHandler._build_default_message(doc, is_reminder, target_date)
            
        except Exception as e:
            frappe.log_error(f"Error building message: {str(e)}", 
                           f"WhatsApp Template Error - {doc.doctype}")
            return MessageTemplateHandler._build_fallback_message(doc, is_reminder, target_date)
    
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
    def _build_default_message(doc, is_reminder=False, target_date=None):
        """Build default message format"""
        if is_reminder:
            return f"Reminder: Your document {doc.name} is due on {target_date}."
        
        message = f"{doc.doctype} *{doc.name}* has been submitted."
        
        amount = getattr(doc, "grand_total", None) or getattr(doc, "total", None)
        if amount:
            message += f"\nTotal Amount: ₹{amount}"
        
        message += "\n\nPlease see attached document."
        return message
    
    @staticmethod
    def _build_fallback_message(doc, is_reminder=False, target_date=None):
        """Build basic fallback message"""
        if is_reminder:
            return f"Reminder: Document {doc.name} due on {target_date}."
        return f"{doc.doctype} {doc.name} has been submitted."


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


# Main entry points
def send_scheduled_whatsapp_reminders():
    """Main function to send scheduled WhatsApp reminders"""
    settings = frappe.get_single("WhatsApp Settings")
    if not settings.enabled:
        frappe.log_error("WhatsApp reminders skipped", "WhatsApp Settings disabled")
        return

    for doctype_config in settings.whatsapp_doctypes:
        if not doctype_config.schedule_enabled or not doctype_config.date_field:
            continue

        try:
            process_scheduled_whatsapp_reminder(doctype_config)
        except Exception as e:
            error_msg = f"Scheduler failed for {doctype_config.table_doctype}: {str(e)}"
            frappe.log_error(error_msg, f"WhatsApp Scheduler Error")
            continue


def process_scheduled_whatsapp_reminder(config):
    """Process scheduled reminders for a specific doctype configuration"""
    date_field = config.date_field
    target_date = add_days(nowdate(), config.days_before or 0)
    
    filters = {f"{date_field}": target_date}
    
    # Exclude cancelled documents
    if config.table_doctype in ["Purchase Order", "Sales Order", 
                               "Purchase Invoice", "Sales Invoice"]:
        filters["docstatus"] = ["!=", 2]
    
    docs = frappe.get_all(config.table_doctype, filters=filters, 
                         fields=["name", "docstatus"])

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
            
            phone = get_phone_number(doc, config.phone_field)
            if not phone:
                error_count += 1
                continue

            # Build message and send
            message = MessageTemplateHandler.build_message(doc, config, 
                                                         is_reminder=True, 
                                                         target_date=target_date)
            
            # Try with PDF attachment
            pdf_content = PDFGenerator.generate_pdf(doc.doctype, doc.name)
            
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
        frappe.log_error(f"Reminders processed - Success: {success_count}, Errors: {error_count}", 
                        f"WhatsApp Reminder Summary - {config.table_doctype}")


def handle_whatsapp_notification(doc, method):
    """Handle WhatsApp notification for submitted documents"""
    try:
        # Skip cancelled documents
        if hasattr(doc, 'docstatus') and doc.docstatus == 2:
            return
            
        settings = frappe.get_single("WhatsApp Settings")
        if not settings.enabled:
            return

        # Find matching DocType configuration
        doctype_setting = next(
            (d for d in settings.whatsapp_doctypes 
             if d.enable_whatsapp and d.table_doctype.strip() == doc.doctype), 
            None
        )
        
        if not doctype_setting or not doctype_setting.phone_field:
            return
        
        phone = get_phone_number(doc, doctype_setting.phone_field)
        if not phone:
            frappe.log_error("No mobile number found", 
                           f"{doc.doctype} - {doc.name}")
            return

        # Build message and send
        whatsapp_handler = WhatsAppHandler()
        message = MessageTemplateHandler.build_message(doc, doctype_setting)
        
        # Generate PDF and send
        pdf_content = PDFGenerator.generate_pdf(doc.doctype, doc.name)
        whatsapp_handler.send_message(phone, message, doc.doctype, doc.name, 
                                    pdf_content, fallback_to_text=True)

    except Exception as e:
        frappe.log_error(f"WhatsApp notification failed: {str(e)}", 
                        f"DocType: {doc.doctype}, Name: {doc.name}")

def handle_whatsapp_notification_save(doc, method):
    """Handle WhatsApp notification for submitted documents and non-submittable documents on save"""
    try:
        # Skip cancelled documents
        if hasattr(doc, 'docstatus') and doc.docstatus == 2:
            return
            
        settings = frappe.get_single("WhatsApp Settings")
        if not settings.enabled:
            return

        # Find matching DocType configuration
        doctype_setting = next(
            (d for d in settings.whatsapp_doctypes 
             if d.enable_whatsapp and d.table_doctype.strip() == doc.doctype), 
            None
        )
        
        if not doctype_setting or not doctype_setting.phone_field:
            return
        
        # Check if document is submittable
        meta = frappe.get_meta(doc.doctype)
        is_submittable = meta.is_submittable
        
        # For submittable documents, only proceed if document is submitted (docstatus = 1)
        # For non-submittable documents, proceed on save (docstatus = 0 or no docstatus)
        if is_submittable:
            # Only send notification for submitted documents
            if not (hasattr(doc, 'docstatus') and doc.docstatus == 1):
                return
        else:
            # For non-submittable documents, send notification on save
            # These documents can only be saved (docstatus = 0 or no docstatus field)
            pass
        
        phone = get_phone_number(doc, doctype_setting.phone_field)
        if not phone:
            frappe.log_error("No mobile number found", 
                           f"{doc.doctype} - {doc.name}")
            return

        # Build message and send
        whatsapp_handler = WhatsAppHandler()
        message = MessageTemplateHandler.build_message(doc, doctype_setting)
        
        # Generate PDF and send
        pdf_content = PDFGenerator.generate_pdf(doc.doctype, doc.name)
        whatsapp_handler.send_message(phone, message, doc.doctype, doc.name, 
                                    pdf_content, fallback_to_text=True)

    except Exception as e:
        frappe.log_error(f"WhatsApp notification failed: {str(e)}", 
                        f"DocType: {doc.doctype}, Name: {doc.name}")

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