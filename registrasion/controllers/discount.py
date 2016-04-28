import itertools

from conditions import ConditionController
from registrasion.models import commerce
from registrasion.models import conditions

from django.db.models import Case
from django.db.models import Q
from django.db.models import Sum
from django.db.models import Value
from django.db.models import When


class DiscountAndQuantity(object):
    ''' Represents a discount that can be applied to a product or category
    for a given user.

    Attributes:

        discount (conditions.DiscountBase): The discount object that the
            clause arises from. A given DiscountBase can apply to multiple
            clauses.

        clause (conditions.DiscountForProduct|conditions.DiscountForCategory):
            A clause describing which product or category this discount item
            applies to. This casts to ``str()`` to produce a human-readable
            version of the clause.

        quantity (int): The number of times this discount item can be applied
            for the given user.

    '''

    def __init__(self, discount, clause, quantity):
        self.discount = discount
        self.clause = clause
        self.quantity = quantity

    def __repr__(self):
        return "(discount=%s, clause=%s, quantity=%d)" % (
            self.discount, self.clause, self.quantity,
        )


class DiscountController(object):

    @classmethod
    def available_discounts(cls, user, categories, products):
        ''' Returns all discounts available to this user for the given categories
        and products. The discounts also list the available quantity for this user,
        not including products that are pending purchase. '''


        filtered_clauses = cls._filtered_discounts(user, categories, products)

        discounts = []

        # Markers so that we don't need to evaluate given conditions more than once
        accepted_discounts = set()
        failed_discounts = set()

        for clause in filtered_clauses:
            discount = clause.discount
            cond = ConditionController.for_condition(discount)

            past_use_count = discount.past_use_count


            if past_use_count >= clause.quantity:
                # This clause has exceeded its use count
                pass
            elif discount not in failed_discounts:
                # This clause is still available
                if discount in accepted_discounts or cond.is_met(user, filtered=True):
                    # This clause is valid for this user
                    discounts.append(DiscountAndQuantity(
                        discount=discount,
                        clause=clause,
                        quantity=clause.quantity - past_use_count,
                    ))
                    accepted_discounts.add(discount)
                else:
                    # This clause is not valid for this user
                    failed_discounts.add(discount)
        return discounts

    @classmethod
    def _filtered_discounts(cls, user, categories, products):
        '''

        Returns:
            Sequence[discountbase]: All discounts that passed the filter function.

        '''

        types = list(ConditionController._controllers())
        discounttypes = [i for i in types if issubclass(i, conditions.DiscountBase)]

        # discounts that match provided categories
        category_discounts = conditions.DiscountForCategory.objects.filter(
            category__in=categories
        )
        # discounts that match provided products
        product_discounts = conditions.DiscountForProduct.objects.filter(
            product__in=products
        )
        # discounts that match categories for provided products
        product_category_discounts = conditions.DiscountForCategory.objects.filter(
            category__in=(product.category for product in products)
        )
        # (Not relevant: discounts that match products in provided categories)

        product_discounts = product_discounts.select_related(
            "product",
            "product__category",
        )

        all_category_discounts = category_discounts | product_category_discounts
        all_category_discounts = all_category_discounts.select_related(
            "category",
        )

        valid_discounts = conditions.DiscountBase.objects.filter(
            Q(discountforproduct__in=product_discounts) |
            Q(discountforcategory__in=all_category_discounts)
        )

        all_subsets = []

        for discounttype in discounttypes:
            discounts = discounttype.objects.filter(id__in=valid_discounts)
            ctrl = ConditionController.for_type(discounttype)
            discounts = ctrl.pre_filter(discounts, user)
            discounts = cls._annotate_with_past_uses(discounts, user)
            all_subsets.append(discounts)

        filtered_discounts = list(itertools.chain(*all_subsets))

        # Map from discount key to itself (contains annotations added by filter)
        from_filter = dict((i.id, i) for i in filtered_discounts)

        # The set of all potential discounts
        discount_clauses = set(itertools.chain(
            product_discounts.filter(discount__in=filtered_discounts),
            all_category_discounts.filter(discount__in=filtered_discounts),
        ))

        # Replace discounts with the filtered ones
        # These are the correct subclasses (saves query later on), and have
        # correct annotations from filters if necessary.
        for clause in discount_clauses:
            clause.discount = from_filter[clause.discount.id]

        return discount_clauses

    @classmethod
    def _annotate_with_past_uses(cls, queryset, user):
        ''' Annotates the queryset with a usage count for that discount by the
        given user. '''

        past_use_quantity = When(
            (
                Q(discountitem__cart__user=user) &
                Q(discountitem__cart__status=commerce.Cart.STATUS_PAID)
            ),
            then="discountitem__quantity",
        )

        past_use_quantity_or_zero = Case(
            past_use_quantity,
            default=Value(0),
        )

        queryset = queryset.annotate(past_use_count=Sum(past_use_quantity_or_zero))
        return queryset
