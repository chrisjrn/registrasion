from .batch import BatchController
from .category import CategoryController
from .discount import DiscountController
from .flag import FlagController
from .product import ProductController

import collections
import datetime
import functools
import itertools

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.db.models import Q
from django.utils import timezone

from registrasion.exceptions import CartValidationError
from registrasion.models import commerce
from registrasion.models import conditions
from registrasion.models import inventory


def _modifies_cart(func):
    ''' Decorator that makes the wrapped function raise ValidationError
    if we're doing something that could modify the cart.

    It also wraps the execution of this function in a database transaction,
    and marks the boundaries of a cart operations batch.
    '''

    @functools.wraps(func)
    def inner(self, *a, **k):
        self._fail_if_cart_is_not_active()
        with transaction.atomic():
            with BatchController.batch(self.cart.user):
                # Mark the version of self in the batch cache as modified
                memoised = self.for_user(self.cart.user)
                memoised._modified_by_batch = True
                return func(self, *a, **k)
    return inner


class CartController(object):

    def __init__(self, cart):
        self.cart = cart

    @classmethod
    @BatchController.memoise
    def for_user(cls, user):
        ''' Returns the user's current cart, or creates a new cart
        if there isn't one ready yet. '''

        try:
            existing = commerce.Cart.objects.get(
                user=user,
                status=commerce.Cart.STATUS_ACTIVE,
            )
        except ObjectDoesNotExist:
            existing = commerce.Cart.objects.create(
                user=user,
                time_last_updated=timezone.now(),
                reservation_duration=datetime.timedelta(),
            )
        return cls(existing)

    def _fail_if_cart_is_not_active(self):
        self.cart.refresh_from_db()
        if self.cart.status != commerce.Cart.STATUS_ACTIVE:
            raise ValidationError("You can only amend active carts.")

    def _autoextend_reservation(self):
        ''' Updates the cart's time last updated value, which is used to
        determine whether the cart has reserved the items and discounts it
        holds. '''

        time = timezone.now()

        # Calculate the residual of the _old_ reservation duration
        # if it's greater than what's in the cart now, keep it.
        time_elapsed_since_updated = (time - self.cart.time_last_updated)
        residual = self.cart.reservation_duration - time_elapsed_since_updated

        reservations = [datetime.timedelta(0), residual]

        # If we have vouchers, we're entitled to an hour at minimum.
        if len(self.cart.vouchers.all()) >= 1:
            reservations.append(inventory.Voucher.RESERVATION_DURATION)

        # Else, it's the maximum of the included products
        items = commerce.ProductItem.objects.filter(cart=self.cart)
        agg = items.aggregate(Max("product__reservation_duration"))
        product_max = agg["product__reservation_duration__max"]

        if product_max is not None:
            reservations.append(product_max)

        self.cart.time_last_updated = time
        self.cart.reservation_duration = max(reservations)

    def end_batch(self):
        ''' Calls ``_end_batch`` if a modification has been performed in the
        previous batch. '''
        if hasattr(self, '_modified_by_batch'):
            self._end_batch()

    def _end_batch(self):
        ''' Performs operations that occur occur at the end of a batch of
        product changes/voucher applications etc.

        You need to call this after you've finished modifying the user's cart.
        This is normally done by wrapping a block of code using
        ``operations_batch``.

        '''

        self.cart.refresh_from_db()

        self._recalculate_discounts()

        self._autoextend_reservation()
        self.cart.revision += 1
        self.cart.save()

    def extend_reservation(self, timedelta):
        ''' Extends the reservation on this cart by the given timedelta.
        This can only be done if the current state of the cart is valid (i.e
        all items and discounts in the cart are still available.)

        Arguments:
            timedelta (timedelta): The amount of time to extend the cart by.
                The resulting reservation_duration will be now() + timedelta,
                unless the requested extension is *LESS* than the current
                reservation deadline.

        '''

        self.validate_cart()
        cart = self.cart
        cart.refresh_from_db()

        elapsed = (timezone.now() - cart.time_last_updated)

        if cart.reservation_duration - elapsed > timedelta:
            return

        cart.time_last_updated = timezone.now()
        cart.reservation_duration = timedelta
        cart.save()

    @_modifies_cart
    def set_quantities(self, product_quantities):
        ''' Sets the quantities on each of the products on each of the
        products specified. Raises an exception (ValidationError) if a limit
        is violated. `product_quantities` is an iterable of (product, quantity)
        pairs. '''

        items_in_cart = commerce.ProductItem.objects.filter(cart=self.cart)
        items_in_cart = items_in_cart.select_related(
            "product",
            "product__category",
        )

        product_quantities = list(product_quantities)

        # n.b need to add have the existing items first so that the new
        # items override the old ones.
        all_product_quantities = dict(itertools.chain(
            ((i.product, i.quantity) for i in items_in_cart.all()),
            product_quantities,
        )).items()

        # Validate that the limits we're adding are OK
        products = set(product for product, q in product_quantities)
        try:
            self._test_limits(all_product_quantities)
        except CartValidationError as ve:
            # Only raise errors for products that we're explicitly
            # Manipulating here.
            for ve_field in ve.error_list:
                product, message = ve_field.message
                if product in products:
                    raise ve

        new_items = []
        products = []
        for product, quantity in product_quantities:
            products.append(product)

            if quantity == 0:
                continue

            item = commerce.ProductItem(
                cart=self.cart,
                product=product,
                quantity=quantity,
            )
            new_items.append(item)

        to_delete = (
            Q(quantity=0) |
            Q(product__in=products)
        )

        items_in_cart.filter(to_delete).delete()
        commerce.ProductItem.objects.bulk_create(new_items)

    def _test_limits(self, product_quantities):
        ''' Tests that the quantity changes we intend to make do not violate
        the limits and flag conditions imposed on the products. '''

        errors = []

        # Pre-annotate products
        remainders = ProductController.user_remainders(self.cart.user)

        # Test each product limit here
        for product, quantity in product_quantities:
            if quantity < 0:
                errors.append((product, "Value must be zero or greater."))

            limit = remainders[product.id]

            if quantity > limit:
                errors.append((
                    product,
                    "You may only have %d of product: %s" % (
                        limit, product,
                    )
                ))

        # Collect by category
        by_cat = collections.defaultdict(list)
        for product, quantity in product_quantities:
            by_cat[product.category].append((product, quantity))

        # Pre-annotate categories
        remainders = CategoryController.user_remainders(self.cart.user)

        # Test each category limit here
        for category in by_cat:
            limit = remainders[category.id]

            # Get the amount so far in the cart
            to_add = sum(i[1] for i in by_cat[category])

            if to_add > limit:
                message_base = "You may only add %d items from category: %s"
                message = message_base % (
                    limit, category.name,
                )
                for product, quantity in by_cat[category]:
                    errors.append((product, message))

        # Test the flag conditions
        errs = FlagController.test_flags(
            self.cart.user,
            product_quantities=product_quantities,
        )

        if errs:
            for error in errs:
                errors.append(error)

        if errors:
            raise CartValidationError(errors)

    @_modifies_cart
    def apply_voucher(self, voucher_code):
        ''' Applies the voucher with the given code to this cart. '''

        # Try and find the voucher
        voucher = inventory.Voucher.objects.get(code=voucher_code.upper())

        # Re-applying vouchers should be idempotent
        if voucher in self.cart.vouchers.all():
            return

        self._test_voucher(voucher)

        # If successful...
        self.cart.vouchers.add(voucher)

    def _test_voucher(self, voucher):
        ''' Tests whether this voucher is allowed to be applied to this cart.
        Raises ValidationError if not. '''

        # Is voucher exhausted?
        active_carts = commerce.Cart.reserved_carts()

        # It's invalid for a user to enter a voucher that's exhausted
        carts_with_voucher = active_carts.filter(vouchers=voucher)
        carts_with_voucher = carts_with_voucher.exclude(pk=self.cart.id)
        if carts_with_voucher.count() >= voucher.limit:
            raise ValidationError(
                "Voucher %s is no longer available" % voucher.code)

        # It's not valid for users to re-enter a voucher they already have
        user_carts_with_voucher = carts_with_voucher.filter(
            user=self.cart.user,
        )

        if user_carts_with_voucher.count() > 0:
            raise ValidationError("You have already entered this voucher.")

    def _test_vouchers(self, vouchers):
        ''' Tests each of the vouchers against self._test_voucher() and raises
        the collective ValidationError.
        Future work will refactor _test_voucher in terms of this, and save some
        queries. '''
        errors = []
        for voucher in vouchers:
            try:
                self._test_voucher(voucher)
            except ValidationError as ve:
                errors.append(ve)

        if errors:
            raise(ValidationError(errors))

    def _test_required_categories(self):
        ''' Makes sure that the owner of this cart has satisfied all of the
        required category constraints in the inventory (be it in this cart
        or others). '''

        required = set(inventory.Category.objects.filter(required=True))

        items = commerce.ProductItem.objects.filter(
            product__category__required=True,
            cart__user=self.cart.user,
        ).exclude(
            cart__status=commerce.Cart.STATUS_RELEASED,
        )

        for item in items:
            required.remove(item.product.category)

        errors = []
        for category in required:
            msg = "You must have at least one item from: %s" % category
            errors.append((None, msg))

        if errors:
            raise ValidationError(errors)

    def _append_errors(self, errors, ve):
        for error in ve.error_list:
            errors.append(error.message[1])

    def validate_cart(self):
        ''' Determines whether the status of the current cart is valid;
        this is normally called before generating or paying an invoice '''

        cart = self.cart
        user = self.cart.user
        errors = []

        try:
            self._test_vouchers(self.cart.vouchers.all())
        except ValidationError as ve:
            errors.append(ve)

        items = commerce.ProductItem.objects.filter(cart=cart)
        items = items.select_related("product", "product__category")

        product_quantities = list((i.product, i.quantity) for i in items)
        try:
            self._test_limits(product_quantities)
        except ValidationError as ve:
            self._append_errors(errors, ve)

        try:
            self._test_required_categories()
        except ValidationError as ve:
            self._append_errors(errors, ve)

        # Validate the discounts
        # TODO: refactor in terms of available_discounts
        # why aren't we doing that here?!

        #     def available_discounts(cls, user, categories, products):

        products = [i.product for i in items]
        discounts_with_quantity = DiscountController.available_discounts(
            user,
            [],
            products,
        )
        discounts = set(i.discount.id for i in discounts_with_quantity)

        discount_items = commerce.DiscountItem.objects.filter(cart=cart)
        for discount_item in discount_items:
            discount = discount_item.discount

            if discount.id not in discounts:
                errors.append(
                    ValidationError("Discounts are no longer available")
                )

        if errors:
            raise ValidationError(errors)

    @_modifies_cart
    def fix_simple_errors(self):
        ''' This attempts to fix the easy errors raised by ValidationError.
        This includes removing items from the cart that are no longer
        available, recalculating all of the discounts, and removing voucher
        codes that are no longer available. '''

        # Fix vouchers first (this affects available discounts)
        to_remove = []
        for voucher in self.cart.vouchers.all():
            try:
                self._test_voucher(voucher)
            except ValidationError:
                to_remove.append(voucher)

        for voucher in to_remove:
            self.cart.vouchers.remove(voucher)

        # Fix products and discounts
        items = commerce.ProductItem.objects.filter(cart=self.cart)
        items = items.select_related("product")
        products = set(i.product for i in items)
        available = set(ProductController.available_products(
            self.cart.user,
            products=products,
        ))

        not_available = products - available
        zeros = [(product, 0) for product in not_available]

        self.set_quantities(zeros)

    @transaction.atomic
    def _recalculate_discounts(self):
        ''' Calculates all of the discounts available for this product.'''

        # Delete the existing entries.
        commerce.DiscountItem.objects.filter(cart=self.cart).delete()

        # Order the products such that the most expensive ones are
        # processed first.
        product_items = self.cart.productitem_set.all().select_related(
            "product", "product__category"
        ).order_by("-product__price")

        products = [i.product for i in product_items]
        discounts = DiscountController.available_discounts(
            self.cart.user,
            [],
            products,
        )

        # The highest-value discounts will apply to the highest-value
        # products first, because of the order_by clause
        for item in product_items:
            self._add_discount(item.product, item.quantity, discounts)

    def _add_discount(self, product, quantity, discounts):
        ''' Applies the best discounts on the given product, from the given
        discounts.'''

        def matches(discount):
            ''' Returns True if and only if the given discount apples to
            our product. '''
            if isinstance(discount.clause, conditions.DiscountForCategory):
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
            discount_item = commerce.DiscountItem.objects.create(
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
                discount_item.save()
                # Update the remaining quantity.
                quantity = ours - allowed
            else:
                quantity = 0

            candidate.quantity -= discount_item.quantity
