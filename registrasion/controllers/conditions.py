import itertools
import operator

from collections import defaultdict
from collections import namedtuple

from django.db.models import Case
from django.db.models import Count
from django.db.models import F, Q
from django.db.models import Sum
from django.db.models import Value
from django.db.models import When
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


_FlagCounter = namedtuple(
    "_FlagCounter",
    (
        "products",
        "categories",
    ),
)


_ConditionsCount = namedtuple(
    "ConditionsCount",
    (
        "dif",
        "eit",
    ),
)


class FlagCounter(_FlagCounter):

    @classmethod
    def count(cls):
        # Get the count of how many conditions should exist per product
        flagbases = conditions.FlagBase.objects

        types = (
            conditions.FlagBase.ENABLE_IF_TRUE,
            conditions.FlagBase.DISABLE_IF_FALSE,
        )
        keys = ("eit", "dif")
        flags = [
            flagbases.filter(
                condition=condition_type
            ).values(
                'products', 'categories'
            ).annotate(
                count=Count('id')
            )
            for condition_type in types
        ]

        cats = defaultdict(lambda: defaultdict(int))
        prod = defaultdict(lambda: defaultdict(int))

        for key, flagcounts in zip(keys, flags):
            for row in flagcounts:
                if row["products"] is not None:
                    prod[row["products"]][key] = row["count"]
                if row["categories"] is not None:
                    cats[row["categories"]][key] = row["count"]

        return cls(products=prod, categories=cats)

    def get(self, product):
        p = self.products[product.id]
        c = self.categories[product.category.id]
        eit = p["eit"] + c["eit"]
        dif = p["dif"] + c["dif"]
        return _ConditionsCount(dif=dif, eit=eit)


class ConditionController(object):
    ''' Base class for testing conditions that activate Flag
    or Discount objects. '''

    def __init__(self, condition):
        self.condition = condition

    @staticmethod
    def _controllers():
        return {
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

    @staticmethod
    def for_type(cls):
        return ConditionController._controllers()[cls]

    @staticmethod
    def for_condition(condition):
        try:
            return ConditionController.for_type(type(condition))(condition)
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

        if products:
            # Simplify the query.
            all_conditions = cls._filtered_flags(user, products)
        else:
            all_conditions = []

        # All disable-if-false conditions on a product need to be met
        do_not_disable = defaultdict(lambda: True)
        # At least one enable-if-true condition on a product must be met
        do_enable = defaultdict(lambda: False)
        # (if either sort of condition is present)

        # Count the number of conditions for a product
        dif_count = defaultdict(int)
        eit_count = defaultdict(int)

        messages = {}

        for condition in all_conditions:
            cond = cls.for_condition(condition)
            remainder = cond.user_quantity_remaining(user, filtered=True)

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
                    dif_count[product] += 1
                else:
                    do_enable[product] |= met
                    eit_count[product] += 1

                if not met and product not in messages:
                    messages[product] = message

        total_flags = FlagCounter.count()

        valid = {}

        # the problem is that now, not every condition falls into
        # do_not_disable or do_enable '''
        # You should look into this, chris :)

        for product in products:
            if quantities:
                if quantities[product] == 0:
                    continue

            f = total_flags.get(product)
            if f.dif > 0 and f.dif != dif_count[product]:
                do_not_disable[product] = False
                if product not in messages:
                    messages[product] = "Some disable-if-false " \
                                        "conditions were not met"
            if f.eit > 0 and product not in do_enable:
                do_enable[product] = False
                if product not in messages:
                    messages[product] = "Some enable-if-true " \
                                        "conditions were not met"

        for product in itertools.chain(do_not_disable, do_enable):
            f = total_flags.get(product)
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

    @classmethod
    def _filtered_flags(cls, user, products):
        '''

        Returns:
            Sequence[flagbase]: All flags that passed the filter function.

        '''

        types = list(ConditionController._controllers())
        flagtypes = [i for i in types if issubclass(i, conditions.FlagBase)]

        # Get all flags for the products and categories.
        prods = (
            product.flagbase_set.all()
            for product in products
        )
        cats = (
            category.flagbase_set.all()
            for category in set(product.category for product in products)
        )
        all_flags = reduce(operator.or_, itertools.chain(prods, cats))

        all_subsets = []

        for flagtype in flagtypes:
            flags = flagtype.objects.filter(id__in=all_flags)
            ctrl = ConditionController.for_type(flagtype)
            flags = ctrl.pre_filter(flags, user)
            all_subsets.append(flags)

        return itertools.chain(*all_subsets)

    @classmethod
    def pre_filter(cls, queryset, user):
        ''' Returns only the flag conditions that might be available for this
        user. It should hopefully reduce the number of queries that need to be
        executed to determine if a flag is met.

        If this filtration implements the same query as is_met, then you should
        be able to implement ``is_met()`` in terms of this.

        Arguments:

            queryset (Queryset[c]): The canditate conditions.

            user (User): The user for whom we're testing these conditions.

        Returns:
            Queryset[c]: A subset of the conditions that pass the pre-filter
                test for this user.

        '''

        # Default implementation does NOTHING.
        return queryset

    def passes_filter(self, user):
        ''' Returns true if the condition passes the filter '''

        cls = type(self.condition)
        qs = cls.objects.filter(pk=self.condition.id)
        return self.condition in self.pre_filter(qs, user)

    def user_quantity_remaining(self, user, filtered=False):
        ''' Returns the number of items covered by this flag condition the
        user can add to the current cart. This default implementation returns
        a big number if is_met() is true, otherwise 0.

        Either this method, or is_met() must be overridden in subclasses.
        '''

        return _BIG_QUANTITY if self.is_met(user, filtered) else 0

    def is_met(self, user, filtered=False):
        ''' Returns True if this flag condition is met, otherwise returns
        False.

        Either this method, or user_quantity_remaining() must be overridden
        in subclasses.

        Arguments:

            user (User): The user for whom this test must be met.

            filter (bool): If true, this condition was part of a queryset
                returned by pre_filter() for this user.

        '''
        return self.user_quantity_remaining(user, filtered) > 0


class IsMetByFilter(object):

    def is_met(self, user, filtered=False):
        ''' Returns True if this flag condition is met, otherwise returns
        False. It determines if the condition is met by calling pre_filter
        with a queryset containing only self.condition. '''

        if filtered:
            return True  # Why query again?

        return self.passes_filter(user)

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

class RemainderSetByFilter(object):

    def user_quantity_remaining(self, user, filtered=True):
        ''' returns 0 if the date range is violated, otherwise, it will return
        the quantity remaining under the stock limit.

        The filter for this condition must add an annotation called "remainder"
        in order for this to work.
        '''

        if filtered:
            if hasattr(self.condition, "remainder"):
                return self.condition.remainder



        # Mark self.condition with a remainder
        qs = type(self.condition).objects.filter(pk=self.condition.id)
        qs = self.pre_filter(qs, user)

        if len(qs) > 0:
            return qs[0].remainder
        else:
            return 0


class CategoryConditionController(IsMetByFilter, ConditionController):

    @classmethod
    def pre_filter(self, queryset, user):
        ''' Returns all of the items from queryset where the user has a
        product from a category invoking that item's condition in one of their
        carts. '''

        items = commerce.ProductItem.objects.filter(cart__user=user)
        items = items.exclude(cart__status=commerce.Cart.STATUS_RELEASED)
        items = items.select_related("product", "product__category")
        categories = [item.product.category for item in items]

        return queryset.filter(enabling_category__in=categories)


class ProductConditionController(IsMetByFilter, ConditionController):
    ''' Condition tests for ProductFlag and
    IncludedProductDiscount. '''

    @classmethod
    def pre_filter(self, queryset, user):
        ''' Returns all of the items from queryset where the user has a
        product invoking that item's condition in one of their carts. '''

        items = commerce.ProductItem.objects.filter(cart__user=user)
        items = items.exclude(cart__status=commerce.Cart.STATUS_RELEASED)
        items = items.select_related("product", "product__category")
        products = [item.product for item in items]

        return queryset.filter(enabling_products__in=products)


class TimeOrStockLimitConditionController(
        RemainderSetByFilter,
        ConditionController,
    ):
    ''' Common condition tests for TimeOrStockLimit Flag and
    Discount.'''

    @classmethod
    def pre_filter(self, queryset, user):
        ''' Returns all of the items from queryset where the date falls into
        any specified range, but not yet where the stock limit is not yet
        reached.'''

        now = timezone.now()

        # Keep items with no start time, or start time not yet met.
        queryset = queryset.filter(Q(start_time=None) | Q(start_time__lte=now))
        queryset = queryset.filter(Q(end_time=None) | Q(end_time__gte=now))

        # Filter out items that have been reserved beyond the limits
        quantity_or_zero = self._calculate_quantities(user)

        remainder = Case(
            When(limit=None, then=Value(_BIG_QUANTITY)),
            default=F("limit") - Sum(quantity_or_zero),
        )

        queryset = queryset.annotate(remainder=remainder)
        queryset = queryset.filter(remainder__gt=0)

        return queryset

    @classmethod
    def _relevant_carts(cls, user):
        reserved_carts = commerce.Cart.reserved_carts()
        reserved_carts = reserved_carts.exclude(
            user=user,
            status=commerce.Cart.STATUS_ACTIVE,
        )
        return reserved_carts


class TimeOrStockLimitFlagController(
        TimeOrStockLimitConditionController):

    @classmethod
    def _calculate_quantities(cls, user):
        reserved_carts = cls._relevant_carts(user)

        # Calculate category lines
        cat_items = F('categories__product__productitem__product__category')
        reserved_category_products = (
            Q(categories=cat_items) &
            Q(categories__product__productitem__cart__in=reserved_carts)
        )

        # Calculate product lines
        reserved_products = (
            Q(products=F('products__productitem__product')) &
            Q(products__productitem__cart__in=reserved_carts)
        )

        category_quantity_in_reserved_carts = When(
            reserved_category_products,
            then="categories__product__productitem__quantity",
        )

        product_quantity_in_reserved_carts = When(
            reserved_products,
            then="products__productitem__quantity",
        )

        quantity_or_zero = Case(
            category_quantity_in_reserved_carts,
            product_quantity_in_reserved_carts,
            default=Value(0),
        )

        return quantity_or_zero


class TimeOrStockLimitDiscountController(TimeOrStockLimitConditionController):

    @classmethod
    def _calculate_quantities(cls, user):
        reserved_carts = cls._relevant_carts(user)

        quantity_in_reserved_carts = When(
            discountitem__cart__in=reserved_carts,
            then="discountitem__quantity"
        )

        quantity_or_zero = Case(
            quantity_in_reserved_carts,
            default=Value(0)
        )

        return quantity_or_zero


class VoucherConditionController(IsMetByFilter, ConditionController):
    ''' Condition test for VoucherFlag and VoucherDiscount.'''

    @classmethod
    def pre_filter(self, queryset, user):
        ''' Returns all of the items from queryset where the user has entered
        a voucher that invokes that item's condition in one of their carts. '''

        carts = commerce.Cart.objects.filter(
            user=user,
        )
        vouchers = [cart.vouchers.all() for cart in carts]

        return queryset.filter(voucher__in=itertools.chain(*vouchers))
