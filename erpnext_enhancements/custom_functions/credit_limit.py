import frappe
from frappe.utils import flt
from erpnext.selling.doctype.customer.customer import get_credit_limit, get_customer_outstanding

@frappe.whitelist()
def get_credit_balance_3_enhanced(customer, company):
    """
    Enhanced credit balance calculation with detailed breakdown
    matching ERPNext's internal logic
    """
    
    # Get basic credit info
    credit_limit = get_credit_limit(customer, company) or 0
    total_outstanding = get_customer_outstanding(
        customer, company, ignore_outstanding_sales_order=False
    )
    balance = credit_limit - total_outstanding
    
    # 1. Outstanding based on GL Entries (Net position after all allocations)
    # For credit limit: This already includes the effect of allocated payments
    gl_outstanding = frappe.db.sql("""
        SELECT 
            'GL Entry' as source_type,
            'Net Receivable Position' as description,
            SUM(debit) - SUM(credit) as amount
        FROM `tabGL Entry` 
        WHERE party_type = 'Customer'
            AND is_cancelled = 0 
            AND party = %s
            AND company = %s
    """, (customer, company), as_dict=True)
    
    # GL amount represents net receivable position (can be negative if customer has credit)
    gl_amount = flt(gl_outstanding[0].amount) if gl_outstanding and gl_outstanding[0].amount else 0
    
    # Separate query for actual invoice outstanding (before payment allocation)
    invoice_outstanding = frappe.db.sql("""
        SELECT SUM(outstanding_amount) as total_outstanding
        FROM `tabSales Invoice`
        WHERE customer = %s 
            AND company = %s 
            AND docstatus = 1 
            AND outstanding_amount > 0
    """, (customer, company), as_dict=True)
    
    invoice_outstanding_amount = flt(invoice_outstanding[0].total_outstanding) if invoice_outstanding and invoice_outstanding[0].total_outstanding else 0
    
    # 2. Detailed Sales Invoices with outstanding amounts
    invoices = frappe.db.sql("""
        SELECT 
            name,
            posting_date,
            base_grand_total,
            outstanding_amount,
            status
        FROM `tabSales Invoice`
        WHERE customer = %s 
            AND company = %s 
            AND docstatus = 1 
            AND outstanding_amount > 0
        ORDER BY posting_date DESC
    """, (customer, company), as_dict=True)
    
    # 3. Sales Orders - Unbilled portions (matching ERPNext logic)
    sales_orders = frappe.db.sql("""
        SELECT 
            name,
            transaction_date,
            base_grand_total,
            per_billed,
            advance_paid,
            ROUND(base_grand_total * (100 - per_billed) / 100, 2) as unbilled_amount,
            ROUND((base_grand_total * (100 - per_billed) / 100) - advance_paid, 2) as net_pending_amount,
            ROUND(base_grand_total - advance_paid, 2) as total_pending_amount,
            status
        FROM `tabSales Order`
        WHERE customer = %s 
            AND company = %s 
            AND docstatus = 1
            AND per_billed < 100 
            AND status NOT IN ('Closed', 'Cancelled')
        ORDER BY transaction_date DESC
    """, (customer, company), as_dict=True)
    
    so_outstanding = sum(flt(so.unbilled_amount) for so in sales_orders)
    
    # 4. Delivery Notes not against Sales Orders (unbilled deliveries)
    delivery_notes_detail = frappe.db.sql("""
        SELECT 
            dn.name,
            dn.posting_date,
            dn.base_grand_total,
            dn.base_net_total,
            dn_item.name as dn_item_name,
            dn_item.amount as dn_item_amount,
            COALESCE(si_summary.invoiced_amount, 0) as invoiced_amount,
            (dn_item.amount - COALESCE(si_summary.invoiced_amount, 0)) as uninvoiced_amount
        FROM `tabDelivery Note` dn
        JOIN `tabDelivery Note Item` dn_item ON dn.name = dn_item.parent
        LEFT JOIN (
            SELECT 
                dn_detail,
                SUM(amount) as invoiced_amount
            FROM `tabSales Invoice Item`
            WHERE docstatus = 1
            GROUP BY dn_detail
        ) si_summary ON dn_item.name = si_summary.dn_detail
        WHERE dn.customer = %s 
            AND dn.company = %s
            AND dn.docstatus = 1 
            AND dn.status NOT IN ('Closed', 'Stopped')
            AND IFNULL(dn_item.against_sales_order, '') = ''
            AND IFNULL(dn_item.against_sales_invoice, '') = ''
            AND (dn_item.amount - COALESCE(si_summary.invoiced_amount, 0)) > 0
        ORDER BY dn.posting_date DESC
    """, (customer, company), as_dict=True)
    
    # Calculate DN outstanding
    dn_outstanding = 0
    for dn_item in delivery_notes_detail:
        if dn_item.uninvoiced_amount > 0 and dn_item.base_net_total:
            # Proportional calculation as per ERPNext logic
            proportion = dn_item.uninvoiced_amount / dn_item.base_net_total
            dn_outstanding += proportion * dn_item.base_grand_total
    
    # 5. Payment Entries - Only truly unallocated amounts
    # These are payments sitting as credit that haven't been allocated to any invoice
    payments = frappe.db.sql("""
        SELECT 
            pe.name,
            pe.posting_date,
            pe.paid_amount,
            pe.unallocated_amount,
            pe.reference_no,
            pe.reference_date,
            CASE 
                WHEN pe.unallocated_amount > 0 THEN 'Unallocated'
                ELSE 'Fully Allocated'
            END as allocation_status
        FROM `tabPayment Entry` pe
        WHERE pe.party_type = 'Customer' 
            AND pe.party = %s 
            AND pe.company = %s 
            AND pe.docstatus = 1
        ORDER BY pe.posting_date DESC
    """, (customer, company), as_dict=True)
    
    # Only count truly unallocated amounts (these provide additional credit)
    unallocated_payments = [pe for pe in payments if flt(pe.unallocated_amount) > 0]
    total_unallocated = sum(flt(pe.unallocated_amount) for pe in unallocated_payments)
    
    # 6. Detailed breakdown summary - Using ERPNext's method as the definitive calculation
    # The issue: GL entries already reflect allocated payments, so we shouldn't double-count
    # ERPNext's get_customer_outstanding handles this complexity correctly
    
    breakdown = {
        'gl_net_position': gl_amount,  # Net receivable after allocations (can be negative)
        'invoice_outstanding_gross': invoice_outstanding_amount,  # Gross invoice outstanding
        'so_outstanding': so_outstanding,  # Unbilled sales orders
        'dn_outstanding': dn_outstanding,  # Unbilled deliveries  
        'total_unallocated_payments': total_unallocated,  # Additional unallocated credits
        'erpnext_calculation': total_outstanding,  # ERPNext's authoritative calculation
        'manual_simple': gl_amount + so_outstanding + dn_outstanding,  # Simple addition
        'explanation': 'ERPNext uses complex logic for allocated vs unallocated payments'
    }
    
    # Log detailed information for debugging
    frappe.log_error(frappe.as_json({
        "customer": customer,
        "company": company,
        "credit_limit": credit_limit,
        "breakdown": breakdown,
        "balance": balance,
        "invoices_count": len(invoices),
        "sales_orders_count": len(sales_orders),
        "delivery_notes_count": len(delivery_notes_detail),
        "payments_count": len(payments),
    }), "DEBUG Enhanced Credit Balance")
    
    return {
        "credit_limit": credit_limit,
        "outstanding": total_outstanding,
        "balance": balance,
        "breakdown": breakdown,
        
        # Detailed data
        "invoices": invoices,
        "sales_orders": sales_orders,
        "delivery_notes": delivery_notes_detail,
        # Return both allocated and unallocated payments for display
        "payments": payments,
        "unallocated_payments": unallocated_payments,
        
        # Summary totals
        "total_invoice_outstanding": sum(flt(inv.outstanding_amount) for inv in invoices),
        "total_so_unbilled": so_outstanding,
        "total_dn_unbilled": dn_outstanding,
        "total_unallocated_payments": total_unallocated,
        
        # Calculation verification - now more realistic
        "calculation_check": {
            "simple_manual": breakdown['manual_simple'],
            "erpnext_authoritative": total_outstanding,
            "difference": abs(breakdown['manual_simple'] - total_outstanding),
            "note": "ERPNext handles payment allocation complexity that our simple calculation cannot replicate"
        }
    }

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
