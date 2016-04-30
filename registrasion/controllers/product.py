import itertools

from django.db.models import Case
from django.db.models import F, Q
from django.db.models import Sum
from django.db.models import When
from django.db.models import Value

from registrasion.models import commerce
from registrasion.models import inventory

from .category import CategoryController
from .flag import FlagController


class ProductController(object):

    def __init__(self, product):
        self.product = product

    @classmethod
    def available_products(cls, user, category=None, products=None):
        ''' Returns a list of all of the products that are available per
        flag conditions from the given categories. '''
        if category is None and products is None:
            raise ValueError("You must provide products or a category")

        if category is not None:
            all_products = inventory.Product.objects.filter(category=category)
            all_products = all_products.select_related("category")
        else:
            all_products = []

        if products is not None:
            all_products = set(itertools.chain(all_products, products))

        category_remainders = CategoryController.user_remainders(user)
        product_remainders = ProductController.user_remainders(user)

        passed_limits = set(
            product
            for product in all_products
            if category_remainders[product.category.id] > 0
            if product_remainders[product.id] > 0
        )

        failed_and_messages = FlagController.test_flags(
            user, products=passed_limits
        )
        failed_conditions = set(i[0] for i in failed_and_messages)

        out = list(passed_limits - failed_conditions)
        out.sort(key=lambda product: product.order)

        return out

    @classmethod
    def user_remainders(cls, user):
        '''

        Return:
            Mapping[int->int]: A dictionary that maps the product ID to the
            user's remainder for that product.
        '''

        products = inventory.Product.objects.all()

        cart_filter = (
            Q(productitem__cart__user=user) &
            Q(productitem__cart__status=commerce.Cart.STATUS_PAID)
        )

        quantity = When(
            cart_filter,
            then='productitem__quantity'
        )

        quantity_or_zero = Case(
            quantity,
            default=Value(0),
        )

        remainder = Case(
            When(limit_per_user=None, then=Value(99999999)),
            default=F('limit_per_user') - Sum(quantity_or_zero),
        )

        products = products.annotate(remainder=remainder)

        return dict((product.id, product.remainder) for product in products)
