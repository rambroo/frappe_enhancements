import requests
import frappe
import re
from frappe.utils import add_days, nowdate, date_diff, formatdate
import frappe
from frappe.utils import now_datetime, get_datetime, add_to_date, time_diff_in_seconds, get_time
from datetime import datetime, timedelta
import pytz


# Add these validation and helper functions to your whatsapp_handler.py

def validate_timing_configuration(config):
    """
    Validate timing-based WhatsApp configuration
    Call this from your WhatsApp Settings validation
    """
    if not getattr(config, 'custom_add_timing', False):
        return True  # No timing configuration, nothing to validate
    
    timing_type = getattr(config, 'custom_timing', None)
    
    if not timing_type:
        frappe.throw("Please select timing type (Field or Dedicated) when timing is enabled")
    
    if timing_type == "Field":
        # Validate field-based timing
        fieldname = getattr(config, 'custom_fieldname', None)
        if not fieldname:
            frappe.throw("Please specify field name for field-based timing")
        
        # Check if field exists in doctype
        meta = frappe.get_meta(config.table_doctype)
        field = meta.get_field(fieldname)
        
        if not field:
            frappe.throw(f"Field '{fieldname}' does not exist in {config.table_doctype}")
        
        if field.fieldtype not in ['Datetime', 'Date', 'Time']:
            frappe.throw(f"Field '{fieldname}' must be of type Datetime, Date, or Time for timing-based reminders")
        
        # Validate time before setting
        time_before = getattr(config, 'custom_time_before_minutes', 60)
        if not isinstance(time_before, (int, float)) or time_before <= 0:
            frappe.throw("Time before field must be a positive number (in minutes)")
    
    elif timing_type == "Dedicated":
        # Validate dedicated time
        dedicated_time = getattr(config, 'custom_time', None)
        if not dedicated_time:
            frappe.throw("Please specify dedicated time for dedicated time reminders")
    
    return True


def get_datetime_fields_for_doctype(doctype):
    """
    Get list of datetime/date fields for a doctype
    This can be used in your frontend to populate field options
    """
    try:
        meta = frappe.get_meta(doctype)
        datetime_fields = []
        
        for field in meta.fields:
            if field.fieldtype in ['Datetime', 'Date']:
                datetime_fields.append({
                    'fieldname': field.fieldname,
                    'label': field.label or field.fieldname,
                    'fieldtype': field.fieldtype
                })
        
        return datetime_fields
    except Exception as e:
        frappe.log_error(f"Error getting datetime fields for {doctype}: {str(e)}", 
                        "WhatsApp Field Lookup Error")
        return []


@frappe.whitelist()
def get_timing_field_options(doctype):
    """
    API method to get datetime field options for frontend
    """
    if not doctype:
        return []
    
    return get_datetime_fields_for_doctype(doctype)


def test_timing_configuration(config_name=None):
    """
    Test timing configuration without sending actual messages
    """
    settings = safe_get_settings()
    if not settings:
        return {"error": "WhatsApp Settings not found"}
    
    if config_name:
        # Test specific configuration
        config = None
        for c in settings.whatsapp_doctypes:
            if c.name == config_name:
                config = c
                break
        
        if not config:
            return {"error": f"Configuration {config_name} not found"}
        
        configs_to_test = [config]
    else:
        # Test all timing configurations
        configs_to_test = [
            config for config in settings.whatsapp_doctypes
            if (config.enable_whatsapp and 
                getattr(config, 'custom_add_timing', False) and
                getattr(config, 'custom_timing', None))
        ]
    
    results = []
    current_datetime = now_datetime()
    
    for config in configs_to_test:
        try:
            result = {
                "doctype": config.table_doctype,
                "timing_type": config.custom_timing,
                "status": "valid",
                "messages": []
            }
            
            if config.custom_timing == "Field":
                # Test field-based configuration
                fieldname = getattr(config, 'custom_fieldname', '')
                time_before = getattr(config, 'custom_time_before_minutes', 60)
                
                result["fieldname"] = fieldname
                result["time_before_minutes"] = time_before
                
                # Check if field exists
                try:
                    meta = frappe.get_meta(config.table_doctype)
                    field = meta.get_field(fieldname)
                    
                    if field:
                        result["field_type"] = field.fieldtype
                        result["messages"].append(f"Field '{fieldname}' found ({field.fieldtype})")
                        
                        # Test query for matching documents
                        target_start = add_to_date(current_datetime, minutes=time_before)
                        target_end = add_to_date(current_datetime, minutes=time_before + 15)
                        
                        count = frappe.db.count(config.table_doctype, {
                            fieldname: ["between", [target_start, target_end]]
                        })
                        
                        result["matching_docs"] = count
                        result["messages"].append(f"Found {count} documents in target time range")
                    else:
                        result["status"] = "error"
                        result["messages"].append(f"Field '{fieldname}' not found")
                        
                except Exception as field_error:
                    result["status"] = "error"
                    result["messages"].append(f"Field validation error: {str(field_error)}")
            
            elif config.custom_timing == "Dedicated":
                # Test dedicated time configuration
                dedicated_time = getattr(config, 'custom_time', None)
                
                if dedicated_time:
                    result["dedicated_time"] = str(dedicated_time)
                    result["messages"].append(f"Dedicated time set to {dedicated_time}")
                    
                    # Count total documents for this doctype
                    count = frappe.db.count(config.table_doctype)
                    result["total_docs"] = count
                    result["messages"].append(f"Total documents: {count}")
                else:
                    result["status"] = "error"
                    result["messages"].append("Dedicated time not set")
            
            # Test phone field
            if config.phone_field:
                result["messages"].append(f"Phone field: {config.phone_field}")
            else:
                result["status"] = "error"
                result["messages"].append("Phone field not configured")
                
        except Exception as e:
            result = {
                "doctype": config.table_doctype,
                "status": "error",
                "messages": [f"Configuration test failed: {str(e)}"]
            }
        
        results.append(result)
    
    return {
        "test_time": current_datetime.strftime('%Y-%m-%d %H:%M:%S'),
        "total_configs": len(results),
        "results": results
    }


def cleanup_old_timing_logs(days_to_keep=7):
    """
    Clean up old timing reminder logs to prevent database bloat
    Run this weekly
    """
    try:
        cutoff_date = add_to_date(frappe.utils.nowdate(), days=-days_to_keep)
        
        # Delete old timing reminder logs
        frappe.db.sql("""
            DELETE FROM `tabError Log`
            WHERE method LIKE 'WhatsApp Timing Reminder Sent%'
            AND creation < %s
        """, (cutoff_date,))
        
        frappe.db.commit()
        
        frappe.log_error(
            f"Cleaned up timing reminder logs older than {cutoff_date}",
            "WhatsApp Timing Log Cleanup"
        )
        
    except Exception as e:
        frappe.log_error(f"Error cleaning up timing logs: {str(e)}", 
                        "WhatsApp Timing Cleanup Error")


# Add this to your weekly scheduler in hooks.py
def weekly_timing_cleanup():
    """Weekly cleanup of timing reminder logs"""
    cleanup_old_timing_logs(days_to_keep=7)


# Example of how to add field validation in your WhatsApp Settings doctype
def validate_whatsapp_doctype_timing(doc, method):
    """
    Add this to your WhatsApp Doctype validation
    """
    for config in doc.whatsapp_doctypes:
        if getattr(config, 'custom_add_timing', False):
            validate_timing_configuration(config)

def process_timing_based_whatsapp_reminders():
    """
    Process timing-based WhatsApp reminders (called every 15 minutes)
    This handles both field-based timing and dedicated time reminders
    """
    settings = safe_get_settings()
    if not settings or not settings.enabled:
        return

    current_datetime = now_datetime()
    current_time = current_datetime.time()
    
    # Get all timing-based configurations
    timing_configs = [
        config for config in settings.whatsapp_doctypes
        if (config.enable_whatsapp and 
            getattr(config, 'custom_add_timing', False) and
            getattr(config, 'custom_timing', None))
    ]

    for config in timing_configs:
        try:
            if config.custom_timing == "Field":
                process_field_based_timing_reminders(config, current_datetime)
            elif config.custom_timing == "Dedicated":
                process_dedicated_time_reminders(config, current_datetime, current_time)
        except Exception as e:
            frappe.log_error(
                f"Timing-based reminder failed for {config.table_doctype}: {str(e)}", 
                f"WhatsApp Timing Error"
            )


def process_field_based_timing_reminders(config, current_datetime):
    """
    Process field-based timing reminders
    Send message X hours/minutes before the datetime field value
    """
    if not config.custom_fieldname:
        frappe.log_error(
            f"Field name not specified for timing-based reminder in {config.table_doctype}",
            "WhatsApp Timing Config Error"
        )
        return
    
    # Get the time buffer (how much before the field time to send)
    time_before_minutes = getattr(config, 'custom_time_before_minutes', 60)  # Default 60 minutes
    
    # Calculate the target datetime range (15-minute window for scheduler)
    target_start = add_to_date(current_datetime, minutes=time_before_minutes)
    target_end = add_to_date(current_datetime, minutes=time_before_minutes + 15)
    
    # Build filters for documents
    filters = {
        config.custom_fieldname: ["between", [target_start, target_end]]
    }
    
    # Exclude cancelled documents for submittable doctypes
    submittable_doctypes = [
        "Purchase Order", "Sales Order", "Purchase Invoice", 
        "Sales Invoice", "Delivery Note", "Purchase Receipt"
    ]
    
    if config.table_doctype in submittable_doctypes:
        filters["docstatus"] = ["!=", 2]
    
    # Get matching documents
    docs = frappe.get_all(
        config.table_doctype,
        filters=filters,
        fields=["name", "docstatus"] if config.table_doctype in submittable_doctypes else ["name"]
    )
    
    if not docs:
        return
    
    whatsapp_handler = WhatsAppHandler()
    success_count = error_count = condition_skip_count = 0
    
    for d in docs:
        try:
            doc = frappe.get_doc(config.table_doctype, d.name)
            
            # Skip cancelled documents
            if hasattr(doc, 'docstatus') and doc.docstatus == 2:
                continue
            
            # Check if we already sent a reminder for this document today
            if has_timing_reminder_been_sent_today(doc.doctype, doc.name, "field_based"):
                continue
            
            # Check custom condition
            if hasattr(config, 'custom_condition') and config.custom_condition:
                if not evaluate_custom_condition(doc, config.custom_condition):
                    condition_skip_count += 1
                    continue
            
            # Get phone number
            phone = get_phone_number_enhanced(doc, config.phone_field)
            if not phone:
                error_count += 1
                continue
            
            # Get the actual datetime value from the field
            field_datetime = getattr(doc, config.custom_fieldname, None)
            if not field_datetime:
                continue
            
            # Build message
            message = MessageTemplateHandler.build_message(
                doc, config,
                is_reminder=True,
                target_date=field_datetime,
                trigger_event="Timing Reminder"
            )
            
            # Add timing context to message
            time_remaining = time_diff_in_seconds(field_datetime, current_datetime) / 3600  # Hours
            if time_remaining > 0:
                if time_remaining >= 1:
                    time_text = f"{int(time_remaining)} hour{'s' if int(time_remaining) != 1 else ''}"
                else:
                    time_text = f"{int(time_remaining * 60)} minute{'s' if int(time_remaining * 60) != 1 else ''}"
                
                message += f"\n\n⏰ Time remaining: {time_text}"
            
            # Send message
            if whatsapp_handler.send_message(phone, message, doc.doctype, doc.name):
                success_count += 1
                # Log that reminder was sent
                log_timing_reminder_sent(doc.doctype, doc.name, "field_based")
            else:
                error_count += 1
                
        except Exception as e:
            frappe.log_error(
                f"Field-based timing reminder failed for {d.name}: {str(e)}", 
                f"WhatsApp Field Timing Error - {config.table_doctype}"
            )
            error_count += 1
    
    # Log summary
    if success_count > 0 or error_count > 0 or condition_skip_count > 0:
        frappe.log_error(
            f"Field timing reminders - Success: {success_count}, Errors: {error_count}, "
            f"Condition Skips: {condition_skip_count}",
            f"WhatsApp Field Timing Summary - {config.table_doctype}"
        )


def process_dedicated_time_reminders(config, current_datetime, current_time):
    """
    Process dedicated time reminders
    Send message at a specific time daily
    """
    if not config.custom_time:
        frappe.log_error(
            f"Dedicated time not specified for {config.table_doctype}",
            "WhatsApp Timing Config Error"
        )
        return
    
    # Parse the dedicated time
    dedicated_time = get_time(config.custom_time)
    
    # Check if current time is within 15-minute window of dedicated time
    current_minutes = current_time.hour * 60 + current_time.minute
    dedicated_minutes = dedicated_time.hour * 60 + dedicated_time.minute
    
    # Allow 15-minute window (scheduler runs every 15 minutes)
    if not (dedicated_minutes <= current_minutes < dedicated_minutes + 15):
        return
    
    # Get all active documents of this doctype
    filters = {}
    
    # Exclude cancelled documents for submittable doctypes
    submittable_doctypes = [
        "Purchase Order", "Sales Order", "Purchase Invoice", 
        "Sales Invoice", "Delivery Note", "Purchase Receipt"
    ]
    
    if config.table_doctype in submittable_doctypes:
        filters["docstatus"] = ["!=", 2]
    
    # Add date filters if specified (e.g., only send for documents created/modified today)
    if hasattr(config, 'dedicated_time_filter_field') and config.dedicated_time_filter_field:
        today = frappe.utils.nowdate()
        filters[config.dedicated_time_filter_field] = today
    
    docs = frappe.get_all(
        config.table_doctype,
        filters=filters,
        fields=["name", "docstatus"] if config.table_doctype in submittable_doctypes else ["name"]
    )
    
    if not docs:
        return
    
    whatsapp_handler = WhatsAppHandler()
    success_count = error_count = condition_skip_count = 0
    
    for d in docs:
        try:
            doc = frappe.get_doc(config.table_doctype, d.name)
            
            # Skip cancelled documents
            if hasattr(doc, 'docstatus') and doc.docstatus == 2:
                continue
            
            # Check if we already sent a reminder for this document today
            if has_timing_reminder_been_sent_today(doc.doctype, doc.name, "dedicated_time"):
                continue
            
            # Check custom condition
            if hasattr(config, 'custom_condition') and config.custom_condition:
                if not evaluate_custom_condition(doc, config.custom_condition):
                    condition_skip_count += 1
                    continue
            
            # Get phone number
            phone = get_phone_number_enhanced(doc, config.phone_field)
            if not phone:
                error_count += 1
                continue
            
            # Build message
            message = MessageTemplateHandler.build_message(
                doc, config,
                is_reminder=True,
                target_date=None,
                trigger_event="Daily Reminder"
            )
            
            # Add timing context to message
            message += f"\n\n🕐 Daily reminder at {dedicated_time.strftime('%I:%M %p')}"
            
            # Send message
            if whatsapp_handler.send_message(phone, message, doc.doctype, doc.name):
                success_count += 1
                # Log that reminder was sent
                log_timing_reminder_sent(doc.doctype, doc.name, "dedicated_time")
            else:
                error_count += 1
                
        except Exception as e:
            frappe.log_error(
                f"Dedicated time reminder failed for {d.name}: {str(e)}", 
                f"WhatsApp Dedicated Time Error - {config.table_doctype}"
            )
            error_count += 1
    
    # Log summary
    if success_count > 0 or error_count > 0 or condition_skip_count > 0:
        frappe.log_error(
            f"Dedicated time reminders ({dedicated_time.strftime('%I:%M %p')}) - "
            f"Success: {success_count}, Errors: {error_count}, Condition Skips: {condition_skip_count}",
            f"WhatsApp Dedicated Time Summary - {config.table_doctype}"
        )


def has_timing_reminder_been_sent_today(doctype, docname, reminder_type):
    """
    Check if a timing reminder has already been sent today for this document
    """
    try:
        today = frappe.utils.nowdate()
        
        # Check in Error Log (we use this to track sent reminders)
        existing_log = frappe.db.exists("Error Log", {
            "method": f"WhatsApp Timing Reminder Sent - {doctype}",
            "error": ["like", f"%{docname}%{reminder_type}%"],
            "creation": [">=", today + " 00:00:00"]
        })
        
        return bool(existing_log)
        
    except Exception as e:
        frappe.log_error(f"Error checking timing reminder log: {str(e)}", "WhatsApp Timing Check Error")
        return False


def log_timing_reminder_sent(doctype, docname, reminder_type):
    """
    Log that a timing reminder was sent (to prevent duplicate sends)
    """
    try:
        frappe.log_error(
            f"Timing reminder sent for {docname} (type: {reminder_type})",
            f"WhatsApp Timing Reminder Sent - {doctype}"
        )
    except Exception as e:
        pass  # Don't fail if logging fails


def get_timing_reminder_test_data():
    """
    Test function to check timing configurations
    """
    settings = safe_get_settings()
    if not settings:
        return {"error": "WhatsApp Settings not found"}
    
    timing_configs = [
        config for config in settings.whatsapp_doctypes
        if (config.enable_whatsapp and 
            getattr(config, 'custom_add_timing', False) and
            getattr(config, 'custom_timing', None))
    ]
    
    result = {
        "current_time": now_datetime().strftime('%Y-%m-%d %H:%M:%S'),
        "configs": []
    }
    
    for config in timing_configs:
        config_data = {
            "doctype": config.table_doctype,
            "timing_type": config.custom_timing,
            "phone_field": config.phone_field
        }
        
        if config.custom_timing == "Field":
            config_data["fieldname"] = getattr(config, 'custom_fieldname', '')
            config_data["time_before"] = getattr(config, 'custom_time_before_minutes', 60)
        elif config.custom_timing == "Dedicated":
            config_data["dedicated_time"] = str(getattr(config, 'custom_time', ''))
        
        result["configs"].append(config_data)
    
    return result




def safe_get_settings():
    """Safely get WhatsApp Settings to avoid import errors during installation"""
    if frappe.flags.in_install or frappe.flags.in_patch or frappe.flags.in_migrate:
        return None

    if not frappe.db.exists("DocType", "WhatsApp Settings"):
        return None

    try:
        return frappe.get_single("WhatsApp Settings")
    except ImportError as e:
        frappe.log_error(f"Could not load WhatsApp Settings: {e}", "WhatsApp Settings")
        return None


class WhatsAppHandler:
    """Centralized WhatsApp message handler - simplified without PDF support"""
    
    def __init__(self):
        self.settings = safe_get_settings()
        self.api_url = "https://api.botmastersender.com/api/v2/?action=send"
        
        if not self.settings:
            frappe.throw("WhatsApp Settings not configured or not available")

    def is_enabled(self):
        """Check if WhatsApp is enabled and configured"""
        return (self.settings.enabled and 
                self.settings.sender_id and 
                self.settings.auth_token)
    
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
        """Send text-only message"""
        try:
            data = {
                'senderId': self.settings.sender_id,
                'authToken': self.settings.auth_token,
                'messageText': message,
                'receiverId': f"91{receiver_id}"
            }
            
            response = requests.post(self.api_url, data=data, timeout=30)
            return self._handle_response(response, receiver_id, doctype, docname)
            
        except Exception as e:
            frappe.log_error(f"Message sending failed: {str(e)}", 
                           f"WhatsApp Error - {doctype} {docname}")
            return False
    
    def _handle_response(self, response, receiver_id, doctype, docname):
        """Handle API response"""
        if response.status_code != 200:
            frappe.log_error(f"API failed with status {response.status_code}: {response.text}", 
                           f"WhatsApp HTTP Error - {doctype}")
            return False
        
        try:
            response_data = response.json()
            if isinstance(response_data, list) and len(response_data) > 0:
                response_data = response_data[0]
            
            # Check for success indicators
            success_indicators = [
                response_data.get('status') == 'success' if isinstance(response_data, dict) else False,
                'success' in response.text.lower(),
                'sent' in response.text.lower(),
                response_data.get('result') == 'success' if isinstance(response_data, dict) else False
            ]
            
            if any(success_indicators):
                frappe.log_error(f"WhatsApp sent successfully to {receiver_id}", 
                               f"WhatsApp Success - {doctype}")
                return True
            else:
                frappe.log_error(f"API returned error: {response.text}", 
                               f"WhatsApp API Error - {doctype}")
                return False
                
        except ValueError:
            # Non-JSON response
            if 'success' in response.text.lower() or 'sent' in response.text.lower():
                frappe.log_error(f"WhatsApp sent successfully to {receiver_id}", 
                               f"WhatsApp Success - {doctype}")
                return True
            else:
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
    # Update the MessageTemplateHandler to handle timing reminders
    def build_timing_message(doc, doctype_setting, timing_type, field_datetime=None):
        """Build message for timing-based reminders"""
        try:
            # Use custom template if available
            if doctype_setting.custom_template:
                template_doc = frappe.get_doc("WhatsApp Message Template", 
                                            doctype_setting.custom_template)
                
                if template_doc and template_doc.is_active and template_doc.template_text:
                    return MessageTemplateHandler._process_template(
                        template_doc.template_text, doc, field_datetime
                    )
            
            # Use reminder message if available
            if doctype_setting.reminder_message:
                return MessageTemplateHandler._process_template(
                    doctype_setting.reminder_message, doc, field_datetime
                )
            
            # Build default timing message
            if timing_type == "field_based" and field_datetime:
                return f"⏰ Reminder: {doc.doctype} *{doc.name}*\n" \
                    f"Scheduled time: {field_datetime.strftime('%d-%m-%Y %I:%M %p')}\n" \
                    f"Please ensure you're prepared for the scheduled activity."
            elif timing_type == "dedicated_time":
                return f"📅 Daily Reminder: {doc.doctype} *{doc.name}*\n" \
                    f"This is your scheduled daily reminder.\n" \
                    f"Please review and take necessary action."
            else:
                return f"⏰ Timing Reminder: {doc.doctype} *{doc.name}*"
                
        except Exception as e:
            frappe.log_error(f"Error building timing message: {str(e)}", 
                            f"WhatsApp Timing Message Error - {doc.doctype}")
            return f"Reminder: {doc.doctype} {doc.name}"


    @staticmethod
    def build_message(doc, doctype_setting, is_reminder=False, target_date=None, trigger_event=None):
        """Build WhatsApp message using template or default format"""
        
        try:
            # Handle different trigger events
            if trigger_event == "Cancel":
                if doctype_setting.custom_template:
                    template_doc = frappe.get_doc("WhatsApp Message Template", 
                                                doctype_setting.custom_template)
                    
                    if template_doc and template_doc.is_active and template_doc.template_text:
                        return MessageTemplateHandler._process_template(
                            template_doc.template_text, doc, target_date
                        )
                
                return f"{doc.doctype} *{doc.name}* has been cancelled."
            
            # Handle scheduled reminders
            if trigger_event == "Scheduled Reminder" or is_reminder:
                if doctype_setting.reminder_message:
                    return MessageTemplateHandler._process_template(
                        doctype_setting.reminder_message, doc, target_date
                    )
                
                if doctype_setting.custom_template:
                    template_doc = frappe.get_doc("WhatsApp Message Template", 
                                                doctype_setting.custom_template)
                    
                    if template_doc and template_doc.is_active and template_doc.template_text:
                        return MessageTemplateHandler._process_template(
                            template_doc.template_text, doc, target_date
                        )
                
                return MessageTemplateHandler._build_default_message(
                    doc, is_reminder=True, target_date=target_date
                )
            
            # Handle other events (Submit/Save/Creation/Update)
            if doctype_setting.custom_template:
                template_doc = frappe.get_doc("WhatsApp Message Template", 
                                            doctype_setting.custom_template)
                
                if template_doc and template_doc.is_active and template_doc.template_text:
                    return MessageTemplateHandler._process_template(
                        template_doc.template_text, doc, target_date
                    )
            
            return MessageTemplateHandler._build_default_message(
                doc, is_reminder=False, target_date=target_date, trigger_event=trigger_event
            )
            
        except Exception as e:
            frappe.log_error(f"Error building message: {str(e)}", 
                           f"WhatsApp Template Error - {doc.doctype}")
            return MessageTemplateHandler._build_fallback_message(
                doc, is_reminder, target_date, trigger_event
            )
    # Add this function to your MessageTemplateHandler class

    @staticmethod
    def format_whatsapp_message(message):
        """Format message for WhatsApp with proper line breaks"""
        if not message:
            return message
        
        # Replace various line break formats with \n
        replacements = [
            ('%0A\\n', '\n'),      # %0A\n combination
            ('%0A', '\n'),         # URL encoded line break
            ('\\n', '\n'),         # Escaped newline
            ('/n', '\n'),          # Common typo
            ('&lt;br&gt;', '\n'),  # HTML br tags (encoded)
            ('<br>', '\n'),        # HTML br tags
            ('<br/>', '\n'),       # HTML br tags (self-closing)
            ('<BR>', '\n'),        # HTML BR tags (uppercase)
            ('&nbsp;', ' '),       # Non-breaking space
        ]
        
        for old, new in replacements:
            message = message.replace(old, new)
        
        # Clean up multiple consecutive line breaks (more than 2)
        import re
        message = re.sub(r'\n{3,}', '\n\n', message)
        
        # Remove trailing whitespace from each line
        lines = message.split('\n')
        lines = [line.rstrip() for line in lines]
        message = '\n'.join(lines)
        
        return message.strip()


    @staticmethod
    def _process_template(template_text, doc, target_date=None):
        """Process template with placeholder replacement and proper formatting"""
        template_text = MessageTemplateHandler.clean_html(template_text)
        
        # Build and replace placeholders
        placeholders = MessageTemplateHandler._build_placeholders(doc, target_date)
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
        
        # Format the message for WhatsApp (ADD THIS LINE)
        message = MessageTemplateHandler.format_whatsapp_message(message)
        
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
                    # Clean HTML for text fields
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
    def _build_default_message(doc, is_reminder=False, target_date=None, trigger_event=None):
        """Build default message format"""
        if is_reminder or trigger_event == "Scheduled Reminder":
            if target_date:
                message = f"Reminder: Your document {doc.name} is due on {target_date}."
            else:
                message = f"Reminder: Your document {doc.name} requires attention."
        else:
            # Messages based on trigger event
            event_messages = {
                "Submit": f"{doc.doctype} *{doc.name}* has been submitted.",
                "Save": f"{doc.doctype} *{doc.name}* has been saved.",
                "Cancel": f"{doc.doctype} *{doc.name}* has been cancelled.",
                "On Creation": f"New {doc.doctype} *{doc.name}* has been created.",
                "On Update": f"{doc.doctype} *{doc.name}* has been updated."
            }
            
            message = event_messages.get(trigger_event, 
                                       f"{doc.doctype} *{doc.name}* has been processed.")
        
        # Add amount if available
        amount = getattr(doc, "grand_total", None) or getattr(doc, "total", None)
        if amount:
            message += f"\nTotal Amount: ₹{amount}"
    
        # ADD THIS LINE: Format the message for WhatsApp
        message = MessageTemplateHandler.format_whatsapp_message(message)    
        return message
    
    # Fix 4: Update _build_fallback_message function
    @staticmethod
    def _build_fallback_message(doc, is_reminder=False, target_date=None, trigger_event=None):
        """Build basic fallback message"""
        if is_reminder or trigger_event == "Scheduled Reminder":
            if target_date:
                message = f"Reminder: Document {doc.name} due on {target_date}."
            else:
                message = f"Reminder: Document {doc.name} requires attention."
        
        event_messages = {
            "Cancel": f"{doc.doctype} {doc.name} has been cancelled.",
            "Submit": f"{doc.doctype} {doc.name} has been submitted.",
            "Save": f"{doc.doctype} {doc.name} has been saved.",
            "On Creation": f"New {doc.doctype} {doc.name} has been created.",
            "On Update": f"{doc.doctype} {doc.name} has been updated."
        }
        
        message = event_messages.get(trigger_event, f"{doc.doctype} {doc.name} has been processed.")
        
        # ADD THIS LINE: Format the message for WhatsApp
        message = MessageTemplateHandler.format_whatsapp_message(message)
        
        return message


# Phone number utilities
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
        # Find all ToDo entries for this document
        todo_filters = {
            "reference_type": doc.doctype,
            "reference_name": doc.name,
            "status": "Open"
        }
        
        todos = frappe.get_all("ToDo", filters=todo_filters, fields=["allocated_to"])
        
        if not todos:
            # Try without status filter
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

# Add this new function for evaluating custom conditions
def evaluate_custom_condition(doc, condition_code):
    """
    Evaluate custom condition code for WhatsApp notifications
    Similar to Frappe's notification system - FIXED VERSION
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
        
        # FIXED: Add all document fields to context for easy access
        # Method 1: Using get_valid_columns (field names as strings)
        try:
            valid_columns = doc.meta.get_valid_columns()
            for fieldname in valid_columns:
                if hasattr(doc, fieldname):
                    context[fieldname] = doc.get(fieldname)
        except:
            pass
        
        # Method 2: Using meta.fields (field objects) as backup
        try:
            for field in doc.meta.fields:
                if hasattr(doc, field.fieldname):
                    context[field.fieldname] = doc.get(field.fieldname)
        except:
            pass
        
        # Method 3: Direct iteration through document as final backup
        try:
            for key in doc.as_dict():
                context[key] = doc.get(key)
        except:
            pass
        
        # Evaluate the condition
        result = frappe.safe_eval(condition_code, context)
        
        # Log condition evaluation for debugging (optional - remove in production)
        frappe.log_error(
            f"Condition evaluated - Document: {doc.name}, Result: {result}, Condition: {condition_code[:100]}...",
            f"WhatsApp Condition Debug - {doc.doctype}"
        )
        
        return bool(result)
        
    except Exception as e:
        # Log the error and default to not sending to prevent spam
        frappe.log_error(
            f"Error evaluating condition: {str(e)}\nCondition: {condition_code}\nDocument: {doc.name}",
            f"WhatsApp Condition Error - {doc.doctype}"
        )
        return False


# Modify the process_scheduled_whatsapp_reminder function
def process_scheduled_whatsapp_reminder(config):
    """Process scheduled reminders for a specific doctype configuration - MODIFIED to include condition check"""
    date_field = config.date_field
    
    # Calculate target date based on trigger timing
    if config.trigger_timing == "Days Before":
        target_date = add_days(nowdate(), config.days_before or 0)
    elif config.trigger_timing == "Days After":
        target_date = add_days(nowdate(), -(config.days_after or 0))
    else:
        target_date = nowdate()
    
    filters = {f"{date_field}": target_date}
    
    # Exclude cancelled documents for submittable doctypes
    submittable_doctypes = [
        "Purchase Order", "Sales Order", "Purchase Invoice", 
        "Sales Invoice", "Delivery Note", "Purchase Receipt"
    ]
    
    if config.table_doctype in submittable_doctypes:
        filters["docstatus"] = ["!=", 2]
    
    docs = frappe.get_all(
        config.table_doctype, 
        filters=filters, 
        fields=["name", "docstatus"] if config.table_doctype in submittable_doctypes else ["name"]
    )

    whatsapp_handler = WhatsAppHandler()
    success_count = error_count = condition_skip_count = 0

    for d in docs:
        try:
            # Skip cancelled documents
            if hasattr(d, 'docstatus') and d.docstatus == 2:
                continue
                
            doc = frappe.get_doc(config.table_doctype, d.name)
            
            if hasattr(doc, 'docstatus') and doc.docstatus == 2:
                continue
            
            # ADDED: Check custom condition for scheduled reminders
            if hasattr(config, 'custom_condition') and config.custom_condition:
                if not evaluate_custom_condition(doc, config.custom_condition):
                    condition_skip_count += 1
                    continue
            
            phone = get_phone_number_enhanced(doc, config.phone_field)
            if not phone:
                error_count += 1
                continue

            message = MessageTemplateHandler.build_message(
                doc, config, 
                is_reminder=True, 
                target_date=target_date,
                trigger_event="Scheduled Reminder"
            )
            
            if whatsapp_handler.send_message(phone, message, doc.doctype, doc.name):
                success_count += 1
            else:
                error_count += 1
                
        except Exception as e:
            frappe.log_error(f"Failed to process reminder for {d.name}: {str(e)}", 
                           f"WhatsApp Reminder Error")
            error_count += 1

    # Log summary - MODIFIED to include condition skips
    if success_count > 0 or error_count > 0 or condition_skip_count > 0:
        frappe.log_error(
            f"Reminders processed - Success: {success_count}, Errors: {error_count}, Condition Skips: {condition_skip_count}", 
            f"WhatsApp Reminder Summary - {config.table_doctype}"
        )

# Document event handlers
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


# Modify the _handle_whatsapp_notification function
def _handle_whatsapp_notification(doc, method, trigger_event):
    """Unified WhatsApp notification handler - MODIFIED to include condition check"""
    try:
        settings = safe_get_settings()
        if not settings or not settings.enabled:
            return

        # Find matching configurations
        matching_configs = [
            d for d in settings.whatsapp_doctypes 
            if (d.enable_whatsapp and 
                d.table_doctype.strip() == doc.doctype and
                d.trigger_event == trigger_event and
                d.trigger_timing == "Immediate")
        ]
        
        if not matching_configs:
            return

        whatsapp_handler = WhatsAppHandler()
        
        for doctype_setting in matching_configs:
            try:
                # ADDED: Check custom condition before processing
                if hasattr(doctype_setting, 'custom_condition') and doctype_setting.custom_condition:
                    if not evaluate_custom_condition(doc, doctype_setting.custom_condition):
                        frappe.log_error(
                            f"Custom condition not met for {doc.name}",
                            f"WhatsApp Condition Skip - {doc.doctype}"
                        )
                        continue
                
                _process_whatsapp_config(doc, doctype_setting, whatsapp_handler)
            except Exception as e:
                frappe.log_error(
                    f"Config processing failed for {doctype_setting.table_doctype}: {str(e)}", 
                    f"WhatsApp Config Error - {doc.doctype}"
                )

    except Exception as e:
        frappe.log_error(f"WhatsApp notification failed: {str(e)}", 
                        f"DocType: {doc.doctype}, Name: {doc.name}")



def _process_whatsapp_config(doc, doctype_setting, whatsapp_handler):
    """Process individual WhatsApp configuration"""
    if not doctype_setting.phone_field:
        frappe.log_error("No phone field configured", f"{doc.doctype} - {doc.name}")
        return
    
    # Handle assigned_to field (multiple assignments)
    if doctype_setting.phone_field.strip() == "assigned_to":
        assigned_phones = get_assigned_user_phone_numbers(doc)
        
        if not assigned_phones:
            frappe.log_error("No assigned users with phone numbers found", 
                           f"{doc.doctype} - {doc.name}")
            return
        
        message = MessageTemplateHandler.build_message(
            doc, doctype_setting, trigger_event=doctype_setting.trigger_event
        )
        
        success_count = error_count = 0
        
        for assigned_user in assigned_phones:
            try:
                if whatsapp_handler.send_message(
                    assigned_user['phone'], message, doc.doctype, doc.name
                ):
                    success_count += 1
                else:
                    error_count += 1
            except Exception as send_error:
                error_count += 1
                frappe.log_error(
                    f"Error sending to {assigned_user['user']}: {str(send_error)}", 
                    f"Assignment Send Error - {doc.doctype}"
                )
        
        frappe.log_error(
            f"Assignment notifications: {success_count} sent, {error_count} failed", 
            f"Assignment Summary - {doc.doctype}"
        )
        return
    
    # Handle single phone number
    phone = get_phone_number_enhanced(doc, doctype_setting.phone_field)
    if not phone:
        frappe.log_error("No mobile number found", f"{doc.doctype} - {doc.name}")
        return

    message = MessageTemplateHandler.build_message(
        doc, doctype_setting, trigger_event=doctype_setting.trigger_event
    )
    
    whatsapp_handler.send_message(phone, message, doc.doctype, doc.name)


# Child table reminder utilities (simplified without PDF)
def process_scheduled_whatsapp_reminder_enhanced(config):
    """Enhanced scheduler that handles both document and child table reminders"""
    date_field = config.date_field
    
    if '.' in date_field:
        return process_child_table_reminders_auto(config)
    else:
        return process_scheduled_whatsapp_reminder(config)


# Modify the process_child_table_reminders_auto function
def process_child_table_reminders_auto(config):
    """Process child table reminders based on date_field notation - MODIFIED to include condition check"""
    date_field = config.date_field
    
    if '.' not in date_field:
        frappe.log_error("Invalid child table field format. Use 'table_field.date_field'", 
                        f"Child Table Config Error - {config.table_doctype}")
        return
    
    child_table_field, child_date_field = date_field.split('.', 1)
    
    # Validate fields
    parent_meta = frappe.get_meta(config.table_doctype)
    table_field_meta = parent_meta.get_field(child_table_field)
    
    if not table_field_meta or table_field_meta.fieldtype != "Table":
        frappe.log_error(f"Invalid child table field '{child_table_field}'", 
                        f"Child Table Field Error - {config.table_doctype}")
        return
    
    child_doctype = table_field_meta.options
    child_meta = frappe.get_meta(child_doctype)
    if not child_meta.get_field(child_date_field):
        frappe.log_error(f"Date field '{child_date_field}' not found in {child_doctype}", 
                        f"Child Date Field Error - {config.table_doctype}")
        return
    
    # Calculate target date
    if config.trigger_timing == "Days Before":
        target_date = add_days(nowdate(), config.days_before or 0)
    elif config.trigger_timing == "Days After":
        target_date = add_days(nowdate(), -(config.days_after or 0))
    else:
        target_date = nowdate()
    
    # Get parent documents with matching child records
    parent_docs = get_parents_with_matching_child_dates(
        config.table_doctype, 
        child_table_field, 
        child_doctype,
        child_date_field, 
        target_date
    )
    
    whatsapp_handler = WhatsAppHandler()
    success_count = error_count = condition_skip_count = 0
    
    for parent_info in parent_docs:
        try:
            parent_doc = frappe.get_doc(config.table_doctype, parent_info['name'])
            
            # Skip cancelled documents
            if hasattr(parent_doc, 'docstatus') and parent_doc.docstatus == 2:
                continue
            
            # ADDED: Check custom condition for child table reminders
            if hasattr(config, 'custom_condition') and config.custom_condition:
                if not evaluate_custom_condition(parent_doc, config.custom_condition):
                    condition_skip_count += 1
                    continue
            
            phone = get_phone_number_enhanced(parent_doc, config.phone_field)
            if not phone:
                frappe.log_error(f"No phone found for {parent_doc.name}", 
                               f"Child Reminder Phone - {config.table_doctype}")
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
            
            # Send individual messages for each child record
            for child_row in matching_children:
                message = build_child_message_auto(
                    parent_doc, child_row, config, target_date, 
                    child_table_field, child_date_field
                )
                
                if whatsapp_handler.send_message(phone, message, parent_doc.doctype, parent_doc.name):
                    success_count += 1
                else:
                    error_count += 1
                        
        except Exception as e:
            frappe.log_error(
                f"Child table reminder failed for {parent_info['name']}: {str(e)}", 
                f"Child Reminder Error - {config.table_doctype}"
            )
            error_count += 1
    
    # Log summary - MODIFIED to include condition skips
    frappe.log_error(
        f"Child table reminders ({child_table_field}.{child_date_field}) - "
        f"Success: {success_count}, Errors: {error_count}, Condition Skips: {condition_skip_count}", 
        f"Child Reminder Summary - {config.table_doctype}"
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


def build_child_message_auto(parent_doc, child_row, config, target_date, 
                           child_table_field, child_date_field):
    """Build message for individual child record"""
    
    # Try custom template first
    if hasattr(config, 'custom_template') and config.custom_template:
        try:
            template_doc = frappe.get_doc("WhatsApp Message Template", config.custom_template)
            if template_doc and template_doc.is_active and template_doc.template_text:
                return process_child_template_auto(
                    template_doc.template_text, parent_doc, child_row, target_date
                )
        except Exception as e:
            frappe.log_error(f"Template processing failed: {str(e)}", 
                           f"Child Template Error - {config.table_doctype}")
    
    # Try reminder message field
    if hasattr(config, 'reminder_message') and config.reminder_message:
        return process_child_template_auto(
            config.reminder_message, parent_doc, child_row, target_date
        )
    
    # Build default message
    return build_default_child_message(parent_doc, child_row, target_date, child_table_field)


def process_child_template_auto(template_text, parent_doc, child_row, target_date):
    """Process template with automatic placeholder detection"""
    
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
    
    # ADD THIS LINE: Format the message for WhatsApp
    message = MessageTemplateHandler.format_whatsapp_message(message)
    
    return message




# Fix 3: Update build_default_child_message function
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
    
    # ADD THIS LINE: Format the message for WhatsApp
    message = MessageTemplateHandler.format_whatsapp_message(message)
    
    return message.strip()



# Main scheduler function
def send_scheduled_whatsapp_reminders_enhanced():
    """Enhanced scheduler that handles both document and child table reminders"""
    settings = safe_get_settings()
    if not settings or not settings.enabled:
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
            process_scheduled_whatsapp_reminder_enhanced(doctype_config)
        except Exception as e:
            frappe.log_error(
                f"Enhanced scheduler failed for {doctype_config.table_doctype}: {str(e)}", 
                f"WhatsApp Scheduler Error"
            )


# Utility and test functions
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


def send_whatsapp_without_pdf(receiver_id, message, doctype, docname):
    """Emergency fallback - send without PDF (now same as regular send)"""
    whatsapp_handler = WhatsAppHandler()
    
    if not whatsapp_handler.is_enabled():
        return False
    
    # Add document reference to message
    text_message = message + f"\n\nDocument: {docname}"
    
    return whatsapp_handler.send_message(receiver_id, text_message, doctype, docname)


# Backward compatibility wrapper (simplified)
def send_whatsapp_message_with_attachment(receiver_id, message, doctype, docname, 
                                        print_format=None, fallback_to_text=False):
    """Backward compatibility wrapper - now sends text-only messages"""
    whatsapp_handler = WhatsAppHandler()
    return whatsapp_handler.send_message(receiver_id, message, doctype, docname)