import itertools
import operator

from collections import defaultdict
from collections import namedtuple

from django.db.models import Sum
from django.utils import timezone

from registrasion.models import commerce
from registrasion.models import conditions
from registrasion.models import inventory


ConditionAndRemainder = namedtuple(
    "ConditionAndRemainder",
    (
        "condition",
        "remainder",
    ),
)


class ConditionController(object):
    ''' Base class for testing conditions that activate Flag
    or Discount objects. '''

    def __init__(self):
        pass

    @staticmethod
    def for_condition(condition):
        CONTROLLERS = {
            conditions.CategoryFlag: CategoryConditionController,
            conditions.IncludedProductDiscount: ProductConditionController,
            conditions.ProductFlag: ProductConditionController,
            conditions.TimeOrStockLimitDiscount:
                TimeOrStockLimitDiscountController,
            conditions.TimeOrStockLimitFlag:
                TimeOrStockLimitFlagController,
            conditions.VoucherDiscount: VoucherConditionController,
            conditions.VoucherFlag: VoucherConditionController,
        }

        try:
            return CONTROLLERS[type(condition)](condition)
        except KeyError:
            return ConditionController()

    SINGLE = True
    PLURAL = False
    NONE = True
    SOME = False
    MESSAGE = {
        NONE: {
            SINGLE:
                "%(items)s is no longer available to you",
            PLURAL:
                "%(items)s are no longer available to you",
        },
        SOME: {
            SINGLE:
                "Only %(remainder)d of the following item remains: %(items)s",
            PLURAL:
                "Only %(remainder)d of the following items remain: %(items)s"
        },
    }

    @classmethod
    def test_flags(
            cls, user, products=None, product_quantities=None):
        ''' Evaluates all of the flag conditions on the given products.

        If `product_quantities` is supplied, the condition is only met if it
        will permit the sum of the product quantities for all of the products
        it covers. Otherwise, it will be met if at least one item can be
        accepted.

        If all flag conditions pass, an empty list is returned, otherwise
        a list is returned containing all of the products that are *not
        enabled*. '''

        if products is not None and product_quantities is not None:
            raise ValueError("Please specify only products or "
                             "product_quantities")
        elif products is None:
            products = set(i[0] for i in product_quantities)
            quantities = dict((product, quantity)
                              for product, quantity in product_quantities)
        elif product_quantities is None:
            products = set(products)
            quantities = {}

        # Get the conditions covered by the products themselves
        prods = (
            product.flagbase_set.select_subclasses()
            for product in products
        )
        # Get the conditions covered by their categories
        cats = (
            category.flagbase_set.select_subclasses()
            for category in set(product.category for product in products)
        )

        if products:
            # Simplify the query.
            all_conditions = reduce(operator.or_, itertools.chain(prods, cats))
        else:
            all_conditions = []

        # All disable-if-false conditions on a product need to be met
        do_not_disable = defaultdict(lambda: True)
        # At least one enable-if-true condition on a product must be met
        do_enable = defaultdict(lambda: False)
        # (if either sort of condition is present)

        messages = {}

        for condition in all_conditions:
            cond = cls.for_condition(condition)
            remainder = cond.user_quantity_remaining(user)

            # Get all products covered by this condition, and the products
            # from the categories covered by this condition
            cond_products = condition.products.all()
            from_category = inventory.Product.objects.filter(
                category__in=condition.categories.all(),
            ).all()
            all_products = cond_products | from_category
            all_products = all_products.select_related("category")
            # Remove the products that we aren't asking about
            all_products = [
                product
                for product in all_products
                if product in products
            ]

            if quantities:
                consumed = sum(quantities[i] for i in all_products)
            else:
                consumed = 1
            met = consumed <= remainder

            if not met:
                items = ", ".join(str(product) for product in all_products)
                base = cls.MESSAGE[remainder == 0][len(all_products) == 1]
                message = base % {"items": items, "remainder": remainder}

            for product in all_products:
                if condition.is_disable_if_false:
                    do_not_disable[product] &= met
                else:
                    do_enable[product] |= met

                if not met and product not in messages:
                    messages[product] = message

        valid = {}
        for product in itertools.chain(do_not_disable, do_enable):
            if product in do_enable:
                # If there's an enable-if-true, we need need of those met too.
                # (do_not_disable will default to true otherwise)
                valid[product] = do_not_disable[product] and do_enable[product]
            elif product in do_not_disable:
                # If there's a disable-if-false condition, all must be met
                valid[product] = do_not_disable[product]

        error_fields = [
            (product, messages[product])
            for product in valid if not valid[product]
        ]

        return error_fields

    def user_quantity_remaining(self, user):
        ''' Returns the number of items covered by this flag condition the
        user can add to the current cart. This default implementation returns
        a big number if is_met() is true, otherwise 0.

        Either this method, or is_met() must be overridden in subclasses.
        '''

        return 99999999 if self.is_met(user) else 0

    def is_met(self, user):
        ''' Returns True if this flag condition is met, otherwise returns
        False.

        Either this method, or user_quantity_remaining() must be overridden
        in subclasses.
        '''
        return self.user_quantity_remaining(user) > 0


class CategoryConditionController(ConditionController):

    def __init__(self, condition):
        self.condition = condition

    def is_met(self, user):
        ''' returns True if the user has a product from a category that invokes
        this condition in one of their carts '''

        carts = commerce.Cart.objects.filter(user=user)
        carts = carts.exclude(status=commerce.Cart.STATUS_RELEASED)
        enabling_products = inventory.Product.objects.filter(
            category=self.condition.enabling_category,
        )
        products_count = commerce.ProductItem.objects.filter(
            cart__in=carts,
            product__in=enabling_products,
        ).count()
        return products_count > 0


class ProductConditionController(ConditionController):
    ''' Condition tests for ProductFlag and
    IncludedProductDiscount. '''

    def __init__(self, condition):
        self.condition = condition

    def is_met(self, user):
        ''' returns True if the user has a product that invokes this
        condition in one of their carts '''

        carts = commerce.Cart.objects.filter(user=user)
        carts = carts.exclude(status=commerce.Cart.STATUS_RELEASED)
        products_count = commerce.ProductItem.objects.filter(
            cart__in=carts,
            product__in=self.condition.enabling_products.all(),
        ).count()
        return products_count > 0


class TimeOrStockLimitConditionController(ConditionController):
    ''' Common condition tests for TimeOrStockLimit Flag and
    Discount.'''

    def __init__(self, ceiling):
        self.ceiling = ceiling

    def user_quantity_remaining(self, user):
        ''' returns 0 if the date range is violated, otherwise, it will return
        the quantity remaining under the stock limit. '''

        # Test date range
        if not self._test_date_range():
            return 0

        return self._get_remaining_stock(user)

    def _test_date_range(self):
        now = timezone.now()

        if self.ceiling.start_time is not None:
            if now < self.ceiling.start_time:
                return False

        if self.ceiling.end_time is not None:
            if now > self.ceiling.end_time:
                return False

        return True

    def _get_remaining_stock(self, user):
        ''' Returns the stock that remains under this ceiling, excluding the
        user's current cart. '''

        if self.ceiling.limit is None:
            return 99999999

        # We care about all reserved carts, but not the user's current cart
        reserved_carts = commerce.Cart.reserved_carts()
        reserved_carts = reserved_carts.exclude(
            user=user,
            status=commerce.Cart.STATUS_ACTIVE,
        )

        items = self._items()
        items = items.filter(cart__in=reserved_carts)
        count = items.aggregate(Sum("quantity"))["quantity__sum"] or 0

        return self.ceiling.limit - count


class TimeOrStockLimitFlagController(
        TimeOrStockLimitConditionController):

    def _items(self):
        category_products = inventory.Product.objects.filter(
            category__in=self.ceiling.categories.all(),
        )
        products = self.ceiling.products.all() | category_products

        product_items = commerce.ProductItem.objects.filter(
            product__in=products.all(),
        )
        return product_items


class TimeOrStockLimitDiscountController(TimeOrStockLimitConditionController):

    def _items(self):
        discount_items = commerce.DiscountItem.objects.filter(
            discount=self.ceiling,
        )
        return discount_items


class VoucherConditionController(ConditionController):
    ''' Condition test for VoucherFlag and VoucherDiscount.'''

    def __init__(self, condition):
        self.condition = condition

    def is_met(self, user):
        ''' returns True if the user has the given voucher attached. '''
        carts_count = commerce.Cart.objects.filter(
            user=user,
            vouchers=self.condition.voucher,
        ).count()
        return carts_count > 0
