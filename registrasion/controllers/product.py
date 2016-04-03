import itertools

from django.db.models import Sum
from registrasion import models as rego

from category import CategoryController
from conditions import ConditionController


class ProductController(object):

    def __init__(self, product):
        self.product = product

    @classmethod
    def available_products(cls, user, category=None, products=None):
        ''' Returns a list of all of the products that are available per
        enabling conditions from the given categories.
        TODO: refactor so that all conditions are tested here and
        can_add_with_enabling_conditions calls this method. '''
        if category is None and products is None:
            raise ValueError("You must provide products or a category")

        if category is not None:
            all_products = rego.Product.objects.filter(category=category)
        else:
            all_products = []

        if products is not None:
            all_products = itertools.chain(all_products, products)

        passed_limits = set(
            product
            for product in all_products
            if CategoryController(product.category).user_quantity_remaining(
                user
            ) > 0
            if cls(product).user_quantity_remaining(user) > 0
        )

        failed_conditions = set(ConditionController.test_enabling_conditions(
            user, products=passed_limits
        ))

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

        carts = rego.Cart.objects.filter(
            user=user,
            active=False,
            released=False,
        )

        items = rego.ProductItem.objects.filter(
            cart__in=carts,
            product=self.product,
        )

        prod_count = items.aggregate(Sum("quantity"))["quantity__sum"] or 0

        return prod_limit - prod_count
