import itertools

from django.db.models import Sum
from registrasion.models import commerce
from registrasion.models import inventory

from category import CategoryController
from conditions import ConditionController


class ProductController(object):

    def __init__(self, product):
        self.product = product

    @classmethod
    def available_products(cls, user, category=None, products=None):
        ''' Returns a list of all of the products that are available per
        flag conditions from the given categories.
        TODO: refactor so that all conditions are tested here and
        can_add_with_flags calls this method. '''
        if category is None and products is None:
            raise ValueError("You must provide products or a category")

        if category is not None:
            all_products = inventory.Product.objects.filter(category=category)
            all_products = all_products.select_related("category")
        else:
            all_products = []

        if products is not None:
            all_products = set(itertools.chain(all_products, products))

        cat_quants = dict(
            (
                category,
                CategoryController(category).user_quantity_remaining(user),
            )
            for category in set(product.category for product in all_products)
        )

        passed_limits = set(
            product
            for product in all_products
            if cat_quants[product.category] > 0
            if cls(product).user_quantity_remaining(user) > 0
        )

        failed_and_messages = ConditionController.test_flags(
            user, products=passed_limits
        )
        failed_conditions = set(i[0] for i in failed_and_messages)

        out = list(passed_limits - failed_conditions)
        out.sort(key=lambda product: product.order)

        return out

    def user_quantity_remaining(self, user):
        ''' Returns the quantity of this product that the user add in the
        current cart. '''

        prod_limit = self.product.limit_per_user

        if prod_limit is None:
            # Don't need to run the remaining queries
            return 999999  # We can do better

        carts = commerce.Cart.objects.filter(
            user=user,
            status=commerce.Cart.STATUS_PAID,
        )

        items = commerce.ProductItem.objects.filter(
            cart__in=carts,
            product=self.product,
        )

        prod_count = items.aggregate(Sum("quantity"))["quantity__sum"] or 0

        return prod_limit - prod_count
