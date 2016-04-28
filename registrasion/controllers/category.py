from registrasion.models import commerce
from registrasion.models import inventory

from django.db.models import Case
from django.db.models import F, Q
from django.db.models import Sum
from django.db.models import When
from django.db.models import Value


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


    @classmethod
    def attach_user_remainders(cls, user, categories):
        '''

        Return:
            queryset(inventory.Product): A queryset containing items from
            ``categories``, with an extra attribute -- remainder = the amount
            of items from this category that is remaining.
        '''

        ids = [category.id for category in categories]
        categories = inventory.Category.objects.filter(id__in=ids)

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

        return categories

    def user_quantity_remaining(self, user):
        ''' Returns the quantity of this product that the user add in the
        current cart. '''

        with_remainders = self.attach_user_remainders(user, [self.category])

        return with_remainders[0].remainder
