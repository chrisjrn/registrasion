from reporting import views as rv

from django.conf.urls import include
from django.conf.urls import url

from .views import (
    product_category,
    checkout,
    credit_note,
    invoice,
    manual_payment,
    refund,
    invoice_access,
    edit_profile,
    guided_registration,
    amend_registration,
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
    url(r"^register/([0-9]+)$", guided_registration,
        name="guided_registration"),
]


reports = [
    url(r"^$", rv.reports_list, name="reports_list"),
    url(r"^attendee/?$", rv.attendee, name="attendee"),
    url(r"^attendee/([0-9]*)$", rv.attendee, name="attendee"),
    url(r"^credit_notes/?$", rv.credit_notes, name="credit_notes"),
    url(r"^items_sold/?$", rv.items_sold, name="items_sold"),
    url(r"^product_status/?$", rv.product_status, name="product_status"),
    url(r"^reconciliation/?$", rv.reconciliation, name="reconciliation"),
]


urlpatterns = [
    url(r"^reports/", include(reports)),
    url(r"^", include(public))  # This one must go last.
]
