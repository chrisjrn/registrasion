from registrasion.models import commerce
from registrasion.models import inventory

from django.db.models import Case
from django.db.models import F, Q
from django.db.models import Sum
from django.db.models import When
from django.db.models import Value

from .batch import BatchController

from operator import attrgetter


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

        return sorted(set(i.category for i in available), key=attrgetter("order"))

    @classmethod
    @BatchController.memoise
    def user_remainders(cls, user):
        '''

        Return:
            Mapping[int->int]: A dictionary that maps the category ID to the
            user's remainder for that category.

        '''

        categories = inventory.Category.objects.all()

        cart_filter = (
            Q(product__productitem__cart__user=user) &
            Q(product__productitem__cart__status=commerce.Cart.STATUS_PAID)
        )

        quantity = When(
            cart_filter,
            then='product__productitem__quantity'
        )

        quantity_or_zero = Case(
            quantity,
            default=Value(0),
        )

        remainder = Case(
            When(limit_per_user=None, then=Value(99999999)),
            default=F('limit_per_user') - Sum(quantity_or_zero),
        )

        categories = categories.annotate(remainder=remainder)

        return dict((cat.id, cat.remainder) for cat in categories)
