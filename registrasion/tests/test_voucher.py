import datetime
import pytz

from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from registrasion import models as rego
from cart_controller_helper import TestingCartController
from registrasion.controllers.invoice import InvoiceController

from test_cart import RegistrationCartTestCase

UTC = pytz.timezone('UTC')


class VoucherTestCases(RegistrationCartTestCase):

    @classmethod
    def new_voucher(self, code="VOUCHER", limit=1):
        voucher = rego.Voucher.objects.create(
            recipient="Voucher recipient",
            code=code,
            limit=limit,
        )
        voucher.save()
        return voucher

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
        self.add_timedelta(rego.Voucher.RESERVATION_DURATION * 2)
        cart_2.apply_voucher(voucher.code)
        cart_2.cart.active = False
        cart_2.cart.save()

        # After the reservation duration, user 1 should not be able to apply
        # voucher, as user 2 has paid for their cart.
        self.add_timedelta(rego.Voucher.RESERVATION_DURATION * 2)
        with self.assertRaises(ValidationError):
            cart_1.apply_voucher(voucher.code)

    def test_voucher_enables_item(self):
        voucher = self.new_voucher()

        enabling_condition = rego.VoucherEnablingCondition.objects.create(
            description="Voucher condition",
            voucher=voucher,
            mandatory=False,
        )
        enabling_condition.save()
        enabling_condition.products.add(self.PROD_1)
        enabling_condition.save()

        # Adding the product without a voucher will not work
        current_cart = TestingCartController.for_user(self.USER_1)
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_1, 1)

        # Apply the voucher
        current_cart.apply_voucher(voucher.code)
        current_cart.add_to_cart(self.PROD_1, 1)

    def test_voucher_enables_discount(self):
        voucher = self.new_voucher()

        discount = rego.VoucherDiscount.objects.create(
            description="VOUCHER RECIPIENT",
            voucher=voucher,
        )
        discount.save()
        rego.DiscountForProduct.objects.create(
            discount=discount,
            product=self.PROD_1,
            percentage=Decimal(100),
            quantity=1
        ).save()

        # Having PROD_1 in place should add a discount
        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.apply_voucher(voucher.code)
        current_cart.add_to_cart(self.PROD_1, 1)
        self.assertEqual(1, len(current_cart.cart.discountitem_set.all()))

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
        with self.assertRaises(ValidationError):
            current_cart.apply_voucher(voucher.code)

    def test_voucher_can_only_be_applied_once_across_multiple_carts(self):
        voucher = self.new_voucher(limit=2)
        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.apply_voucher(voucher.code)

        inv = InvoiceController.for_cart(current_cart.cart)
        inv.pay("Hello!", inv.invoice.value)

        with self.assertRaises(ValidationError):
            current_cart.apply_voucher(voucher.code)

        return current_cart

    def test_refund_releases_used_vouchers(self):
        voucher = self.new_voucher(limit=2)
        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.apply_voucher(voucher.code)

        inv = InvoiceController.for_cart(current_cart.cart)
        inv.pay("Hello!", inv.invoice.value)

        current_cart = TestingCartController.for_user(self.USER_1)
        with self.assertRaises(ValidationError):
            current_cart.apply_voucher(voucher.code)

        inv.refund("Hello!", inv.invoice.value)
        current_cart.apply_voucher(voucher.code)
