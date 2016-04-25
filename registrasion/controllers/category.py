from registrasion.models import commerce
from registrasion.models import inventory

from django.db.models import Sum


class AllProducts(object):
    pass


class CategoryController(object):

    def __init__(self, category):
        self.category = category

    @classmethod
    def available_categories(cls, user, products=AllProducts):
        ''' Returns the categories available to the user. Specify `products` if
        you want to restrict to just the categories that hold the specified
        products, otherwise it'll do all. '''

        # STOPGAP -- this needs to be elsewhere tbqh
        from product import ProductController

        if products is AllProducts:
            products = inventory.Product.objects.all().select_related(
                "category",
            )

        available = ProductController.available_products(
            user,
            products=products,
        )

        return set(i.category for i in available)

    def user_quantity_remaining(self, user):
        ''' Returns the number of items from this category that the user may
        add in the current cart. '''

        cat_limit = self.category.limit_per_user

        if cat_limit is None:
            # We don't need to waste the following queries
            return 99999999

        carts = commerce.Cart.objects.filter(
            user=user,
            status=commerce.Cart.STATUS_PAID,
        )

        items = commerce.ProductItem.objects.filter(
            cart__in=carts,
            product__category=self.category,
        )

        cat_count = items.aggregate(Sum("quantity"))["quantity__sum"] or 0
        return cat_limit - cat_count
