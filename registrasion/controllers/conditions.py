import itertools

from collections import defaultdict
from collections import namedtuple

from django.db.models import Q
from django.db.models import Sum
from django.utils import timezone

from registrasion import models as rego


ConditionAndRemainder = namedtuple(
    "ConditionAndRemainder",
    (
        "condition",
        "remainder",
    ),
)


class ConditionController(object):
    ''' Base class for testing conditions that activate EnablingCondition
    or Discount objects. '''

    def __init__(self):
        pass

    @staticmethod
    def for_condition(condition):
        CONTROLLERS = {
            rego.CategoryEnablingCondition: CategoryConditionController,
            rego.IncludedProductDiscount: ProductConditionController,
            rego.ProductEnablingCondition: ProductConditionController,
            rego.TimeOrStockLimitDiscount:
                TimeOrStockLimitDiscountController,
            rego.TimeOrStockLimitEnablingCondition:
                TimeOrStockLimitEnablingConditionController,
            rego.VoucherDiscount: VoucherConditionController,
            rego.VoucherEnablingCondition: VoucherConditionController,
        }

        try:
            return CONTROLLERS[type(condition)](condition)
        except KeyError:
            return ConditionController()

    @classmethod
    def test_enabling_conditions(
            cls, user, products=None, product_quantities=None):
        ''' Evaluates all of the enabling conditions on the given products.

        If `product_quantities` is supplied, the condition is only met if it
        will permit the sum of the product quantities for all of the products
        it covers. Otherwise, it will be met if at least one item can be
        accepted.

        If all enabling conditions pass, an empty list is returned, otherwise
        a list is returned containing all of the products that are *not
        enabled*. '''

        if products is not None and product_quantities is not None:
            raise ValueError("Please specify only products or "
                             "product_quantities")
        elif products is None:
            products = set(i[0] for i in product_quantities)
            quantities = dict( (product, quantity)
                for product, quantity in product_quantities )
        elif product_quantities is None:
            products = set(products)
            quantities = {}

        # Get the conditions covered by the products themselves
        all_conditions = [
            product.enablingconditionbase_set.select_subclasses() |
            product.category.enablingconditionbase_set.select_subclasses()
            for product in products
        ]
        all_conditions = set(itertools.chain(*all_conditions))

        # All mandatory conditions on a product need to be met
        mandatory = defaultdict(lambda: True)
        # At least one non-mandatory condition on a product must be met
        # if there are no mandatory conditions
        non_mandatory = defaultdict(lambda: False)

        remainders = []
        for condition in all_conditions:
            cond = cls.for_condition(condition)
            remainder = cond.user_quantity_remaining(user)

            # Get all products covered by this condition, and the products
            # from the categories covered by this condition
            cond_products = condition.products.all()
            from_category = rego.Product.objects.filter(
                category__in=condition.categories.all(),
            ).all()
            all_products = set(itertools.chain(cond_products, from_category))

            # Remove the products that we aren't asking about
            all_products = all_products & products

            if quantities:
                consumed = sum(quantities[i] for i in all_products)
            else:
                consumed = 1
            met = consumed <= remainder

            for product in all_products:
                if condition.mandatory:
                    mandatory[product] &= met
                else:
                    non_mandatory[product] |= met

        valid = defaultdict(lambda: True)
        for product in itertools.chain(mandatory, non_mandatory):
            if product in mandatory:
                # If there's a mandatory condition, all must be met
                valid[product] = mandatory[product]
            else:
                # Otherwise, we need just one non-mandatory condition met
                valid[product] = non_mandatory[product]

        error_fields = [product for product in valid if not valid[product]]
        return error_fields

    def user_quantity_remaining(self, user):
        ''' Returns the number of items covered by this enabling condition the
        user can add to the current cart. This default implementation returns
        a big number if is_met() is true, otherwise 0.

        Either this method, or is_met() must be overridden in subclasses.
        '''

        return 99999999 if self.is_met(user) else 0

    def is_met(self, user):
        ''' Returns True if this enabling condition is met, otherwise returns
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

        carts = rego.Cart.objects.filter(user=user, released=False)
        enabling_products = rego.Product.objects.filter(
            category=self.condition.enabling_category,
        )
        products_count = rego.ProductItem.objects.filter(
            cart__in=carts,
            product__in=enabling_products,
        ).count()
        return products_count > 0


class ProductConditionController(ConditionController):
    ''' Condition tests for ProductEnablingCondition and
    IncludedProductDiscount. '''

    def __init__(self, condition):
        self.condition = condition

    def is_met(self, user):
        ''' returns True if the user has a product that invokes this
        condition in one of their carts '''

        carts = rego.Cart.objects.filter(user=user, released=False)
        products_count = rego.ProductItem.objects.filter(
            cart__in=carts,
            product__in=self.condition.enabling_products.all(),
        ).count()
        return products_count > 0


class TimeOrStockLimitConditionController(ConditionController):
    ''' Common condition tests for TimeOrStockLimit EnablingCondition and
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
        reserved_carts = rego.Cart.reserved_carts()
        reserved_carts = reserved_carts.exclude(
            user=user,
            active=True,
        )

        items = self._items()
        items = items.filter(cart__in=reserved_carts)
        count = items.aggregate(Sum("quantity"))["quantity__sum"] or 0

        return self.ceiling.limit - count

class TimeOrStockLimitEnablingConditionController(
        TimeOrStockLimitConditionController):

    def _items(self):
        category_products = rego.Product.objects.filter(
            category__in=self.ceiling.categories.all(),
        )
        products = self.ceiling.products.all() | category_products

        product_items = rego.ProductItem.objects.filter(
            product__in=products.all(),
        )
        return product_items


class TimeOrStockLimitDiscountController(TimeOrStockLimitConditionController):

    def _items(self):
        discount_items = rego.DiscountItem.objects.filter(
            discount=self.ceiling,
        )
        return discount_items


class VoucherConditionController(ConditionController):
    ''' Condition test for VoucherEnablingCondition and VoucherDiscount.'''

    def __init__(self, condition):
        self.condition = condition

    def is_met(self, user):
        ''' returns True if the user has the given voucher attached. '''
        carts_count = rego.Cart.objects.filter(
            user=user,
            vouchers=self.condition.voucher,
        ).count()
        return carts_count > 0
