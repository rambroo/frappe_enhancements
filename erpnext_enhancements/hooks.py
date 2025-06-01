app_name = "erpnext_enhancements"
app_title = "erpnext_enhancements"
app_publisher = "Rohan"
app_description = "Used for common features in Clients"
app_email = "rohan@micronxt.com"
app_license = "mit"

# Apps
# ------------------
doctype_js = {
    "Purchase Order": "public/js/purchase_order_review.js"
}

jenv = {
    "jinja": ["erpnext_enhancements.templates.includes.po_review_modal_template"]
}

doc_events = {
    "*": {
        "on_submit": "erpnext_enhancements.api.whatsapp_reminders.whatsapp.handle_whatsapp_notification",
        "before_save": "erpnext_enhancements.api.whatsapp_reminders.whatsapp.handle_whatsapp_notification"
    }
}

scheduler_events = {
    "daily": [
        "erpnext_enhancements.api.whatsapp_reminders.whatsapp.send_scheduled_whatsapp_reminders"
    ]
}

        #Recurrsion Error will look into it

        # ,
        # "after_insert": "erpnext_enhancements.api.whatsapp_reminders.whatsapp.handle_whatsapp_notification",
        # "on_update": "erpnext_enhancements.api.whatsapp_reminders.whatsapp.handle_whatsapp_notification",
        # "after_save": "erpnext_enhancements.api.whatsapp_reminders.whatsapp.handle_whatsapp_notification",



# # Scheduler Events
# scheduler_events = {
#     "daily": [
#         "erpnext_enhancements.api.whatsapp_reminders.whatsapp.send_po_due_reminders"
#     ]
# }





# # Document Events
# doc_events = {
#     # Your existing setup
#     "Purchase Order": {
#         "on_submit": "erpnext_enhancements.api.whatsapp_reminders.whatsapp.send_po_notification"
#     },
#     # Add WhatsApp notifications to all doctypes
#     "*": {
#         "after_insert": "erpnext_enhancements.utils.notification_extension.send_whatsapp_after_notification",
#         "on_update": "erpnext_enhancements.utils.notification_extension.send_whatsapp_after_notification",
#         "on_submit": "erpnext_enhancements.utils.notification_extension.send_whatsapp_after_notification",
#         "on_cancel": "erpnext_enhancements.utils.notification_extension.send_whatsapp_after_notification"
#     }
# }

# # Scheduler Events
# scheduler_events = {
#     "daily": [
#         "erpnext_enhancements.api.whatsapp_reminders.whatsapp.send_po_due_reminders"
#     ]
# }


# // FIREBASE RELATED CHANEGES START

# web_include_js = [
#     "https://www.gstatic.com/firebasejs/8.10.0/firebase-app.js",
#     "https://www.gstatic.com/firebasejs/8.10.0/firebase-messaging.js",
#     "/assets/erpnext_enhancements/js/fcm-init.js"
# ]

# # Include JS in desk pages (for admin notifications)
# app_include_js = [
#     "https://www.gstatic.com/firebasejs/8.10.0/firebase-app.js",          
#     "https://www.gstatic.com/firebasejs/8.10.0/firebase-messaging.js",
#     "/assets/erpnext_enhancements/js/fcm-init.js"
# ]

# # In hooks.py
# website_route_rules = [
#     {"from_route": "/firebase-messaging-sw.js", "to_route": "erpnext_enhancements/www/firebase-messaging-sw.js"}
# ]

# # Document Events
# # ---------------
# # Hook on document methods and events
# doc_events = {
#     "Purchase Order": {
#         "on_update": "erpnext_enhancements.notifications.handle_status_change"
#     }
#     # Replace "Your DocType" with the actual DocType name you want to monitor
#     # For example: "Task", "Issue", etc.
# }


# // FIREBASE RELATED CHANEGES END


# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "erpnext_enhancements",
# 		"logo": "/assets/erpnext_enhancements/logo.png",
# 		"title": "erpnext_enhancements",
# 		"route": "/erpnext_enhancements",
# 		"has_permission": "erpnext_enhancements.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/erpnext_enhancements/css/erpnext_enhancements.css"
# app_include_js = "/assets/erpnext_enhancements/js/erpnext_enhancements.js"

# include js, css files in header of web template
# web_include_css = "/assets/erpnext_enhancements/css/erpnext_enhancements.css"
# web_include_js = "/assets/erpnext_enhancements/js/erpnext_enhancements.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "erpnext_enhancements/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "erpnext_enhancements/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "erpnext_enhancements.utils.jinja_methods",
# 	"filters": "erpnext_enhancements.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "erpnext_enhancements.install.before_install"
# after_install = "erpnext_enhancements.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "erpnext_enhancements.uninstall.before_uninstall"
# after_uninstall = "erpnext_enhancements.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "erpnext_enhancements.utils.before_app_install"
# after_app_install = "erpnext_enhancements.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "erpnext_enhancements.utils.before_app_uninstall"
# after_app_uninstall = "erpnext_enhancements.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "erpnext_enhancements.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"erpnext_enhancements.tasks.all"
# 	],
# 	"daily": [
# 		"erpnext_enhancements.tasks.daily"
# 	],
# 	"hourly": [
# 		"erpnext_enhancements.tasks.hourly"
# 	],
# 	"weekly": [
# 		"erpnext_enhancements.tasks.weekly"
# 	],
# 	"monthly": [
# 		"erpnext_enhancements.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "erpnext_enhancements.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "erpnext_enhancements.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "erpnext_enhancements.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["erpnext_enhancements.utils.before_request"]
# after_request = ["erpnext_enhancements.utils.after_request"]

# Job Events
# ----------
# before_job = ["erpnext_enhancements.utils.before_job"]
# after_job = ["erpnext_enhancements.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"erpnext_enhancements.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

