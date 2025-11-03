<p>A new Purchase Invoice ({{ doc.name }}) requires your approval.</p>

<p><strong>Supplier:</strong> {{ doc.supplier }}<br />
<strong>Total Amount:</strong> {{ doc.grand_total }}</p>

<p>📌 Click below to review:<br />
<a href="{{ frappe.utils.get_url_to_form('Purchase Invoice', doc.name) }}">View Purchase Invoice</a></p>
