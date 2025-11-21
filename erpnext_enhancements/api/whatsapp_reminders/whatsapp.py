import requests
import frappe
import re
from frappe.utils import add_days, nowdate, date_diff, formatdate, now_datetime, add_to_date, get_datetime
from datetime import datetime, time, timedelta


def safe_get_settings():
    """Safely get WhatsApp Settings to avoid import errors during installation"""
    if frappe.flags.in_install or frappe.flags.in_patch or frappe.flags.in_migrate:
        return None

    if not frappe.db.exists("DocType", "WhatsApp Setting"):
        return None

    try:
        return frappe.get_single("WhatsApp Setting")
    except ImportError as e:
        frappe.log_error(f"Could not load WhatsApp Settings: {e}", "WhatsApp Settings")
        return None


class WhatsAppHandler:
    """Centralized WhatsApp message handler using HiSocial API"""

    def __init__(self):
        self.settings = safe_get_settings()
        self.api_url = "https://hisocial.in/api/send"

        if not self.settings:
            frappe.throw("WhatsApp Settings not configured or not available")

    def is_enabled(self):
        """Check if WhatsApp is enabled and configured"""
        return (self.settings.enabled and
                self.settings.instance_id and
                self.settings.access_token)

    def send_message(self, receiver_id, message, doctype=None, docname=None):
        """Send WhatsApp text message"""
        if not self.is_enabled():
            frappe.log_error("WhatsApp not configured", "WhatsApp Settings")
            return False

        clean_receiver = self._clean_phone_number(receiver_id)
        if not clean_receiver:
            frappe.log_error(f"Invalid phone number: {receiver_id}",
                           f"WhatsApp - {doctype} {docname}")
            return False

        return self._send_text_message(clean_receiver, message, doctype, docname)

    def _send_text_message(self, receiver_id, message, doctype, docname):
        """Send text-only message via HiSocial API"""
        try:
            payload = {
                'number': f"91{receiver_id}",
                'type': 'text',
                'message': message,
                'instance_id': self.settings.instance_id,
                'access_token': self.settings.access_token
            }

            headers = {'Content-Type': 'application/json'}
            response = requests.post(self.api_url, json=payload, headers=headers, timeout=30)
            return self._handle_response(response, receiver_id, doctype, docname)

        except Exception as e:
            frappe.log_error(f"Message sending failed: {str(e)}",
                           f"WhatsApp Error - {doctype} {docname}")
            return False

    def _handle_response(self, response, receiver_id, doctype, docname):
        """Handle HiSocial API response"""
        if response.status_code != 200:
            frappe.log_error(f"API failed with status {response.status_code}: {response.text}",
                           f"WhatsApp HTTP Error - {doctype}")
            return False

        try:
            response_data = response.json()

            # HiSocial returns status field
            if isinstance(response_data, dict):
                status = response_data.get('status')
                if status == 'success' or status == True or status == 'sent':
                    frappe.log_error(f"WhatsApp sent successfully to 91{receiver_id}",
                                   f"WhatsApp Success - {doctype}")
                    return True
                else:
                    error_msg = response_data.get('message', response.text)
                    frappe.log_error(f"API returned error: {error_msg}",
                                   f"WhatsApp API Error - {doctype}")
                    return False

            # Fallback check
            if 'success' in response.text.lower() or 'sent' in response.text.lower():
                frappe.log_error(f"WhatsApp sent successfully to 91{receiver_id}",
                               f"WhatsApp Success - {doctype}")
                return True
            else:
                frappe.log_error(f"API returned: {response.text}",
                               f"WhatsApp API Error - {doctype}")
                return False

        except ValueError:
            frappe.log_error(f"API returned non-JSON response: {response.text}",
                           f"WhatsApp API Error - {doctype}")
            return False
    
    def _clean_phone_number(self, phone):
        """Clean and validate phone number"""
        if not phone:
            return None
        
        # Remove formatting and keep only digits
        phone = str(phone).strip()
        phone = re.sub(r'[^\d]', '', phone)
        
        # Remove country code if present
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
            # Remove Quill editor specific divs
            text = re.sub(r'<div class="ql-editor[^"]*"[^>]*>', '', text)
            text = re.sub(r'</div>', '', text)
            
            # Remove all HTML tags
            text = re.sub(r'<[^>]+>', '', text)
            
            # Replace common HTML entities
            html_entities = {
                '&nbsp;': ' ', '&amp;': '&', '&lt;': '<', '&gt;': '>',
                '&quot;': '"', '&#39;': "'", '&apos;': "'",
                '&hellip;': '...', '&mdash;': '—', '&ndash;': '–'
            }
            
            for entity, replacement in html_entities.items():
                text = text.replace(entity, replacement)
            
            # Clean up whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            text = re.sub(r'\n\s*\n', '\n', text)
            
            return text
            
        except Exception as e:
            frappe.log_error(f"Error cleaning HTML: {str(e)}", "WhatsApp HTML Cleanup")
            return text

    @staticmethod
    def format_whatsapp_message(message):
        """Format message for WhatsApp with proper line breaks"""
        if not message:
            return message
        
        # Replace various line break formats with \n
        replacements = [
            ('%0A\\n', '\n'),
            ('%0A', '\n'),
            ('\\n', '\n'),
            ('/n', '\n'),
            ('&lt;br&gt;', '\n'),
            ('<br>', '\n'),
            ('<br/>', '\n'),
            ('<BR>', '\n'),
            ('&nbsp;', ' '),
        ]
        
        for old, new in replacements:
            message = message.replace(old, new)
        
        # Clean up multiple consecutive line breaks (more than 2)
        message = re.sub(r'\n{3,}', '\n\n', message)
        
        # Remove trailing whitespace from each line
        lines = message.split('\n')
        lines = [line.rstrip() for line in lines]
        message = '\n'.join(lines)
        
        return message.strip()

    @staticmethod
    def build_message(doc, notification, is_reminder=False, target_date=None, target_time=None):
        """Build WhatsApp message using template"""
        
        try:
            # Get template if specified
            if notification.message:
                template_doc = frappe.get_doc("WhatsApp Message Template", notification.message)
                
                if template_doc and template_doc.is_active and template_doc.template_text:
                    return MessageTemplateHandler._process_template(
                        template_doc.template_text, doc, target_date, target_time
                    )
            
            # Fallback to default message
            return MessageTemplateHandler._build_default_message(
                doc, notification, target_date, target_time
            )
            
        except Exception as e:
            frappe.log_error(f"Error building message: {str(e)}", 
                           f"WhatsApp Template Error - {doc.doctype}")
            return MessageTemplateHandler._build_fallback_message(
                doc, notification, target_date, target_time
            )

    @staticmethod
    def _process_template(template_text, doc, target_date=None, target_time=None):
        """Process template with placeholder replacement and proper formatting"""
        template_text = MessageTemplateHandler.clean_html(template_text)
        
        # Build and replace placeholders
        placeholders = MessageTemplateHandler._build_placeholders(doc, target_date, target_time)
        message = template_text
        
        for placeholder, value in placeholders.items():
            message = message.replace(placeholder, str(value))
        
        # Handle dynamic field placeholders
        remaining_patterns = re.findall(r'\{([^}]+)\}', message)
        for pattern in remaining_patterns:
            if hasattr(doc, pattern):
                value = getattr(doc, pattern)
                if value:
                    if isinstance(value, str):
                        value = MessageTemplateHandler.clean_html(value)
                    
                    if hasattr(value, 'strftime'):
                        try:
                            value = formatdate(value)
                        except:
                            value = str(value)
                    
                    message = message.replace(f'{{{pattern}}}', str(value))
                else:
                    message = message.replace(f'{{{pattern}}}', "")
        
        # Format the message for WhatsApp
        message = MessageTemplateHandler.format_whatsapp_message(message)
        
        return message
    
    @staticmethod
    def _build_placeholders(doc, target_date=None, target_time=None):
        """Build common placeholders dictionary including time placeholders"""
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
            
            # Days calculation
            try:
                days_diff = date_diff(target_date, nowdate())
                placeholders.update({
                    '{days_remaining}': str(max(0, days_diff)),
                    '{days_left}': str(max(0, days_diff)),
                    '{day_text}': "day" if days_diff == 1 else "days" if days_diff > 1 else "today"
                })
            except:
                placeholders.update({
                    '{days_remaining}': "", '{days_left}': "", '{day_text}': ""
                })
        
        # Time placeholders
        if target_time:
            try:
                if isinstance(target_time, str):
                    time_str = target_time
                elif isinstance(target_time, timedelta):
                    total_seconds = int(target_time.total_seconds())
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    time_str = f"{hours:02d}:{minutes:02d}"
                elif hasattr(target_time, 'strftime'):
                    time_str = target_time.strftime("%H:%M")
                else:
                    time_str = str(target_time)
                
                placeholders.update({
                    '{appointment_time}': time_str,
                    '{target_time}': time_str,
                    '{reminder_time}': time_str,
                    '{scheduled_time}': time_str
                })
            except Exception as e:
                frappe.log_error(f"Error processing time placeholders: {str(e)}", "WhatsApp Time Placeholder Error")
                placeholders.update({
                    '{appointment_time}': "", '{target_time}': "", 
                    '{reminder_time}': "", '{scheduled_time}': ""
                })
        
        # Common document fields
        common_fields = [
            'customer', 'supplier', 'posting_date', 'due_date', 
            'status', 'delivery_date', 'transaction_date', 
            'description', 'remarks', 'subject', 'title'
        ]
        
        for field in common_fields:
            if hasattr(doc, field):
                value = getattr(doc, field)
                if value:
                    if isinstance(value, str) and field in ['description', 'remarks', 'subject', 'title']:
                        value = MessageTemplateHandler.clean_html(value)
                    elif hasattr(value, 'strftime'):
                        try:
                            value = formatdate(value)
                        except:
                            value = str(value)
                    
                    placeholders[f'{{{field}}}'] = str(value)
                else:
                    placeholders[f'{{{field}}}'] = ""
        
        return placeholders
    
    @staticmethod
    def _build_default_message(doc, notification, target_date=None, target_time=None):
        """Build default message format including time information"""
        
        if notification.event == "Scheduled Reminder":
            if target_date and target_time:
                try:
                    if isinstance(target_time, str):
                        time_str = target_time
                    elif isinstance(target_time, timedelta):
                        total_seconds = int(target_time.total_seconds())
                        hours = total_seconds // 3600
                        minutes = (total_seconds % 3600) // 60
                        time_str = f"{hours:02d}:{minutes:02d}"
                    elif hasattr(target_time, 'strftime'):
                        time_str = target_time.strftime("%H:%M")
                    else:
                        time_str = str(target_time)
                    
                    message = f"Reminder: Your {doc.doctype} *{doc.name}* is scheduled for {formatdate(target_date)} at {time_str}."
                except Exception as e:
                    frappe.log_error(f"Error formatting time in message: {str(e)}", "WhatsApp Time Format Error")
                    message = f"Reminder: Your {doc.doctype} *{doc.name}* is scheduled for {target_date}."
            elif target_date:
                message = f"Reminder: Your {doc.doctype} *{doc.name}* is due on {target_date}."
            else:
                message = f"Reminder: Your {doc.doctype} *{doc.name}* requires attention."
        else:
            # Messages based on trigger event
            event_messages = {
                "Submit": f"{doc.doctype} *{doc.name}* has been submitted.",
                "Save": f"{doc.doctype} *{doc.name}* has been saved.",
                "Cancel": f"{doc.doctype} *{doc.name}* has been cancelled.",
                "On Creation": f"New {doc.doctype} *{doc.name}* has been created.",
                "On Update": f"{doc.doctype} *{doc.name}* has been updated."
            }
            
            message = event_messages.get(notification.event, 
                                       f"{doc.doctype} *{doc.name}* has been processed.")
        
        # Add amount if available
        amount = getattr(doc, "grand_total", None) or getattr(doc, "total", None)
        if amount:
            message += f"\nTotal Amount: ₹{amount}"
    
        message = MessageTemplateHandler.format_whatsapp_message(message)    
        return message
    
    @staticmethod
    def _build_fallback_message(doc, notification, target_date=None, target_time=None):
        """Build basic fallback message including time"""
        
        if notification.event == "Scheduled Reminder":
            if target_date and target_time:
                try:
                    if isinstance(target_time, timedelta):
                        total_seconds = int(target_time.total_seconds())
                        hours = total_seconds // 3600
                        minutes = (total_seconds % 3600) // 60
                        time_str = f"{hours:02d}:{minutes:02d}"
                    elif hasattr(target_time, 'strftime'):
                        time_str = target_time.strftime("%H:%M")
                    else:
                        time_str = str(target_time)
                    
                    message = f"Reminder: {doc.doctype} {doc.name} scheduled for {target_date} at {time_str}."
                except Exception as e:
                    frappe.log_error(f"Error in fallback time formatting: {str(e)}", "WhatsApp Fallback Time Error")
                    message = f"Reminder: {doc.doctype} {doc.name} due on {target_date}."
            elif target_date:
                message = f"Reminder: {doc.doctype} {doc.name} due on {target_date}."
            else:
                message = f"Reminder: {doc.doctype} {doc.name} requires attention."
        else:
            event_messages = {
                "Cancel": f"{doc.doctype} {doc.name} has been cancelled.",
                "Submit": f"{doc.doctype} {doc.name} has been submitted.",
                "Save": f"{doc.doctype} {doc.name} has been saved.",
                "On Creation": f"New {doc.doctype} {doc.name} has been created.",
                "On Update": f"{doc.doctype} {doc.name} has been updated."
            }
            
            message = event_messages.get(notification.event, f"{doc.doctype} {doc.name} has been processed.")
        
        message = MessageTemplateHandler.format_whatsapp_message(message)
        
        return message


# ============================================================================
# NOTIFICATION QUERY HELPERS
# ============================================================================

def get_active_notifications(document_type=None, event=None):
    """
    Get active WhatsApp Notifications with optional filters
    
    Args:
        document_type: Filter by Document Type
        event: Filter by event (Submit, Save, Cancel, etc.)
    
    Returns:
        list: List of notification names
    """
    filters = {"enabled": 1}
    
    if document_type:
        filters["document_type"] = document_type
    
    if event:
        filters["event"] = event
    
    return frappe.get_all(
        "WhatsApp Notification",
        filters=filters,
        fields=["name"]
    )


# ============================================================================
# PHONE NUMBER UTILITIES
# ============================================================================

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


def get_phone_number_enhanced(doc, phone_field):
    """Enhanced phone number getter supporting user fields and regular fields"""
    if not phone_field:
        return None
    
    phone_field = phone_field.strip()
    
    # User-based fields
    user_fields = [
        'owner', 'modified_by', 'assigned_to', 'created_by', 
        'approved_by', 'submitted_by'
    ]
    
    # Handle user-based fields
    if phone_field in user_fields:
        return get_user_phone_number(doc, phone_field)
    
    # Handle user field with suffix (e.g., "owner.mobile_no")
    if '.' in phone_field:
        parts = phone_field.split('.')
        if len(parts) == 2 and parts[0] in user_fields:
            return get_user_phone_number(doc, parts[0])
    
    # Handle regular fields
    return get_phone_number(doc, phone_field)


def get_user_phone_number(doc, user_field):
    """Get phone number from User document"""
    try:
        # Handle assigned_to field (multiple assignments)
        if user_field == "assigned_to":
            assigned_phones = get_assigned_user_phone_numbers(doc)
            if assigned_phones:
                if len(assigned_phones) > 1:
                    frappe.log_error(
                        f"Multiple assignments found ({len(assigned_phones)}), using first one.", 
                        f"Multiple Assignment Warning - {doc.doctype}"
                    )
                return assigned_phones[0]['phone']
            return None
        
        # Handle regular user fields
        username = getattr(doc, user_field, None)
        if not username:
            return None
        
        user_doc = frappe.get_doc("User", username)
        
        # Try multiple phone fields
        phone_fields_to_try = ['mobile_no', 'phone', 'cell_number', 'whatsapp_number']
        
        for field in phone_fields_to_try:
            if hasattr(user_doc, field):
                phone = getattr(user_doc, field)
                if phone:
                    cleaned_phone = WhatsAppHandler()._clean_phone_number(phone)
                    if cleaned_phone:
                        return cleaned_phone
        
        frappe.log_error(f"No phone number found for user {username}", 
                        f"User Phone Lookup - {doc.doctype}")
        return None
        
    except Exception as e:
        frappe.log_error(f"Error getting user phone for {user_field}: {str(e)}", 
                        f"User Phone Error - {doc.doctype}")
        return None


def get_assigned_user_phone_numbers(doc):
    """Get phone numbers for all assigned users from ToDo doctype"""
    try:
        todo_filters = {
            "reference_type": doc.doctype,
            "reference_name": doc.name,
            "status": "Open"
        }
        
        todos = frappe.get_all("ToDo", filters=todo_filters, fields=["allocated_to"])
        
        if not todos:
            todos = frappe.get_all(
                "ToDo",
                filters={"reference_type": doc.doctype, "reference_name": doc.name},
                fields=["allocated_to"]
            )
        
        if not todos:
            return []
        
        phone_numbers = []
        processed_users = set()
        
        for todo in todos:
            if not todo.allocated_to or todo.allocated_to in processed_users:
                continue
                
            processed_users.add(todo.allocated_to)
            
            try:
                user_doc = frappe.get_doc("User", todo.allocated_to)
                
                phone_fields_to_try = ['mobile_no', 'phone', 'cell_number', 'whatsapp_number']
                
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
                    
            except Exception as user_error:
                frappe.log_error(f"Error processing user {todo.allocated_to}: {str(user_error)}", 
                               f"Assignment User Error - {doc.doctype}")
                continue
        
        return phone_numbers
        
    except Exception as e:
        frappe.log_error(f"Error getting assigned users' phones: {str(e)}", 
                        f"Assignment Phone Error - {doc.doctype}")
        return []


def get_phone_numbers_by_role(role):
    """
    Get phone numbers for all users with specific role
    
    Args:
        role: Role name
    
    Returns:
        list: [{"phone": str, "user": str}]
    """
    try:
        # Get all users with this role
        users = frappe.get_all(
            "Has Role",
            filters={"role": role, "parenttype": "User"},
            fields=["parent"]
        )
        
        if not users:
            return []
        
        phone_numbers = []
        processed_users = set()
        
        for user_data in users:
            username = user_data.parent
            
            if username in processed_users:
                continue
            
            processed_users.add(username)
            
            try:
                user_doc = frappe.get_doc("User", username)
                
                # Skip disabled users
                if user_doc.enabled == 0:
                    continue
                
                # Try multiple phone fields
                phone_fields_to_try = ['mobile_no', 'phone', 'cell_number', 'whatsapp_number']
                
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
                        'user': username
                    })
                    
            except Exception as user_error:
                frappe.log_error(f"Error processing user {username}: {str(user_error)}", 
                               f"Role User Error - {role}")
                continue
        
        return phone_numbers
        
    except Exception as e:
        frappe.log_error(f"Error getting users by role {role}: {str(e)}", 
                        "Role Phone Error")
        return []


# ============================================================================
# LINKED DOCUMENT PROCESSING
# ============================================================================

def get_linked_document_recipients(doc, notification):
    """
    Get recipients from linked documents configured in notification.linked_documents

    Args:
        doc: Parent document object
        notification: WhatsApp Notification document

    Returns:
        list: [{"phone": str, "source": str}]
    """
    all_phones = []

    if not hasattr(notification, 'linked_documents') or not notification.linked_documents:
        return all_phones

    for linked_config in notification.linked_documents:
        try:
            linked_doctype = linked_config.linked_doctype
            if not linked_doctype:
                continue

            # Find link fields in the document that point to the linked_doctype
            linked_doc_name = find_linked_document(doc, linked_doctype)

            if not linked_doc_name:
                frappe.log_error(
                    f"No link to {linked_doctype} found in {doc.doctype} {doc.name}",
                    f"WhatsApp Linked Doc - {doc.doctype}"
                )
                continue

            # Get the linked document
            try:
                linked_doc = frappe.get_doc(linked_doctype, linked_doc_name)
            except Exception as e:
                frappe.log_error(
                    f"Could not fetch linked doc {linked_doctype} {linked_doc_name}: {str(e)}",
                    f"WhatsApp Linked Doc Error - {doc.doctype}"
                )
                continue

            # Check condition if specified
            if linked_config.condition:
                if not evaluate_custom_condition(linked_doc, linked_config.condition):
                    continue

            # Get phone from phone_field
            if linked_config.phone_field:
                phone = get_phone_number_enhanced(linked_doc, linked_config.phone_field)
                if phone:
                    all_phones.append({
                        'phone': phone,
                        'source': f"Linked {linked_doctype}: {linked_doc_name} ({linked_config.phone_field})"
                    })

            # Get assignees of linked document
            if linked_config.send_to_all_assignees:
                assigned_phones = get_assigned_user_phone_numbers(linked_doc)
                for assigned in assigned_phones:
                    all_phones.append({
                        'phone': assigned['phone'],
                        'source': f"Linked {linked_doctype} Assignee: {assigned['user']}"
                    })

            # Get role-based recipients
            if linked_config.receiver_by_role:
                role_phones = get_phone_numbers_by_role(linked_config.receiver_by_role)
                for role_phone in role_phones:
                    all_phones.append({
                        'phone': role_phone['phone'],
                        'source': f"Linked {linked_doctype} Role ({linked_config.receiver_by_role}): {role_phone['user']}"
                    })

        except Exception as e:
            frappe.log_error(
                f"Error processing linked document config: {str(e)}",
                f"WhatsApp Linked Doc Error - {doc.doctype}"
            )
            continue

    return all_phones


def find_linked_document(doc, target_doctype):
    """
    Find a linked document of target_doctype in the given document
    Scans all Link fields in the document to find one pointing to target_doctype

    Args:
        doc: Document object to scan
        target_doctype: The doctype we're looking for

    Returns:
        str: Name of the linked document, or None if not found
    """
    try:
        meta = frappe.get_meta(doc.doctype)

        # Check all Link fields in the document
        for field in meta.fields:
            if field.fieldtype == "Link" and field.options == target_doctype:
                linked_value = getattr(doc, field.fieldname, None)
                if linked_value:
                    return linked_value

        # Also check Dynamic Link fields
        for field in meta.fields:
            if field.fieldtype == "Dynamic Link":
                # Get the doctype field that this dynamic link references
                link_doctype_field = field.options
                if link_doctype_field and hasattr(doc, link_doctype_field):
                    actual_doctype = getattr(doc, link_doctype_field, None)
                    if actual_doctype == target_doctype:
                        linked_value = getattr(doc, field.fieldname, None)
                        if linked_value:
                            return linked_value

        return None

    except Exception as e:
        frappe.log_error(
            f"Error finding linked document: {str(e)}",
            f"WhatsApp Find Link Error - {doc.doctype}"
        )
        return None


# ============================================================================
# RECIPIENT PROCESSING
# ============================================================================

def process_notification_recipients(doc, notification):
    """
    Process all recipients from notification and return list of phone numbers

    Args:
        doc: Document object
        notification: WhatsApp Notification document

    Returns:
        list: [{"phone": str, "source": str}] - source indicates where phone came from
    """
    all_phones = []

    # Handle send_to_all_assignees flag
    if getattr(notification, 'send_to_all_assignees', False):
        assigned_phones = get_assigned_user_phone_numbers(doc)
        for assigned in assigned_phones:
            all_phones.append({
                'phone': assigned['phone'],
                'source': f"Assigned User: {assigned['user']}"
            })

    # Process linked documents child table
    linked_phones = get_linked_document_recipients(doc, notification)
    all_phones.extend(linked_phones)

    # Process recipients child table
    if not notification.recipients and not linked_phones:
        return all_phones

    if not notification.recipients:
        # Remove duplicates and return
        seen_phones = set()
        unique_phones = []
        for phone_data in all_phones:
            if phone_data['phone'] not in seen_phones:
                seen_phones.add(phone_data['phone'])
                unique_phones.append(phone_data)
        return unique_phones
    
    for recipient in notification.recipients:
        try:
            # Check recipient-level condition if exists
            if recipient.condition:
                if not evaluate_custom_condition(doc, recipient.condition):
                    frappe.log_error(
                        f"Recipient condition not met for {doc.name}",
                        f"WhatsApp Recipient Condition Skip - {doc.doctype}"
                    )
                    continue
            
            # Handle receiver_by_document_field
            if recipient.receiver_by_document_field:
                phone = get_phone_number_enhanced(doc, recipient.receiver_by_document_field)
                if phone:
                    all_phones.append({
                        'phone': phone,
                        'source': f"Field: {recipient.receiver_by_document_field}"
                    })
                else:
                    frappe.log_error(
                        f"No phone found for field '{recipient.receiver_by_document_field}' in {doc.name}",
                        f"WhatsApp Recipient Phone - {doc.doctype}"
                    )
            
            # Handle receiver_by_role
            if recipient.receiver_by_role:
                role_phones = get_phone_numbers_by_role(recipient.receiver_by_role)
                for role_phone in role_phones:
                    all_phones.append({
                        'phone': role_phone['phone'],
                        'source': f"Role: {recipient.receiver_by_role} - User: {role_phone['user']}"
                    })
                
                if not role_phones:
                    frappe.log_error(
                        f"No users with phone found for role '{recipient.receiver_by_role}'",
                        f"WhatsApp Role Phone - {doc.doctype}"
                    )
        
        except Exception as e:
            frappe.log_error(
                f"Error processing recipient: {str(e)}",
                f"WhatsApp Recipient Error - {doc.doctype}"
            )
            continue
    
    # Remove duplicates while preserving order
    seen_phones = set()
    unique_phones = []
    for phone_data in all_phones:
        if phone_data['phone'] not in seen_phones:
            seen_phones.add(phone_data['phone'])
            unique_phones.append(phone_data)
    
    return unique_phones


# ============================================================================
# CONDITION EVALUATION
# ============================================================================

def evaluate_custom_condition(doc, condition_code):
    """
    Evaluate custom condition code for WhatsApp notifications
    Similar to Frappe's notification system
    """
    if not condition_code or not condition_code.strip():
        return True  # No condition means always send
    
    try:
        # Prepare the context for condition evaluation
        context = {
            'doc': doc,
            'frappe': frappe,
            'nowdate': frappe.utils.nowdate,
            'now_datetime': frappe.utils.now_datetime,
            'add_days': frappe.utils.add_days,
            'date_diff': frappe.utils.date_diff,
            'cint': frappe.utils.cint,
            'cstr': frappe.utils.cstr,
            'flt': frappe.utils.flt
        }
        
        # Add all document fields to context
        try:
            valid_columns = doc.meta.get_valid_columns()
            for fieldname in valid_columns:
                if hasattr(doc, fieldname):
                    context[fieldname] = doc.get(fieldname)
        except:
            pass
        
        try:
            for field in doc.meta.fields:
                if hasattr(doc, field.fieldname):
                    context[field.fieldname] = doc.get(field.fieldname)
        except:
            pass
        
        try:
            for key in doc.as_dict():
                context[key] = doc.get(key)
        except:
            pass
        
        # Evaluate the condition
        result = frappe.safe_eval(condition_code, context)
        
        return bool(result)
        
    except Exception as e:
        frappe.log_error(
            f"Error evaluating condition: {str(e)}\nCondition: {condition_code}\nDocument: {doc.name}",
            f"WhatsApp Condition Error - {doc.doctype}"
        )
        return False


# ============================================================================
# DOCUMENT EVENT HANDLERS (IMMEDIATE NOTIFICATIONS)
# ============================================================================

def handle_whatsapp_notification_submit(doc, method):
    """Handle WhatsApp notification for submitted documents"""
    _handle_whatsapp_notification(doc, method, "Submit")


def handle_whatsapp_notification_save(doc, method):
    """Handle WhatsApp notification for saved documents"""
    _handle_whatsapp_notification(doc, method, "Save")


def handle_whatsapp_notification_cancel(doc, method):
    """Handle WhatsApp notification for cancelled documents"""
    _handle_whatsapp_notification(doc, method, "Cancel")


def handle_whatsapp_notification_creation(doc, method):
    """Handle WhatsApp notification for newly created documents"""
    _handle_whatsapp_notification(doc, method, "On Creation")


def handle_whatsapp_notification_update(doc, method):
    """Handle WhatsApp notification for updated documents"""
    if doc.is_new():
        return
    _handle_whatsapp_notification(doc, method, "On Update")


def _handle_whatsapp_notification(doc, method, trigger_event):
    """Unified WhatsApp notification handler for immediate events - enqueues background job"""
    try:
        # Skip internal/system doctypes to prevent recursion and performance issues
        excluded_doctypes = [
            'WhatsApp Notification', 'WhatsApp Notification Recipient',
            'WhatsApp Message Template', 'WhatsApp Setting', 'WhatsApp Linked Document',
            'Comment', 'Communication', 'Email Queue', 'Notification Log',
            'Activity Log', 'Error Log', 'Scheduled Job Log', 'Version',
            'Access Log', 'Route History', 'View Log', 'Energy Point Log',
            'Notification Settings', 'Web Form', 'Web Page', 'Portal Settings'
        ]

        if doc.doctype in excluded_doctypes:
            return

        settings = safe_get_settings()
        if not settings or not settings.enabled:
            return

        # Get matching notifications
        notifications = get_active_notifications(
            document_type=doc.doctype,
            event=trigger_event
        )

        if not notifications:
            return

        # Enqueue background job for each notification
        for notification_data in notifications:
            frappe.enqueue(
                "erpnext_enhancements.api.whatsapp_reminders.whatsapp.process_whatsapp_notification_background",
                doctype=doc.doctype,
                docname=doc.name,
                notification_name=notification_data.name,
                queue="default",
                timeout=300
            )
            frappe.logger("whatsapp_notification").info(
                f"WhatsApp notification queued for {doc.doctype} {doc.name} - Notification: {notification_data.name}"
            )

    except Exception as e:
        frappe.log_error(f"WhatsApp notification handler failed: {str(e)}",
                        f"DocType: {doc.doctype}, Name: {doc.name}")


def process_whatsapp_notification_background(doctype, docname, notification_name):
    """Background job to process WhatsApp notification and send messages"""
    job_logger = frappe.logger("whatsapp_background_job")
    job_logger.info(f"START: WhatsApp notification for {doctype} {docname} - Notification: {notification_name}")

    try:
        # Fetch the document
        doc = frappe.get_doc(doctype, docname)
        job_logger.info(f"SUCCESS: Fetched {doctype} document {doc.name}")

        # Fetch the notification
        notification = frappe.get_doc("WhatsApp Notification", notification_name)

        # Check notification-level condition
        if notification.condition:
            if not evaluate_custom_condition(doc, notification.condition):
                job_logger.info(f"Condition not met for notification {notification.name}")
                return

        # Get all recipient phone numbers
        recipients = process_notification_recipients(doc, notification)

        if not recipients:
            job_logger.info(f"No recipients found for notification {notification.name}")
            return

        # Build message once
        message = MessageTemplateHandler.build_message(doc, notification)
        job_logger.info(f"Message built for {len(recipients)} recipients")

        # Create WhatsApp handler
        whatsapp_handler = WhatsAppHandler()

        # Send to all recipients
        success_count = error_count = 0

        for recipient in recipients:
            try:
                if whatsapp_handler.send_message(
                    recipient['phone'], message, doc.doctype, doc.name
                ):
                    success_count += 1
                    job_logger.info(f"Message sent to {recipient['source']} ({recipient['phone']})")
                else:
                    error_count += 1
            except Exception as send_error:
                error_count += 1
                job_logger.error(f"Error sending to {recipient['source']}: {str(send_error)}")

        # Log summary
        job_logger.info(
            f"COMPLETE: Notification '{notification.name}' - {success_count} sent, {error_count} failed"
        )

    except Exception as e:
        job_logger.error(f"FAILED: {str(e)}")
        frappe.log_error(
            f"Background WhatsApp job failed: {str(e)}",
            f"WhatsApp Background Error - {doctype}"
        )


# ============================================================================
# SCHEDULED REMINDERS (DATE-BASED - DAILY CRON)
# ============================================================================

def send_scheduled_whatsapp_reminders_enhanced():
    """
    Main scheduler for date-based reminders (runs daily)
    Handles both document-level and child table reminders
    """
    settings = safe_get_settings()
    if not settings or not settings.enabled:
        frappe.log_error("WhatsApp reminders skipped", "WhatsApp Settings disabled")
        return

    # Get all scheduled reminder notifications (date-based only, not time-based)
    notifications = frappe.get_all(
        "WhatsApp Notification",
        filters={
            "enabled": 1,
            "event": "Scheduled Reminder",
            "add_timing": 0  # Only date-based reminders
        },
        fields=["name"]
    )

    for notification_data in notifications:
        try:
            notification = frappe.get_doc("WhatsApp Notification", notification_data.name)
            
            # Check if date_field is configured
            if not notification.date_field:
                frappe.log_error(
                    f"No date_field configured for notification {notification.name}",
                    "WhatsApp Reminder Config Error"
                )
                continue
            
            # Process the reminder
            if '.' in notification.date_field:
                # Child table reminder
                process_child_table_reminders(notification)
            else:
                # Document-level reminder
                process_document_reminders(notification)
                
        except Exception as e:
            frappe.log_error(
                f"Scheduler failed for notification {notification_data.name}: {str(e)}", 
                f"WhatsApp Scheduler Error"
            )


def process_document_reminders(notification):
    """Process document-level date-based reminders"""
    
    date_field = notification.date_field
    
    # Calculate target date based on days_before or days_after
    if notification.days_before:
        target_date = add_days(nowdate(), notification.days_before)
    elif notification.days_after:
        target_date = add_days(nowdate(), -(notification.days_after))
    else:
        target_date = nowdate()
    
    # Build filters
    filters = {date_field: target_date}
    
    # Exclude cancelled documents for submittable doctypes
    submittable_doctypes = [
        "Purchase Order", "Sales Order", "Purchase Invoice", 
        "Sales Invoice", "Delivery Note", "Purchase Receipt"
    ]
    
    if notification.document_type in submittable_doctypes:
        filters["docstatus"] = ["!=", 2]
    
    # Get matching documents
    try:
        docs = frappe.get_all(
            notification.document_type,
            filters=filters,
            fields=["name", "docstatus"] if notification.document_type in submittable_doctypes else ["name"]
        )
    except Exception as e:
        frappe.log_error(
            f"Error querying documents: {str(e)}",
            f"WhatsApp Reminder Query - {notification.document_type}"
        )
        return

    whatsapp_handler = WhatsAppHandler()
    success_count = error_count = condition_skip_count = 0

    for d in docs:
        try:
            # Skip cancelled documents
            if hasattr(d, 'docstatus') and d.docstatus == 2:
                continue
                
            doc = frappe.get_doc(notification.document_type, d.name)
            
            if hasattr(doc, 'docstatus') and doc.docstatus == 2:
                continue
            
            # Check notification-level condition
            if notification.condition:
                if not evaluate_custom_condition(doc, notification.condition):
                    condition_skip_count += 1
                    continue
            
            # Get recipients
            recipients = process_notification_recipients(doc, notification)
            
            if not recipients:
                error_count += 1
                continue

            # Build message
            message = MessageTemplateHandler.build_message(
                doc, notification,
                is_reminder=True,
                target_date=target_date
            )
            
            # Send to all recipients
            for recipient in recipients:
                try:
                    if whatsapp_handler.send_message(recipient['phone'], message, doc.doctype, doc.name):
                        success_count += 1
                    else:
                        error_count += 1
                except Exception as send_error:
                    error_count += 1
                    frappe.log_error(
                        f"Send failed to {recipient['source']}: {str(send_error)}",
                        f"WhatsApp Reminder Send Error"
                    )
                
        except Exception as e:
            frappe.log_error(f"Failed to process reminder for {d.name}: {str(e)}", 
                           f"WhatsApp Reminder Error")
            error_count += 1

    # Log summary
    if success_count > 0 or error_count > 0 or condition_skip_count > 0:
        frappe.log_error(
            f"Reminders processed for {notification.name} - Success: {success_count}, "
            f"Errors: {error_count}, Condition Skips: {condition_skip_count}", 
            f"WhatsApp Reminder Summary - {notification.document_type}"
        )


# ============================================================================
# SCHEDULED REMINDERS (TIME-BASED - HOURLY CRON)
# ============================================================================

def process_scheduled_whatsapp_time_reminders():
    """Process time-based WhatsApp reminders (runs hourly)"""
    settings = safe_get_settings()
    if not settings or not settings.enabled:
        frappe.log_error("WhatsApp time reminders skipped", "WhatsApp Settings disabled")
        return
    
    # Get all time-based reminder notifications
    notifications = frappe.get_all(
        "WhatsApp Notification",
        filters={
            "enabled": 1,
            "event": "Scheduled Reminder",
            "add_timing": 1  # Only time-based reminders
        },
        fields=["name"]
    )
    
    if not notifications:
        frappe.log_error("No time-based WhatsApp notifications found", "WhatsApp Time Reminder")
        return
    
    for notification_data in notifications:
        try:
            notification = frappe.get_doc("WhatsApp Notification", notification_data.name)
            
            # Validate time-based fields
            if not notification.time_field or not notification.hours_before:
                frappe.log_error(
                    f"Incomplete time config for notification {notification.name}",
                    "WhatsApp Time Config Error"
                )
                continue
            
            process_time_based_reminders(notification)
            
        except Exception as e:
            frappe.log_error(
                f"Time reminder failed for {notification_data.name}: {str(e)}", 
                f"WhatsApp Time Reminder Error"
            )


def process_time_based_reminders(notification):
    """Process time-based reminders for a notification"""
    
    current_datetime = now_datetime()
    current_date = current_datetime.date()
    
    # Calculate time range for checking
    hours_before = notification.hours_before
    target_start_time = current_datetime
    target_end_time = add_to_date(current_datetime, hours=hours_before)
    
    frappe.log_error(
        f"Processing time reminders: {notification.document_type}, "
        f"Time range: {target_start_time.strftime('%H:%M')} - {target_end_time.strftime('%H:%M')}", 
        f"WhatsApp Time Debug - {notification.document_type}"
    )
    
    # Get documents with today's date in the date_field
    date_filters = {notification.date_field: current_date}
    
    # Exclude cancelled documents for submittable doctypes
    submittable_doctypes = [
        "Purchase Order", "Sales Order", "Purchase Invoice", 
        "Sales Invoice", "Delivery Note", "Purchase Receipt"
    ]
    
    if notification.document_type in submittable_doctypes:
        date_filters["docstatus"] = ["!=", 2]
    
    try:
        docs = frappe.get_all(
            notification.document_type,
            filters=date_filters,
            fields=["name", "docstatus", notification.time_field] if notification.document_type in submittable_doctypes 
            else ["name", notification.time_field]
        )
    except Exception as e:
        frappe.log_error(f"Error querying documents: {str(e)}", 
                        f"WhatsApp Time Query Error - {notification.document_type}")
        return
    
    whatsapp_handler = WhatsAppHandler()
    success_count = error_count = condition_skip_count = time_skip_count = 0
    
    for d in docs:
        try:
            # Skip cancelled documents
            if hasattr(d, 'docstatus') and d.docstatus == 2:
                continue
            
            doc = frappe.get_doc(notification.document_type, d.name)
            
            if hasattr(doc, 'docstatus') and doc.docstatus == 2:
                continue
            
            # Get the time field value
            time_field_value = getattr(doc, notification.time_field, None)
            if not time_field_value:
                time_skip_count += 1
                continue
            
            # Check if time falls within our target range
            if not is_time_in_range(time_field_value, target_start_time, target_end_time):
                time_skip_count += 1
                continue
            
            # Check notification-level condition
            if notification.condition:
                if not evaluate_custom_condition(doc, notification.condition):
                    condition_skip_count += 1
                    continue
            
            # Get recipients
            recipients = process_notification_recipients(doc, notification)
            
            if not recipients:
                error_count += 1
                frappe.log_error(f"No recipients found for {doc.name}", 
                               f"WhatsApp Time Recipients Error - {notification.document_type}")
                continue
            
            # Build message with time information
            message = MessageTemplateHandler.build_message(
                doc, notification,
                is_reminder=True,
                target_date=current_date,
                target_time=time_field_value
            )
            
            # Send to all recipients
            for recipient in recipients:
                try:
                    if whatsapp_handler.send_message(recipient['phone'], message, doc.doctype, doc.name):
                        success_count += 1
                        frappe.log_error(
                            f"Time reminder sent for {doc.name} at {time_field_value} to {recipient['source']}", 
                            f"WhatsApp Time Success - {notification.document_type}"
                        )
                    else:
                        error_count += 1
                except Exception as send_error:
                    error_count += 1
                    frappe.log_error(
                        f"Send failed to {recipient['source']}: {str(send_error)}",
                        f"WhatsApp Time Send Error"
                    )
                
        except Exception as e:
            frappe.log_error(f"Failed to process time reminder for {d.name}: {str(e)}", 
                           f"WhatsApp Time Processing Error - {notification.document_type}")
            error_count += 1
    
    # Log summary
    if success_count > 0 or error_count > 0 or condition_skip_count > 0 or time_skip_count > 0:
        frappe.log_error(
            f"Time reminders processed for {notification.name} - Success: {success_count}, Errors: {error_count}, "
            f"Condition Skips: {condition_skip_count}, Time Skips: {time_skip_count}", 
            f"WhatsApp Time Summary - {notification.document_type}"
        )


def is_time_in_range(time_field_value, start_datetime, end_datetime):
    """Check if the time field value falls within the target time range"""
    try:
        # Handle different time field types
        if isinstance(time_field_value, datetime):
            appointment_datetime = time_field_value
        elif isinstance(time_field_value, time):
            today = start_datetime.date()
            appointment_datetime = datetime.combine(today, time_field_value)
        elif isinstance(time_field_value, timedelta):
            midnight = datetime.combine(start_datetime.date(), time.min)
            appointment_datetime = midnight + time_field_value
            
            frappe.log_error(
                f"Timedelta converted: {time_field_value} -> {appointment_datetime.strftime('%H:%M')}", 
                "WhatsApp Timedelta Debug"
            )
        elif isinstance(time_field_value, str):
            try:
                parsed_time = datetime.strptime(time_field_value, "%H:%M").time()
                today = start_datetime.date()
                appointment_datetime = datetime.combine(today, parsed_time)
            except ValueError:
                try:
                    appointment_datetime = datetime.strptime(time_field_value, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    try:
                        time_parts = time_field_value.split(':')
                        if len(time_parts) >= 2:
                            hours = int(time_parts[0])
                            minutes = int(time_parts[1])
                            seconds = int(time_parts[2]) if len(time_parts) > 2 else 0
                            
                            appointment_time = time(hours, minutes, seconds)
                            today = start_datetime.date()
                            appointment_datetime = datetime.combine(today, appointment_time)
                        else:
                            frappe.log_error(f"Could not parse time string: {time_field_value}", "WhatsApp Time Parse Error")
                            return False
                    except (ValueError, IndexError):
                        frappe.log_error(f"Could not parse time value: {time_field_value}", "WhatsApp Time Parse Error")
                        return False
        else:
            frappe.log_error(f"Unsupported time field type: {type(time_field_value)}", "WhatsApp Time Type Error")
            return False
        
        # Check if appointment datetime falls within our target range
        is_in_range = start_datetime <= appointment_datetime <= end_datetime
        
        frappe.log_error(
            f"Time check: {appointment_datetime.strftime('%H:%M')} between "
            f"{start_datetime.strftime('%H:%M')} - {end_datetime.strftime('%H:%M')}: {is_in_range}", 
            "WhatsApp Time Range Debug"
        )
        
        return is_in_range
        
    except Exception as e:
        frappe.log_error(f"Error checking time range: {str(e)}", "WhatsApp Time Range Error")
        return False


# ============================================================================
# CHILD TABLE REMINDERS
# ============================================================================

def process_child_table_reminders(notification):
    """Process child table reminders based on date_field notation"""
    
    date_field = notification.date_field
    
    if '.' not in date_field:
        frappe.log_error("Invalid child table field format. Use 'table_field.date_field'", 
                        f"Child Table Config Error - {notification.document_type}")
        return
    
    child_table_field, child_date_field = date_field.split('.', 1)
    
    # Validate fields
    parent_meta = frappe.get_meta(notification.document_type)
    table_field_meta = parent_meta.get_field(child_table_field)
    
    if not table_field_meta or table_field_meta.fieldtype != "Table":
        frappe.log_error(f"Invalid child table field '{child_table_field}'", 
                        f"Child Table Field Error - {notification.document_type}")
        return
    
    child_doctype = table_field_meta.options
    child_meta = frappe.get_meta(child_doctype)
    if not child_meta.get_field(child_date_field):
        frappe.log_error(f"Date field '{child_date_field}' not found in {child_doctype}", 
                        f"Child Date Field Error - {notification.document_type}")
        return
    
    # Calculate target date
    if notification.days_before:
        target_date = add_days(nowdate(), notification.days_before)
    elif notification.days_after:
        target_date = add_days(nowdate(), -(notification.days_after))
    else:
        target_date = nowdate()
    
    # Get parent documents with matching child records
    parent_docs = get_parents_with_matching_child_dates(
        notification.document_type,
        child_table_field,
        child_doctype,
        child_date_field,
        target_date
    )
    
    whatsapp_handler = WhatsAppHandler()
    success_count = error_count = condition_skip_count = 0
    
    for parent_info in parent_docs:
        try:
            parent_doc = frappe.get_doc(notification.document_type, parent_info['name'])
            
            # Skip cancelled documents
            if hasattr(parent_doc, 'docstatus') and parent_doc.docstatus == 2:
                continue
            
            # Check notification-level condition
            if notification.condition:
                if not evaluate_custom_condition(parent_doc, notification.condition):
                    condition_skip_count += 1
                    continue
            
            # Get recipients
            recipients = process_notification_recipients(parent_doc, notification)
            
            if not recipients:
                frappe.log_error(f"No recipients found for {parent_doc.name}", 
                               f"Child Reminder Recipients - {notification.document_type}")
                error_count += 1
                continue
            
            # Get matching child records
            child_table = getattr(parent_doc, child_table_field, [])
            matching_children = []
            
            for child_row in child_table:
                child_due_date = getattr(child_row, child_date_field, None)
                if child_due_date and str(child_due_date) == str(target_date):
                    matching_children.append(child_row)
            
            if not matching_children:
                continue
            
            # Send messages for each child record to all recipients
            for child_row in matching_children:
                message = build_child_message(
                    parent_doc, child_row, notification, target_date,
                    child_table_field, child_date_field
                )
                
                for recipient in recipients:
                    try:
                        if whatsapp_handler.send_message(recipient['phone'], message, parent_doc.doctype, parent_doc.name):
                            success_count += 1
                        else:
                            error_count += 1
                    except Exception as send_error:
                        error_count += 1
                        frappe.log_error(
                            f"Send failed to {recipient['source']}: {str(send_error)}",
                            f"Child Reminder Send Error"
                        )
                        
        except Exception as e:
            frappe.log_error(
                f"Child table reminder failed for {parent_info['name']}: {str(e)}", 
                f"Child Reminder Error - {notification.document_type}"
            )
            error_count += 1
    
    # Log summary
    frappe.log_error(
        f"Child table reminders ({child_table_field}.{child_date_field}) for {notification.name} - "
        f"Success: {success_count}, Errors: {error_count}, Condition Skips: {condition_skip_count}", 
        f"Child Reminder Summary - {notification.document_type}"
    )


def get_parents_with_matching_child_dates(parent_doctype, child_table_field, 
                                        child_doctype, child_date_field, target_date):
    """Get parent documents that have child records with matching due dates"""
    try:
        child_table_name = f"tab{child_doctype.replace(' ', ' ')}"
        parent_table_name = f"tab{parent_doctype.replace(' ', ' ')}"
        
        query = f"""
            SELECT DISTINCT p.name
            FROM `{parent_table_name}` p
            INNER JOIN `{child_table_name}` c ON c.parent = p.name
            WHERE c.{child_date_field} = %s
            AND c.parenttype = %s
            AND c.parentfield = %s
            AND p.docstatus != 2
        """
        
        results = frappe.db.sql(
            query,
            (target_date, parent_doctype, child_table_field),
            as_dict=True
        )
        
        frappe.log_error(
            f"Found {len(results)} parent documents with matching child dates for {target_date}", 
            f"Child Query Result - {parent_doctype}"
        )
        
        return results
        
    except Exception as e:
        frappe.log_error(f"Error querying child table dates: {str(e)}", 
                        f"Child Query Error - {parent_doctype}")
        return []


def build_child_message(parent_doc, child_row, notification, target_date,
                       child_table_field, child_date_field):
    """Build message for individual child record"""
    
    # Try template first
    if notification.message:
        try:
            template_doc = frappe.get_doc("WhatsApp Message Template", notification.message)
            if template_doc and template_doc.is_active and template_doc.template_text:
                return process_child_template(
                    template_doc.template_text, parent_doc, child_row, target_date
                )
        except Exception as e:
            frappe.log_error(f"Child template processing failed: {str(e)}", 
                           f"Child Template Error - {notification.document_type}")
    
    # Build default message
    return build_default_child_message(parent_doc, child_row, target_date, child_table_field)


def process_child_template(template_text, parent_doc, child_row, target_date):
    """Process template with automatic placeholder detection for child tables"""
    
    template_text = MessageTemplateHandler.clean_html(template_text)
    
    # Build parent document placeholders
    placeholders = MessageTemplateHandler._build_placeholders(parent_doc, target_date)
    
    # Add child placeholders
    child_placeholders = {}
    common_child_fields = [
        'amount', 'payment_amount', 'due_date', 'description',
        'idx', 'total', 'installment_amount', 'remarks'
    ]
    
    for field in common_child_fields:
        if hasattr(child_row, field):
            value = getattr(child_row, field)
            if value is not None:
                if hasattr(value, 'strftime'):
                    try:
                        value = formatdate(value)
                    except:
                        value = str(value)
                
                # Add multiple placeholder formats
                child_placeholders[f'{{child_{field}}}'] = str(value)
                child_placeholders[f'{{child.{field}}}'] = str(value)
                child_placeholders[f'{{{field}}}'] = str(value)
    
    # Merge and replace placeholders
    all_placeholders = {**placeholders, **child_placeholders}
    message = template_text
    
    for placeholder, value in all_placeholders.items():
        message = message.replace(placeholder, str(value))
    
    # Handle remaining dynamic placeholders
    remaining_patterns = re.findall(r'\{([^}]+)\}', message)
    for pattern in remaining_patterns:
        if hasattr(child_row, pattern):
            value = getattr(child_row, pattern)
            if value is not None:
                if hasattr(value, 'strftime'):
                    try:
                        value = formatdate(value)
                    except:
                        value = str(value)
                message = message.replace(f'{{{pattern}}}', str(value))
        elif hasattr(parent_doc, pattern):
            value = getattr(parent_doc, pattern)
            if value is not None:
                if hasattr(value, 'strftime'):
                    try:
                        value = formatdate(value)
                    except:
                        value = str(value)
                message = message.replace(f'{{{pattern}}}', str(value))
        else:
            message = message.replace(f'{{{pattern}}}', '')
    
    message = MessageTemplateHandler.format_whatsapp_message(message)
    
    return message


def build_default_child_message(parent_doc, child_row, target_date, child_table_field):
    """Build default message for child table reminder"""
    
    # Get amount from common field names
    amount = (getattr(child_row, 'payment_amount', None) or
             getattr(child_row, 'amount', None) or
             getattr(child_row, 'total', None))
    
    # Get description
    description = (getattr(child_row, 'description', None) or
                  getattr(child_row, 'remarks', None) or
                  f"Item {getattr(child_row, 'idx', '')}")
    
    # Build message
    message = f"Reminder: {parent_doc.doctype} *{parent_doc.name}*\n"
    
    if child_table_field == 'payment_schedule':
        message += f"Payment due on {formatdate(target_date)}\n"
    else:
        message += f"Due date: {formatdate(target_date)}\n"
    
    if amount:
        message += f"Amount: ₹{amount}\n"
    
    if description:
        message += f"Description: {description}\n"
    
    message = MessageTemplateHandler.format_whatsapp_message(message)
    
    return message.strip()


# ============================================================================
# CLIENT SCRIPT BASED - MANUAL SENDING
# ============================================================================

@frappe.whitelist()
def send_manual_whatsapp_message(doctype, docname, phone_number, message, template_name=None):
    """
    Backend API for manual WhatsApp message sending from frontend
    
    Args:
        doctype: Document type
        docname: Document name/ID
        phone_number: Phone number to send to
        message: Message text
        template_name: Optional template name
    
    Returns:
        dict: {"success": bool, "message": str, "phone_used": str}
    """
    try:
        if not frappe.has_permission(doctype, "read", docname):
            frappe.throw("Insufficient permissions to send WhatsApp message")
        
        doc = frappe.get_doc(doctype, docname)
        whatsapp_handler = WhatsAppHandler()
        
        if not whatsapp_handler.is_enabled():
            return {
                "success": False,
                "message": "WhatsApp is not configured or disabled",
                "phone_used": None
            }
        
        clean_phone = whatsapp_handler._clean_phone_number(phone_number)
        if not clean_phone:
            return {
                "success": False,
                "message": f"Invalid phone number: {phone_number}",
                "phone_used": phone_number
            }
        
        # Process message (if template is provided)
        processed_message = message
        if template_name:
            try:
                processed_message = process_template_for_manual_send(
                    doc, template_name, message
                )
            except Exception as e:
                frappe.log_error(f"Template processing failed: {str(e)}", 
                               f"Manual WhatsApp Template Error")
        
        success = whatsapp_handler.send_message(
            clean_phone,
            processed_message,
            doctype,
            docname
        )
        
        if success:
            add_whatsapp_comment(doc, clean_phone, processed_message)
            
            return {
                "success": True,
                "message": f"WhatsApp message sent successfully to +91{clean_phone}",
                "phone_used": f"+91{clean_phone}"
            }
        else:
            return {
                "success": False,
                "message": "Failed to send WhatsApp message. Check error logs.",
                "phone_used": f"+91{clean_phone}"
            }
            
    except frappe.PermissionError:
        return {
            "success": False,
            "message": "You don't have permission to send WhatsApp messages for this document",
            "phone_used": None
        }
    except Exception as e:
        frappe.log_error(f"Manual WhatsApp send failed: {str(e)}", 
                        f"Manual WhatsApp Error - {doctype}")
        return {
            "success": False,
            "message": f"Error sending message: {str(e)}",
            "phone_used": phone_number
        }


@frappe.whitelist()
def get_whatsapp_phone_number(doctype, docname, phone_field=None):
    """Get phone number for a document"""
    try:
        if not frappe.has_permission(doctype, "read", docname):
            return {"phone": None, "field_used": None, "formatted_phone": None}
        
        doc = frappe.get_doc(doctype, docname)
        
        if phone_field:
            phone = get_phone_number_enhanced(doc, phone_field)
            if phone:
                return {
                    "phone": phone,
                    "field_used": phone_field,
                    "formatted_phone": f"+91{phone}"
                }
        
        # Auto-detect phone number
        common_phone_fields = [
            'mobile_no', 'mobile', 'phone', 'cell_number', 'whatsapp_number',
            'contact_mobile', 'primary_mobile_no'
        ]
        
        for field in common_phone_fields:
            if hasattr(doc, field):
                phone = get_phone_number_enhanced(doc, field)
                if phone:
                    return {
                        "phone": phone,
                        "field_used": field,
                        "formatted_phone": f"+91{phone}"
                    }
        
        return {"phone": None, "field_used": None, "formatted_phone": None}
        
    except Exception as e:
        frappe.log_error(f"Error getting phone number: {str(e)}", 
                        f"Phone Number Error - {doctype}")
        return {"phone": None, "field_used": None, "formatted_phone": None}


@frappe.whitelist()
def get_whatsapp_templates(doctype=None):
    """Get available WhatsApp message templates"""
    try:
        filters = {"is_active": 1}
        if doctype:
            filters["applicable_doctype"] = doctype
        
        templates = frappe.get_all(
            "WhatsApp Message Template",
            filters=filters,
            fields=["name", "template_name", "template_text", "applicable_doctype"]
        )
        
        return templates
        
    except Exception as e:
        frappe.log_error(f"Error getting templates: {str(e)}", "WhatsApp Templates Error")
        return []


@frappe.whitelist()
def preview_whatsapp_template(doctype, docname, template_name):
    """Preview how a template will look with current document data"""
    try:
        if not frappe.has_permission(doctype, "read", docname):
            return {
                "success": False,
                "preview": "",
                "error": "Insufficient permissions"
            }
        
        doc = frappe.get_doc(doctype, docname)
        template_doc = frappe.get_doc("WhatsApp Message Template", template_name)
        
        if not template_doc.is_active:
            return {
                "success": False,
                "preview": "",
                "error": "Template is not active"
            }
        
        preview_message = MessageTemplateHandler._process_template(
            template_doc.template_text,
            doc
        )
        
        return {
            "success": True,
            "preview": preview_message,
            "error": None
        }
        
    except Exception as e:
        frappe.log_error(f"Template preview failed: {str(e)}", 
                        f"Template Preview Error - {doctype}")
        return {
            "success": False,
            "preview": "",
            "error": str(e)
        }


def process_template_for_manual_send(doc, template_name, fallback_message):
    """Process template for manual sending"""
    try:
        if not template_name:
            return fallback_message
        
        template_doc = frappe.get_doc("WhatsApp Message Template", template_name)
        
        if not template_doc.is_active:
            return fallback_message
        
        return MessageTemplateHandler._process_template(
            template_doc.template_text,
            doc
        )
        
    except Exception as e:
        frappe.log_error(f"Template processing failed in manual send: {str(e)}", 
                        "Manual Template Error")
        return fallback_message


def add_whatsapp_comment(doc, phone_number, message):
    """Add a comment to document timeline when WhatsApp is sent manually"""
    try:
        short_message = message[:100] + "..." if len(message) > 100 else message
        
        comment_text = f"""
WhatsApp Message Sent
📱 Phone: +91{phone_number}
📝 Message: {short_message}
👤 Sent by: {frappe.session.user}
        """.strip()
        
        frappe.get_doc({
            "doctype": "Comment",
            "comment_type": "Info",
            "reference_doctype": doc.doctype,
            "reference_name": doc.name,
            "content": comment_text
        }).insert(ignore_permissions=True)
        
    except Exception as e:
        frappe.log_error(f"Failed to add WhatsApp comment: {str(e)}", 
                        f"WhatsApp Comment Error - {doc.doctype}")


@frappe.whitelist()
def check_whatsapp_settings():
    """Check if WhatsApp is configured and enabled"""
    try:
        settings = safe_get_settings()
        
        if not settings:
            return {
                "enabled": False,
                "configured": False,
                "message": "WhatsApp Settings not found"
            }
        
        if not settings.enabled:
            return {
                "enabled": False,
                "configured": True,
                "message": "WhatsApp is disabled in settings"
            }
        
        if not settings.instance_id or not settings.access_token:
            return {
                "enabled": False,
                "configured": False,
                "message": "WhatsApp API credentials not configured"
            }
        
        return {
            "enabled": True,
            "configured": True,
            "message": "WhatsApp is ready"
        }
        
    except Exception as e:
        frappe.log_error(f"Error checking WhatsApp settings: {str(e)}", 
                        "WhatsApp Settings Check Error")
        return {
            "enabled": False,
            "configured": False,
            "message": f"Error: {str(e)}"
        }


# ============================================================================
# UTILITY AND TEST FUNCTIONS
# ============================================================================

def test_whatsapp_connection():
    """Test WhatsApp API connection"""
    whatsapp_handler = WhatsAppHandler()
    
    if not whatsapp_handler.is_enabled():
        return {"status": "error", "message": "WhatsApp settings not configured"}
    
    test_message = "Test message from Frappe system."
    test_number = "1234567890"  # Replace with actual test number
    
    result = whatsapp_handler.send_message(test_number, test_message, "Test", "Test")
    
    return {
        "status": "success" if result else "error",
        "message": "Test message sent" if result else "Test message failed"
    }