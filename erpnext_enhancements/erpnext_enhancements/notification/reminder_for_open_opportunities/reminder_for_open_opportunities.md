<p>Hello {{ doc.owner }},</p>

<p>This is a reminder to follow up on the open opportunity: <strong>{{ doc.name }}</strong>.</p>

<p>Customer: {{ doc.party_name }}<br>
Expected Closing Date: {{ doc.expected_closing }}</p>

<p>Please update the status or follow up with the client.</p>

<p>Regards,<br>
Your Sales Team<br>
<a href="{{ frappe.utils.get_url_to_form('Opportunity', doc.name) }}">View Opportunity</a></p>
