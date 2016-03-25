from django.db.models import Q
from registrasion import models as rego

from conditions import ConditionController


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
