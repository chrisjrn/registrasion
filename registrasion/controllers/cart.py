import collections
import datetime
import discount
import itertools

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from registrasion import models as rego

from category import CategoryController
from conditions import ConditionController
from product import ProductController


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

    def end_batch(self):
        ''' Performs operations that occur occur at the end of a batch of
        product changes/voucher applications etc.
        THIS SHOULD BE PRIVATE
        '''

        self.recalculate_discounts()

        self.extend_reservation()
        self.cart.revision += 1
        self.cart.save()


    @transaction.atomic
    def set_quantities(self, product_quantities):
        ''' Sets the quantities on each of the products on each of the
        products specified. Raises an exception (ValidationError) if a limit
        is violated. `product_quantities` is an iterable of (product, quantity)
        pairs. '''

        items_in_cart = rego.ProductItem.objects.filter(cart=self.cart)
        product_quantities = list(product_quantities)

        # n.b need to add have the existing items first so that the new
        # items override the old ones.
        all_product_quantities = dict(itertools.chain(
            ((i.product, i.quantity) for i in items_in_cart.all()),
            product_quantities,
        )).items()

        # Validate that the limits we're adding are OK
        self._test_limits(all_product_quantities)

        for product, quantity in product_quantities:
            try:
                product_item = rego.ProductItem.objects.get(
                    cart=self.cart,
                    product=product,
                )
                product_item.quantity = quantity
                product_item.save()
            except ObjectDoesNotExist:
                rego.ProductItem.objects.create(
                    cart=self.cart,
                    product=product,
                    quantity=quantity,
                )

        items_in_cart.filter(quantity=0).delete()

        self.end_batch()

    def _test_limits(self, product_quantities):
        ''' Tests that the quantity changes we intend to make do not violate
        the limits and enabling conditions imposed on the products. '''

        # Test each product limit here
        for product, quantity in product_quantities:
            if quantity < 0:
                # TODO: batch errors
                raise ValidationError("Value must be zero or greater.")

            prod = ProductController(product)
            limit = prod.user_quantity_remaining(self.cart.user)

            if quantity > limit:
                # TODO: batch errors
                raise ValidationError(
                    "You may only have %d of product: %s" % (
                        limit, product.name,
                    )
                )

        # Collect by category
        by_cat = collections.defaultdict(list)
        for product, quantity in product_quantities:
            by_cat[product.category].append((product, quantity))

        # Test each category limit here
        for cat in by_cat:
            ctrl = CategoryController(cat)
            limit = ctrl.user_quantity_remaining(self.cart.user)

            # Get the amount so far in the cart
            to_add = sum(i[1] for i in by_cat[cat])

            if to_add > limit:
                # TODO: batch errors
                raise ValidationError(
                    "You may only have %d items in category: %s" % (
                        limit, cat.name,
                    )
                )

        # Test the enabling conditions
        errs = ConditionController.test_enabling_conditions(
            self.cart.user,
            product_quantities=product_quantities,
        )

        if errs:
            # TODO: batch errors
            raise ValidationError("An enabling condition failed")

    def set_quantity(self, product, quantity, batched=False):
        ''' Sets the _quantity_ of the given _product_ in the cart to the given
        _quantity_. '''

        self.set_quantities(((product, quantity),))

    def add_to_cart(self, product, quantity):
        ''' Adds _quantity_ of the given _product_ to the cart. Raises
        ValidationError if constraints are violated.'''

        try:
            product_item = rego.ProductItem.objects.get(
                cart=self.cart,
                product=product)
            old_quantity = product_item.quantity
        except ObjectDoesNotExist:
            old_quantity = 0
        self.set_quantity(product, old_quantity + quantity)

    def apply_voucher(self, voucher_code):
        ''' Applies the voucher with the given code to this cart. '''

        # Is voucher exhausted?
        active_carts = rego.Cart.reserved_carts()

        # Try and find the voucher
        voucher = rego.Voucher.objects.get(code=voucher_code.upper())

        # It's invalid for a user to enter a voucher that's exhausted
        carts_with_voucher = active_carts.filter(vouchers=voucher)
        if len(carts_with_voucher) >= voucher.limit:
            raise ValidationError("This voucher is no longer available")

        # It's not valid for users to re-enter a voucher they already have
        user_carts_with_voucher = rego.Cart.objects.filter(
            user=self.cart.user,
            released=False,
            vouchers=voucher,
        )
        if len(user_carts_with_voucher) > 0:
            raise ValidationError("You have already entered this voucher.")

        # If successful...
        self.cart.vouchers.add(voucher)
        self.end_batch()

    def validate_cart(self):
        ''' Determines whether the status of the current cart is valid;
        this is normally called before generating or paying an invoice '''

        is_reserved = self.cart in rego.Cart.reserved_carts()

        # TODO: validate vouchers

        items = rego.ProductItem.objects.filter(cart=self.cart)

        product_quantities = list((i.product, i.quantity) for i in items)
        self._test_limits(product_quantities)

        # Validate the discounts
        discount_items = rego.DiscountItem.objects.filter(cart=self.cart)
        seen_discounts = set()

        for discount_item in discount_items:
            discount = discount_item.discount
            if discount in seen_discounts:
                continue
            seen_discounts.add(discount)
            real_discount = rego.DiscountBase.objects.get_subclass(
                pk=discount.pk)
            cond = ConditionController.for_condition(real_discount)

            if not cond.is_met(self.cart.user):
                raise ValidationError("Discounts are no longer available")

    def recalculate_discounts(self):
        ''' Calculates all of the discounts available for this product.
        NB should be transactional, and it's terribly inefficient.
        '''

        # Delete the existing entries.
        rego.DiscountItem.objects.filter(cart=self.cart).delete()

        product_items = self.cart.productitem_set.all()

        products = [i.product for i in product_items]
        discounts = discount.available_discounts(self.cart.user, [], products)

        # The highest-value discounts will apply to the highest-value
        # products first.
        product_items = self.cart.productitem_set.all()
        product_items = product_items.order_by('product__price')
        product_items = reversed(product_items)
        for item in product_items:
            self._add_discount(item.product, item.quantity, discounts)

    def _add_discount(self, product, quantity, discounts):
        ''' Applies the best discounts on the given product, from the given
        discounts.'''

        def matches(discount):
            ''' Returns True if and only if the given discount apples to
            our product. '''
            if isinstance(discount.clause, rego.DiscountForCategory):
                return discount.clause.category == product.category
            else:
                return discount.clause.product == product

        def value(discount):
            ''' Returns the value of this discount clause
            as applied to this product '''
            if discount.clause.percentage is not None:
                return discount.clause.percentage * product.price
            else:
                return discount.clause.price

        discounts = [i for i in discounts if matches(i)]
        discounts.sort(key=value)

        for candidate in reversed(discounts):
            if quantity == 0:
                break
            elif candidate.quantity == 0:
                # This discount clause has been exhausted by this cart
                continue

            # Get a provisional instance for this DiscountItem
            # with the quantity set to as much as we have in the cart
            discount_item = rego.DiscountItem.objects.create(
                product=product,
                cart=self.cart,
                discount=candidate.discount,
                quantity=quantity,
            )

            # Truncate the quantity for this DiscountItem if we exceed quantity
            ours = discount_item.quantity
            allowed = candidate.quantity
            if ours > allowed:
                discount_item.quantity = allowed
                # Update the remaining quantity.
                quantity = ours - allowed
            else:
                quantity = 0

            candidate.quantity -= discount_item.quantity

            discount_item.save()
