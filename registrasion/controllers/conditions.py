from django.db.models import Case
from django.db.models import F, Q
from django.db.models import Sum
from django.db.models import Value
from django.db.models import When
from django.utils import timezone

from registrasion.models import commerce
from registrasion.models import conditions


_BIG_QUANTITY = 99999999  # A big quantity


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
            conditions.SpeakerFlag: SpeakerConditionController,
            conditions.SpeakerDiscount: SpeakerConditionController,
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

        in_user_carts = Q(
            enabling_category__product__productitem__cart__user=user
        )
        released = commerce.Cart.STATUS_RELEASED
        in_released_carts = Q(
            enabling_category__product__productitem__cart__status=released
        )
        queryset = queryset.filter(in_user_carts)
        queryset = queryset.exclude(in_released_carts)

        return queryset


class ProductConditionController(IsMetByFilter, ConditionController):
    ''' Condition tests for ProductFlag and
    IncludedProductDiscount. '''

    @classmethod
    def pre_filter(self, queryset, user):
        ''' Returns all of the items from queryset where the user has a
        product invoking that item's condition in one of their carts. '''

        in_user_carts = Q(enabling_products__productitem__cart__user=user)
        released = commerce.Cart.STATUS_RELEASED
        paid = commerce.Cart.STATUS_PAID
        active = commerce.Cart.STATUS_ACTIVE
        in_released_carts = Q(
            enabling_products__productitem__cart__status=released
        )
        not_in_paid_or_active_carts = ~(
            Q(enabling_products__productitem__cart__status=paid) |
            Q(enabling_products__productitem__cart__status=active)
        )

        queryset = queryset.filter(in_user_carts)
        queryset = queryset.exclude(
            in_released_carts & not_in_paid_or_active_carts
        )

        return queryset


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
        item_cats = F('categories__product__productitem__product__category')
        reserved_category_products = (
            Q(categories=item_cats) &
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

        return queryset.filter(voucher__cart__user=user)


class SpeakerConditionController(IsMetByFilter, ConditionController):

    @classmethod
    def pre_filter(self, queryset, user):
        ''' Returns all of the items from queryset which are enabled by a user
        being a presenter or copresenter of a proposal. '''

        u = user
        # User is a presenter
        user_is_presenter = Q(
            is_presenter=True,
            proposal_kind__proposalbase__presentation__speaker__user=u,
        )
        # User is a copresenter
        user_is_copresenter = Q(
            is_copresenter=True,
            proposal_kind__proposalbase__presentation__additional_speakers__user=u,
        )

        return queryset.filter(user_is_presenter | user_is_copresenter)
