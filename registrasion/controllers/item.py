''' NEEDS TESTS '''

from registrasion.models import commerce
from registrasion.models import inventory

from collections import namedtuple
from django.db.models import Case
from django.db.models import Q
from django.db.models import Sum
from django.db.models import When
from django.db.models import Value

_ProductAndQuantity = namedtuple("ProductAndQuantity", ["product", "quantity"])


class ProductAndQuantity(_ProductAndQuantity):
    ''' Class that holds a product and a quantity.

    Attributes:
        product (models.inventory.Product)

        quantity (int)

    '''
    pass


class ItemController(object):

    def __init__(self, user):
        self.user = user

    def _items(self, cart_status, category=None):
        ''' Aggregates the items that this user has purchased.

        Arguments:
            category (Optional[models.inventory.Category]): the category
                of items to restrict to.

        Returns:
            [ProductAndQuantity, ...]: A list of product-quantity pairs,
                aggregating like products from across multiple invoices.

        '''

        in_cart = (
            Q(productitem__cart__user=self.user) &
            Q(productitem__cart__status=cart_status)
        )

        quantities_in_cart = When(
            in_cart,
            then="productitem__quantity",
        )

        quantities_or_zero = Case(
            quantities_in_cart,
            default=Value(0),
        )

        products = inventory.Product.objects

        if category:
            products = products.filter(category=category)

        products = products.select_related("category")
        products = products.annotate(quantity=Sum(quantities_or_zero))
        products = products.filter(quantity__gt=0)

        out = []
        for prod in products:
            out.append(ProductAndQuantity(prod, prod.quantity))
        return out

    def items_purchased(self, category=None):
        ''' Aggregates the items that this user has purchased.

        Arguments:
            category (Optional[models.inventory.Category]): the category
                of items to restrict to.

        Returns:
            [ProductAndQuantity, ...]: A list of product-quantity pairs,
                aggregating like products from across multiple invoices.

        '''
        return self._items(commerce.Cart.STATUS_PAID, category=category)

    def items_pending(self):
        ''' Gets all of the items that the user has reserved, but has not yet
        paid for.

        Returns:
            [ProductAndQuantity, ...]: A list of product-quantity pairs for the
                items that the user has not yet paid for.

        '''

        return self._items(commerce.Cart.STATUS_ACTIVE)

    def items_released(self):
        ''' Gets all of the items that the user previously paid for, but has
        since refunded.

        Returns:
            [ProductAndQuantity, ...]: A list of product-quantity pairs for the
                items that the user has not yet paid for.

        '''

        return self._items(commerce.Cart.STATUS_RELEASED)
