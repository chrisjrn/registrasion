import datetime
import pytz

from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db import transaction

from registrasion.models import conditions
from registrasion.models import inventory
from controller_helpers import TestingCartController
from controller_helpers import TestingInvoiceController

from test_cart import RegistrationCartTestCase

UTC = pytz.timezone('UTC')


class VoucherTestCases(RegistrationCartTestCase):

    def test_apply_voucher(self):
        voucher = self.new_voucher()

        self.set_time(datetime.datetime(2015, 01, 01, tzinfo=UTC))

        cart_1 = TestingCartController.for_user(self.USER_1)
        cart_1.apply_voucher(voucher.code)
        self.assertIn(voucher, cart_1.cart.vouchers.all())

        # Second user should not be able to apply this voucher (it's exhausted)
        cart_2 = TestingCartController.for_user(self.USER_2)
        with self.assertRaises(ValidationError):
            cart_2.apply_voucher(voucher.code)

        # After the reservation duration
        # user 2 should be able to apply voucher
        self.add_timedelta(inventory.Voucher.RESERVATION_DURATION * 2)
        cart_2.apply_voucher(voucher.code)

        cart_2.next_cart()

        # After the reservation duration, even though the voucher has applied,
        # it exceeds the number of vouchers available.
        self.add_timedelta(inventory.Voucher.RESERVATION_DURATION * 2)
        with self.assertRaises(ValidationError):
            cart_1.validate_cart()

    def test_fix_simple_errors_resolves_unavailable_voucher(self):
        self.test_apply_voucher()

        # User has an exhausted voucher leftover from test_apply_voucher
        cart_1 = TestingCartController.for_user(self.USER_1)
        with self.assertRaises(ValidationError):
            cart_1.validate_cart()

        cart_1.fix_simple_errors()
        # This should work now.
        cart_1.validate_cart()

    def test_voucher_enables_item(self):
        voucher = self.new_voucher()

        flag = conditions.VoucherFlag.objects.create(
            description="Voucher condition",
            voucher=voucher,
            condition=conditions.FlagBase.ENABLE_IF_TRUE,
        )
        flag.products.add(self.PROD_1)

        # Adding the product without a voucher will not work
        current_cart = TestingCartController.for_user(self.USER_1)
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_1, 1)

        # Apply the voucher
        current_cart.apply_voucher(voucher.code)
        current_cart.add_to_cart(self.PROD_1, 1)

    def test_voucher_enables_discount(self):
        voucher = self.new_voucher()

        discount = conditions.VoucherDiscount.objects.create(
            description="VOUCHER RECIPIENT",
            voucher=voucher,
        )
        conditions.DiscountForProduct.objects.create(
            discount=discount,
            product=self.PROD_1,
            percentage=Decimal(100),
            quantity=1
        )

        # Having PROD_1 in place should add a discount
        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.apply_voucher(voucher.code)
        current_cart.add_to_cart(self.PROD_1, 1)
        self.assertEqual(1, len(current_cart.cart.discountitem_set.all()))

    @transaction.atomic
    def test_voucher_codes_unique(self):
        self.new_voucher(code="VOUCHER")
        with self.assertRaises(IntegrityError):
            self.new_voucher(code="VOUCHER")

    def test_multiple_vouchers_work(self):
        self.new_voucher(code="VOUCHER1")
        self.new_voucher(code="VOUCHER2")

    def test_vouchers_case_insensitive(self):
        voucher = self.new_voucher(code="VOUCHeR")
        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.apply_voucher(voucher.code.lower())

    def test_voucher_can_only_be_applied_once(self):
        voucher = self.new_voucher(limit=2)
        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.apply_voucher(voucher.code)
        current_cart.apply_voucher(voucher.code)

        # You can apply the code twice, but it will only add to the cart once.
        self.assertEqual(1, current_cart.cart.vouchers.count())

    def test_voucher_can_only_be_applied_once_across_multiple_carts(self):
        voucher = self.new_voucher(limit=2)
        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.apply_voucher(voucher.code)

        current_cart.next_cart()

        current_cart = TestingCartController.for_user(self.USER_1)

        with self.assertRaises(ValidationError):
            current_cart.apply_voucher(voucher.code)

        return current_cart

    def test_refund_releases_used_vouchers(self):
        voucher = self.new_voucher(limit=2)
        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.apply_voucher(voucher.code)
        current_cart.add_to_cart(self.PROD_1, 1)

        inv = TestingInvoiceController.for_cart(current_cart.cart)
        if not inv.invoice.is_paid:
            inv.pay("Hello!", inv.invoice.value)

        current_cart = TestingCartController.for_user(self.USER_1)
        with self.assertRaises(ValidationError):
            current_cart.apply_voucher(voucher.code)

        inv.refund()
        current_cart.apply_voucher(voucher.code)

    def test_fix_simple_errors_does_not_remove_limited_voucher(self):
        voucher = self.new_voucher(code="VOUCHER")
        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.apply_voucher(voucher.code)

        current_cart.fix_simple_errors()
        self.assertEqual(1, current_cart.cart.vouchers.count())
