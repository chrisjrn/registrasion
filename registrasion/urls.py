from django.conf.urls import url, patterns

urlpatterns = patterns(
    "registrasion.views",
    url(r"^category/([0-9]+)$", "product_category", name="product_category"),
    #    url(r"^category$", "product_category", name="product_category"),
)
