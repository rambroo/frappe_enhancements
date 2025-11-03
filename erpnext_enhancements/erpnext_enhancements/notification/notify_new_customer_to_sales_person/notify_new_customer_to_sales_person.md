<p>Dear {{ frappe.db.get_value("Sales Person", doc.sales_team[0].sales_person, "employee_name") or "Sales Person" }},</p>

<p>A new customer <strong>{{ doc.customer_name }}</strong> has been assigned to you.</p>

<p>Please check your dashboard for more details.</p>

<p>Regards,<br />
ERP System</p>

<p>{% for row in doc.sales<em>team %}
    <p>Email: {{ frappe.db.get_value("Sales Person", row.sales_person, "email") or "No email available" }}</p>

<p>{% endfor %}</p></p>
