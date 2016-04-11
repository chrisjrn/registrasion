import views

from django.conf.urls import url, patterns

urlpatterns = patterns(
    "registrasion.views",
    url(r"^category/([0-9]+)$", "product_category", name="product_category"),
    url(r"^checkout$", "checkout", name="checkout"),
    url(r"^credit_note/([0-9]+)$", views.credit_note, name="credit_note"),
    url(r"^invoice/([0-9]+)$", "invoice", name="invoice"),
    url(r"^invoice/([0-9]+)/([A-Z0-9]+)$", views.invoice, name="invoice"),
    url(r"^invoice/([0-9]+)/manual_payment$",
        views.manual_payment, name="manual_payment"),
    url(r"^invoice/([0-9]+)/refund$",
        views.refund, name="refund"),
    url(r"^invoice_access/([A-Z0-9]+)$", views.invoice_access,
        name="invoice_access"),
    url(r"^profile$", "edit_profile", name="attendee_edit"),
    url(r"^register$", "guided_registration", name="guided_registration"),
    url(r"^register/([0-9]+)$", "guided_registration",
        name="guided_registration"),
)
