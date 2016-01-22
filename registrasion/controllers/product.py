import itertools

from collections import namedtuple

from django.db.models import Q
from registrasion import models as rego

from conditions import ConditionController

DiscountEnabler = namedtuple(
    "DiscountEnabler", (
        "discount",
        "condition",
        "value"))


class ProductController(object):

    def __init__(self, product):
        self.product = product

    def user_can_add_within_limit(self, user, quantity):
        ''' Return true if the user is able to add _quantity_ to their count of
        this Product without exceeding _limit_per_user_.'''

        carts = rego.Cart.objects.filter(user=user)
        items = rego.ProductItem.objects.filter(
            product=self.product,
            cart=carts)

        count = 0
        for item in items:
            count += item.quantity

        if quantity + count > self.product.limit_per_user:
            return False
        else:
            return True

    def can_add_with_enabling_conditions(self, user, quantity):
        ''' Returns true if the user is able to add _quantity_ to their count
        of this Product without exceeding the ceilings the product is attached
        to. '''

        conditions = rego.EnablingConditionBase.objects.filter(
            Q(products=self.product) | Q(categories=self.product.category)
        ).select_subclasses()

        mandatory_violated = False
        non_mandatory_met = False

        for condition in conditions:
            cond = ConditionController.for_condition(condition)
            met = cond.is_met(user, quantity)

            if condition.mandatory and not met:
                mandatory_violated = True
                break
            if met:
                non_mandatory_met = True

        if mandatory_violated:
            # All mandatory conditions must be met
            return False

        if len(conditions) > 0 and not non_mandatory_met:
            # If there's any non-mandatory conditions, one must be met
            return False

        return True

    def get_enabler(self, condition):
        if condition.percentage is not None:
            value = condition.percentage * self.product.price
        else:
            value = condition.price
        return DiscountEnabler(
            discount=condition.discount,
            condition=condition,
            value=value
        )

    def available_discounts(self, user):
        ''' Returns the set of available discounts for this user, for this
        product. '''

        product_discounts = rego.DiscountForProduct.objects.filter(
            product=self.product)
        category_discounts = rego.DiscountForCategory.objects.filter(
            category=self.product.category
        )

        potential_discounts = set(itertools.chain(
            (self.get_enabler(i) for i in product_discounts),
            (self.get_enabler(i) for i in category_discounts),
        ))

        discounts = []
        for discount in potential_discounts:
            real_discount = rego.DiscountBase.objects.get_subclass(
                pk=discount.discount.pk)
            cond = ConditionController.for_condition(real_discount)
            if cond.is_met(user, 0):
                discounts.append(discount)

        return discounts
