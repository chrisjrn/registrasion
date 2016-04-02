from django.db.models import Q
from django.db.models import Sum
from django.utils import timezone

from registrasion import models as rego


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
                TimeOrStockLimitConditionController,
            rego.TimeOrStockLimitEnablingCondition:
                TimeOrStockLimitConditionController,
            rego.VoucherDiscount: VoucherConditionController,
            rego.VoucherEnablingCondition: VoucherConditionController,
        }

        try:
            return CONTROLLERS[type(condition)](condition)
        except KeyError:
            return ConditionController()

    def is_met(self, user, quantity):
        return True


class CategoryConditionController(ConditionController):

    def __init__(self, condition):
        self.condition = condition

    def is_met(self, user, quantity):
        ''' returns True if the user has a product from a category that invokes
        this condition in one of their carts '''

        carts = rego.Cart.objects.filter(user=user, released=False)
        enabling_products = rego.Product.objects.filter(
            category=self.condition.enabling_category,
        )
        products = rego.ProductItem.objects.filter(
            cart=carts,
            product__in=enabling_products,
        )
        return len(products) > 0


class ProductConditionController(ConditionController):
    ''' Condition tests for ProductEnablingCondition and
    IncludedProductDiscount. '''

    def __init__(self, condition):
        self.condition = condition

    def is_met(self, user, quantity):
        ''' returns True if the user has a product that invokes this
        condition in one of their carts '''

        carts = rego.Cart.objects.filter(user=user, released=False)
        products = rego.ProductItem.objects.filter(
            cart=carts,
            product__in=self.condition.enabling_products.all(),
        )
        return len(products) > 0


class TimeOrStockLimitConditionController(ConditionController):
    ''' Condition tests for TimeOrStockLimit EnablingCondition and
    Discount.'''

    def __init__(self, ceiling):
        self.ceiling = ceiling

    def is_met(self, user, quantity):
        ''' returns True if adding _quantity_ of _product_ will not vioilate
        this ceiling. '''

        # Test date range
        if not self.test_date_range():
            return False

        # Test limits
        if not self.test_limits(quantity):
            return False

        # All limits have been met
        return True

    def test_date_range(self):
        now = timezone.now()

        if self.ceiling.start_time is not None:
            if now < self.ceiling.start_time:
                return False

        if self.ceiling.end_time is not None:
            if now > self.ceiling.end_time:
                return False

        return True

    def _products(self):
        ''' Abstracts away the product list, becuase enabling conditions
        list products differently to discounts. '''
        if isinstance(self.ceiling, rego.TimeOrStockLimitEnablingCondition):
            category_products = rego.Product.objects.filter(
                category=self.ceiling.categories.all(),
            )
            return self.ceiling.products.all() | category_products
        else:
            categories = rego.Category.objects.filter(
                discountforcategory__discount=self.ceiling,
            )
            return rego.Product.objects.filter(
                Q(discountforproduct__discount=self.ceiling) |
                Q(category=categories.all())
            )

    def test_limits(self, quantity):
        if self.ceiling.limit is None:
            return True

        reserved_carts = rego.Cart.reserved_carts()
        product_items = rego.ProductItem.objects.filter(
            product__in=self._products().all(),
        )
        product_items = product_items.filter(cart=reserved_carts)

        agg = product_items.aggregate(Sum("quantity"))
        count = agg["quantity__sum"]
        if count is None:
            count = 0

        if count + quantity > self.ceiling.limit:
            return False

        return True


class VoucherConditionController(ConditionController):
    ''' Condition test for VoucherEnablingCondition and VoucherDiscount.'''

    def __init__(self, condition):
        self.condition = condition

    def is_met(self, user, quantity):
        ''' returns True if the user has the given voucher attached. '''
        carts = rego.Cart.objects.filter(
            user=user,
            vouchers=self.condition.voucher,
        )
        return len(carts) > 0
