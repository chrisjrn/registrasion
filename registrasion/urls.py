import views
import staff_views

from django.conf.urls import url, patterns

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
)

urlpatterns = [
    url(r"^category/([0-9]+)$", product_category, name="product_category"),
    url(r"^checkout$", checkout, name="checkout"),
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
    url(r"^report$", staff_views.items_sold, name="items_sold"),  # TODO: rm
]
