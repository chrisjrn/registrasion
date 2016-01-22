import datetime
import pytz

from decimal import Decimal
from django.core.exceptions import ValidationError

from registrasion import models as rego
from registrasion.controllers.cart import CartController

from test_cart import RegistrationCartTestCase

UTC = pytz.timezone('UTC')


class VoucherTestCases(RegistrationCartTestCase):

    @classmethod
    def new_voucher(self):
        voucher = rego.Voucher.objects.create(
            recipient="Voucher recipient",
            code="VOUCHER",
            limit=1
        )
        voucher.save()
        return voucher

    def test_apply_voucher(self):
        voucher = self.new_voucher()

        self.set_time(datetime.datetime(2015, 01, 01, tzinfo=UTC))

        cart_1 = CartController.for_user(self.USER_1)
        cart_1.apply_voucher(voucher)
        self.assertIn(voucher, cart_1.cart.vouchers.all())

        # Second user should not be able to apply this voucher (it's exhausted)
        cart_2 = CartController.for_user(self.USER_2)
        with self.assertRaises(ValidationError):
            cart_2.apply_voucher(voucher)

        # After the reservation duration
        # user 2 should be able to apply voucher
        self.add_timedelta(rego.Voucher.RESERVATION_DURATION * 2)
        cart_2.apply_voucher(voucher)
        cart_2.cart.active = False
        cart_2.cart.save()

        # After the reservation duration, user 1 should not be able to apply
        # voucher, as user 2 has paid for their cart.
        self.add_timedelta(rego.Voucher.RESERVATION_DURATION * 2)
        with self.assertRaises(ValidationError):
            cart_1.apply_voucher(voucher)

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
        current_cart = CartController.for_user(self.USER_1)
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_1, 1)

        # Apply the voucher
        current_cart.apply_voucher(voucher)
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
        current_cart = CartController.for_user(self.USER_1)
        current_cart.apply_voucher(voucher)
        current_cart.add_to_cart(self.PROD_1, 1)
        self.assertEqual(1, len(current_cart.cart.discountitem_set.all()))
