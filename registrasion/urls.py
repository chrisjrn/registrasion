from reporting import views as rv

from django.conf.urls import include
from django.conf.urls import url

from .views import (
    amend_registration,
    checkout,
    credit_note,
    edit_profile,
    guided_registration,
    invoice,
    invoice_access,
    manual_payment,
    product_category,
    refund,
    review,
)


public = [
    url(r"^amend/([0-9]+)$", amend_registration, name="amend_registration"),
    url(r"^category/([0-9]+)$", product_category, name="product_category"),
    url(r"^checkout$", checkout, name="checkout"),
    url(r"^checkout/([0-9]+)$", checkout, name="checkout"),
    url(r"^credit_note/([0-9]+)$", credit_note, name="credit_note"),
    url(r"^invoice/([0-9]+)$", invoice, name="invoice"),
    url(r"^invoice/([0-9]+)/([A-Z0-9]+)$", invoice, name="invoice"),
    url(r"^invoice/([0-9]+)/manual_payment$",
        manual_payment, name="manual_payment"),
    url(r"^invoice/([0-9]+)/refund$",
        refund, name="refund"),
    url(r"^invoice_access/([A-Z0-9]+)$", invoice_access,
        name="invoice_access"),
    url(r"^profile$", edit_profile, name="attendee_edit"),
    url(r"^register$", guided_registration, name="guided_registration"),
    url(r"^review$", review, name="review"),
    url(r"^register/([0-9]+)$", guided_registration,
        name="guided_registration"),
]


reports = [
    url(r"^$", rv.reports_list, name="reports_list"),
    url(r"^attendee/?$", rv.attendee, name="attendee"),
    url(r"^attendee/([0-9]*)$", rv.attendee, name="attendee"),
    url(r"^credit_notes/?$", rv.credit_notes, name="credit_notes"),
    url(r"^discount_status/?$", rv.discount_status, name="discount_status"),
    url(
        r"^paid_invoices_by_date/?$",
        rv.paid_invoices_by_date,
        name="paid_invoices_by_date"
    ),
    url(r"^product_status/?$", rv.product_status, name="product_status"),
    url(r"^reconciliation/?$", rv.reconciliation, name="reconciliation"),
]


urlpatterns = [
    url(r"^reports/", include(reports)),
    url(r"^", include(public))  # This one must go last.
]
