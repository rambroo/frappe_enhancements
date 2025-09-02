import frappe
from erpnext.selling.doctype.customer.customer import get_credit_limit

@frappe.whitelist()
def get_credit_balance(customer, company):
    """Return available credit balance for a customer 
       (Credit Limit - Net Unpaid - Pending SOs)"""

    # Net unpaid = debits - credits from GL (already invoiced & posted)
    outstanding_amt = frappe.db.sql(
        """
        SELECT SUM(debit_in_account_currency) - SUM(credit_in_account_currency)
        FROM `tabGL Entry`
        WHERE party_type = 'Customer'
          AND party = %s
          AND company = %s
          AND is_cancelled = 0
        """,
        (customer, company),
    )[0][0] or 0

    # Pending Sales Orders = approved/final submission SOs, not yet fully invoiced
    pending_so = frappe.db.sql(
        """
        SELECT SUM(base_grand_total * (1 - (per_billed / 100)))
        FROM `tabSales Order`
        WHERE customer = %s
          AND company = %s
          AND docstatus = 1
          AND workflow_state IN ("Approved", "Final Submission","Submitted")
        """,
        (customer, company),
    )[0][0] or 0

    # Credit limit defined for this customer
    credit_limit = get_credit_limit(customer, company) or 0

    # Remaining balance (credit - invoices - pending SOs)
    bal = credit_limit - (outstanding_amt + pending_so)

    return {
        "credit_limit": credit_limit,
        "outstanding_amt": outstanding_amt,
        "pending_so": pending_so,
        "balance": bal,
    }