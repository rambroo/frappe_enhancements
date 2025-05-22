import frappe
from frappe import _
from frappe.utils import now

@frappe.whitelist(allow_guest=False)
def save_device_token(device_token, device_type="web", device_name=None):
    user = frappe.session.user

    if not device_token:
        frappe.throw(_("Device token is required."))

    # Check if same token already exists for same user
    existing = frappe.get_all(
        "User Device",
        filters={
            "user": user,
            "device_token": device_token,
            "device_type": device_type
        },
        limit=1
    )

    if existing:
        return {"message": "Token already registered."}

    doc = frappe.new_doc("User Device")
    doc.user = user
    doc.device_token = device_token
    doc.device_type = device_type
    doc.device_name = device_name or frappe.local.request.headers.get("User-Agent")
    doc.is_active = 1
    doc.insert(ignore_permissions=True)

    return {"message": "Device token saved successfully."}


# fetch('/api/method/erpnext_enhancements.api.device_token.save_device_token', {
#   method: 'POST',
#   headers: {
#     'Content-Type': 'application/json',
#     'X-Frappe-CSRF-Token': frappe.csrf_token // Required for POST in Frappe
#   },
#   body: JSON.stringify({
#     device_token: 'test-token-abc-123',
#     device_type: 'web',
#     device_name: 'Chrome Local Test'
#   })
# })
# .then(res => res.json())
# .then(console.log)
# .catch(console.error);
