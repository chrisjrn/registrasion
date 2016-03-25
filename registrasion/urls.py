from django.conf.urls import url, patterns

urlpatterns = patterns(
    "registrasion.views",
    url(r"^category/([0-9]+)$", "product_category", name="product_category"),
    url(r"^checkout$", "checkout", name="checkout"),
    url(r"^invoice/([0-9]+)$", "invoice", name="invoice"),
    url(r"^invoice/([0-9]+)/pay$", "pay_invoice", name="pay_invoice"),
    url(r"^profile$", "edit_profile", name="profile"),
    url(r"^register$", "guided_registration", name="guided_registration"),
    url(r"^register/([0-9]+)$", "guided_registration", name="guided_registration"),
)
