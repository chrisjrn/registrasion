import datetime
import itertools

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.db.models import Avg, Min, Max, Sum
from django.utils import timezone

from registrasion import models as rego

from conditions import ConditionController
from controllers import ProductController


class CartController(object):

    def __init__(self, cart):
        self.cart = cart

    @staticmethod
    def for_user(user):
        ''' Returns the user's current cart, or creates a new cart
        if there isn't one ready yet. '''

        try:
            existing = rego.Cart.objects.get(user=user, active=True)
        except ObjectDoesNotExist:
            existing = rego.Cart.objects.create(
                user=user,
                time_last_updated=timezone.now(),
                reservation_duration=datetime.timedelta(),
                 )
            existing.save()
        return CartController(existing)


    def extend_reservation(self):
        ''' Updates the cart's time last updated value, which is used to
        determine whether the cart has reserved the items and discounts it
        holds. '''

        reservations = [datetime.timedelta()]

        # If we have vouchers, we're entitled to an hour at minimum.
        if len(self.cart.vouchers.all()) >= 1:
            reservations.append(rego.Voucher.RESERVATION_DURATION)

        # Else, it's the maximum of the included products
        items = rego.ProductItem.objects.filter(cart=self.cart)
        agg = items.aggregate(Max("product__reservation_duration"))
        product_max = agg["product__reservation_duration__max"]

        if product_max is not None:
            reservations.append(product_max)

        self.cart.time_last_updated = timezone.now()
        self.cart.reservation_duration = max(reservations)


    def add_to_cart(self, product, quantity):
        ''' Adds _quantity_ of the given _product_ to the cart. Raises
        ValidationError if constraints are violated.'''

        prod = ProductController(product)

        # TODO: Check enabling conditions for product for user

        if not prod.can_add_with_enabling_conditions(self.cart.user, quantity):
            raise ValidationError("Not enough of that product left (ec)")

        if not prod.user_can_add_within_limit(self.cart.user, quantity):
            raise ValidationError("Not enough of that product left (user)")

        try:
            # Try to update an existing item within this cart if possible.
            product_item = rego.ProductItem.objects.get(
                cart=self.cart,
                product=product)
            product_item.quantity += quantity
        except ObjectDoesNotExist:
            product_item = rego.ProductItem.objects.create(
                cart=self.cart,
                product=product,
                quantity=quantity,
            )
        product_item.save()

        self.recalculate_discounts()

        self.extend_reservation()
        self.cart.revision += 1
        self.cart.save()


    def apply_voucher(self, voucher):
        ''' Applies the given voucher to this cart. '''

        # TODO: is it valid for a cart to re-add a voucher that they have?

        # Is voucher exhausted?
        active_carts = rego.Cart.reserved_carts()
        carts_with_voucher = active_carts.filter(vouchers=voucher)
        if len(carts_with_voucher) >= voucher.limit:
            raise ValidationError("This voucher is no longer available")

        # If successful...
        self.cart.vouchers.add(voucher)

        self.extend_reservation()
        self.cart.revision += 1
        self.cart.save()


    def validate_cart(self):
        ''' Determines whether the status of the current cart is valid;
        this is normally called before generating or paying an invoice '''

        is_reserved = self.cart in rego.Cart.reserved_carts()

        # TODO: validate vouchers

        items = rego.ProductItem.objects.filter(cart=self.cart)
        for item in items:
            # per-user limits are tested at add time, and are unliklely to change
            prod = ProductController(item.product)

            # If the cart is not reserved, we need to see if we can re-reserve
            quantity = 0 if is_reserved else item.quantity

            if not prod.can_add_with_enabling_conditions(self.cart.user, quantity):
                raise ValidationError("Products are no longer available")

        # Validate the discounts
        discount_items = rego.DiscountItem.objects.filter(cart=self.cart)
        seen_discounts = set()

        for discount_item in discount_items:
            discount = discount_item.discount
            if discount in seen_discounts:
                continue
            seen_discounts.add(discount)
            real_discount = rego.DiscountBase.objects.get_subclass(pk=discount.pk)
            cond = ConditionController.for_condition(real_discount)

            quantity = 0 if is_reserved else discount_item.quantity

            if not cond.is_met(self.cart.user, quantity):
                raise ValidationError("Discounts are no longer available")



    def recalculate_discounts(self):
        ''' Calculates all of the discounts available for this product.
        NB should be transactional, and it's terribly inefficient.
        '''

        # Delete the existing entries.
        rego.DiscountItem.objects.filter(cart=self.cart).delete()

        for item in self.cart.productitem_set.all():
            self._add_discount(item.product, item.quantity)


    def _add_discount(self, product, quantity):
        ''' Calculates the best available discounts for this product.
        NB this will be super-inefficient in aggregate because discounts will be
        re-tested for each product. We should work on that.'''

        prod = ProductController(product)
        discounts = prod.available_discounts(self.cart.user)
        discounts.sort(key=lambda discount: discount.value)

        for discount in reversed(discounts):
            if quantity == 0:
                break

            # Get the count of past uses of this discount condition
            # as this affects the total amount we're allowed to use now.
            past_uses = rego.DiscountItem.objects.filter(
                cart__active=False,
                discount=discount.discount,
                product=product,
            )
            agg = past_uses.aggregate(Sum("quantity"))
            past_uses = agg["quantity__sum"]
            if past_uses is None:
                past_uses = 0
            if past_uses == discount.condition.quantity:
                continue

            # Get a provisional instance for this DiscountItem
            # with the quantity set to as much as we have in the cart
            discount_item = rego.DiscountItem.objects.create(
                product=product,
                cart=self.cart,
                discount=discount.discount,
                quantity=quantity,
            )

            # Truncate the quantity for this DiscountItem if we exceed quantity
            ours = discount_item.quantity
            allowed = discount.condition.quantity - past_uses
            if ours > allowed:
                discount_item.quantity = allowed
                # Update the remaining quantity.
                quantity = ours - allowed
            else:
                quantity = 0
                
            discount_item.save()
