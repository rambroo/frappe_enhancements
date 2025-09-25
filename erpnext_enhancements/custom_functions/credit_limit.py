import frappe
from erpnext.selling.doctype.customer.customer import get_credit_limit, get_customer_outstanding

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


@frappe.whitelist()
def get_credit_balance_2(customer, company):
    # Step 1: Get total outstanding (includes SOs since ignore_outstanding_sales_order=False)
    total_outstanding = get_customer_outstanding(
        customer, company, ignore_outstanding_sales_order=False
    ) or 0

    # Step 2: Get outstanding Sales Orders
    sales_orders = frappe.get_all(
        "Sales Order",
        filters={
            "customer": customer,
            "company": company,
            "docstatus": 1,
            "status": ["not in", ["Closed", "Cancelled"]],
        },
        fields=["name", "grand_total", "advance_paid"]
    )

    # Step 3: Find linked payment entries for those SOs
    linked_so_total = 0
    for so in sales_orders:
        allocated_pe = frappe.db.sql("""
            SELECT sum(allocated_amount)
            FROM `tabPayment Entry Reference`
            WHERE reference_doctype = 'Sales Order'
            AND reference_name = %s
        """, so.name)[0][0] or 0

        if allocated_pe > 0:
            linked_so_total += min(allocated_pe, so.grand_total)

    # Step 4: Adjusted outstanding
    adjusted_outstanding = total_outstanding - linked_so_total

    # Step 5: Credit limit
    credit_limit = get_credit_limit(customer, company) or 0

    # Step 6: Final balance
    final_balance = credit_limit - adjusted_outstanding

    return {
        "credit_limit": credit_limit,
        "total_outstanding": total_outstanding,
        "linked_payment_against_so": linked_so_total,
        "adjusted_outstanding": adjusted_outstanding,
        "available_balance": final_balance
    }



@frappe.whitelist()
def get_credit_balance_3(customer, company):
    outstanding_amt = get_customer_outstanding(
        customer, company, ignore_outstanding_sales_order=False
    )
    credit_limit = get_credit_limit(customer, company) or 0
    balance = credit_limit - outstanding_amt

    invoices = frappe.db.sql("""
        SELECT name, outstanding_amount
        FROM `tabSales Invoice`
        WHERE customer=%s AND company=%s AND docstatus=1 AND outstanding_amount > 0
    """, (customer, company), as_dict=True)

    sales_orders = frappe.db.sql("""
        SELECT name, (rounded_total - advance_paid) AS pending_amount
        FROM `tabSales Order`
        WHERE customer=%s AND company=%s AND docstatus=1
          AND status NOT IN ('Closed', 'Cancelled')
    """, (customer, company), as_dict=True)

    payments = frappe.db.sql("""
        SELECT name, paid_amount, unallocated_amount
        FROM `tabPayment Entry`
        WHERE party_type='Customer' AND party=%s AND company=%s AND docstatus=1
    """, (customer, company), as_dict=True)
    
    frappe.log_error(frappe.as_json({
        "credit_limit": credit_limit,
        "outstanding": outstanding_amt,
        "balance": balance,
        "invoices": invoices,
        "sales_orders": sales_orders,
        "payments": payments,
    }), "DEBUG Credit Balance")


    return {
        "credit_limit": credit_limit,
        "outstanding": outstanding_amt,
        "balance": balance,
        "invoices": invoices,
        "sales_orders": sales_orders,
        "payments": payments,
    }
