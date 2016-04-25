import datetime
import pytz

from django.core.exceptions import ValidationError

from controller_helpers import TestingCartController
from test_cart import RegistrationCartTestCase

from registrasion.models import commerce
from registrasion.models import conditions

UTC = pytz.timezone('UTC')


class CeilingsTestCases(RegistrationCartTestCase):

    def test_add_to_cart_ceiling_limit(self):
        self.make_ceiling("Limit ceiling", limit=9)
        self.__add_to_cart_test()

    def test_add_to_cart_ceiling_category_limit(self):
        self.make_category_ceiling("Limit ceiling", limit=9)
        self.__add_to_cart_test()

    def __add_to_cart_test(self):

        current_cart = TestingCartController.for_user(self.USER_1)

        # User should not be able to add 10 of PROD_1 to the current cart
        # because it is affected by limit_ceiling
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_2, 10)

        # User should be able to add 5 of PROD_1 to the current cart
        current_cart.add_to_cart(self.PROD_1, 5)

        # User should not be able to add 6 of PROD_2 to the current cart
        # because it is affected by CEIL_1
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_2, 6)

        # User should be able to add 5 of PROD_2 to the current cart
        current_cart.add_to_cart(self.PROD_2, 4)

    def test_add_to_cart_ceiling_date_range(self):
        self.make_ceiling(
            "date range ceiling",
            start_time=datetime.datetime(2015, 01, 01, tzinfo=UTC),
            end_time=datetime.datetime(2015, 02, 01, tzinfo=UTC))

        current_cart = TestingCartController.for_user(self.USER_1)

        # User should not be able to add whilst we're before start_time
        self.set_time(datetime.datetime(2014, 01, 01, tzinfo=UTC))
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_1, 1)

        # User should be able to add whilst we're during date range
        # On edge of start
        self.set_time(datetime.datetime(2015, 01, 01, tzinfo=UTC))
        current_cart.add_to_cart(self.PROD_1, 1)
        # In middle
        self.set_time(datetime.datetime(2015, 01, 15, tzinfo=UTC))
        current_cart.add_to_cart(self.PROD_1, 1)
        # On edge of end
        self.set_time(datetime.datetime(2015, 02, 01, tzinfo=UTC))
        current_cart.add_to_cart(self.PROD_1, 1)

        # User should not be able to add whilst we're after date range
        self.set_time(datetime.datetime(2014, 01, 01, minute=01, tzinfo=UTC))
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_1, 1)

    def test_add_to_cart_ceiling_limit_reserved_carts(self):
        self.make_ceiling("Limit ceiling", limit=1)

        self.set_time(datetime.datetime(2015, 01, 01, tzinfo=UTC))

        first_cart = TestingCartController.for_user(self.USER_1)
        second_cart = TestingCartController.for_user(self.USER_2)

        first_cart.add_to_cart(self.PROD_1, 1)

        # User 2 should not be able to add item to their cart
        # because user 1 has item reserved, exhausting the ceiling
        with self.assertRaises(ValidationError):
            second_cart.add_to_cart(self.PROD_1, 1)

        # User 2 should be able to add item to their cart once the
        # reservation duration is elapsed
        self.add_timedelta(self.RESERVATION + datetime.timedelta(seconds=1))
        second_cart.add_to_cart(self.PROD_1, 1)

        # User 2 pays for their cart

        second_cart.next_cart()

        # User 1 should not be able to add item to their cart
        # because user 2 has paid for their reserved item, exhausting
        # the ceiling, regardless of the reservation time.
        self.add_timedelta(self.RESERVATION * 20)
        with self.assertRaises(ValidationError):
            first_cart.add_to_cart(self.PROD_1, 1)

    def test_validate_cart_fails_product_ceilings(self):
        self.make_ceiling("Limit ceiling", limit=1)
        self.__validation_test()

    def test_validate_cart_fails_product_discount_ceilings(self):
        self.make_discount_ceiling("Limit ceiling", limit=1)
        self.__validation_test()

    def __validation_test(self):
        self.set_time(datetime.datetime(2015, 01, 01, tzinfo=UTC))

        first_cart = TestingCartController.for_user(self.USER_1)
        second_cart = TestingCartController.for_user(self.USER_2)

        # Adding a valid product should validate.
        first_cart.add_to_cart(self.PROD_1, 1)
        first_cart.validate_cart()

        # Cart should become invalid if lapsed carts are claimed.
        self.add_timedelta(self.RESERVATION + datetime.timedelta(seconds=1))

        # Unpaid cart within reservation window
        second_cart.add_to_cart(self.PROD_1, 1)
        with self.assertRaises(ValidationError):
            first_cart.validate_cart()

        # Paid cart outside the reservation window

        second_cart.next_cart()
        self.add_timedelta(self.RESERVATION + datetime.timedelta(seconds=1))
        with self.assertRaises(ValidationError):
            first_cart.validate_cart()

    def test_items_released_from_ceiling_by_refund(self):
        self.make_ceiling("Limit ceiling", limit=1)

        first_cart = TestingCartController.for_user(self.USER_1)
        first_cart.add_to_cart(self.PROD_1, 1)

        first_cart.next_cart()

        second_cart = TestingCartController.for_user(self.USER_2)
        with self.assertRaises(ValidationError):
            second_cart.add_to_cart(self.PROD_1, 1)

        first_cart.cart.status = commerce.Cart.STATUS_RELEASED
        first_cart.cart.save()

        second_cart.add_to_cart(self.PROD_1, 1)

    def test_discount_ceiling_only_counts_items_covered_by_ceiling(self):
        self.make_discount_ceiling("Limit ceiling", limit=1, percentage=50)
        voucher = self.new_voucher(code="VOUCHER")

        discount = conditions.VoucherDiscount.objects.create(
            description="VOUCHER RECIPIENT",
            voucher=voucher,
        )
        conditions.DiscountForProduct.objects.create(
            discount=discount,
            product=self.PROD_1,
            percentage=100,
            quantity=1
        )

        # Buy two of PROD_1, in separate carts:
        cart = TestingCartController.for_user(self.USER_1)
        # the 100% discount from the voucher should apply to the first item
        # and not the ceiling discount.
        cart.apply_voucher("VOUCHER")
        cart.add_to_cart(self.PROD_1, 1)
        self.assertEqual(1, cart.cart.discountitem_set.count())

        cart.next_cart()

        # The second cart has no voucher attached, so should apply the
        # ceiling discount
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)
        self.assertEqual(1, cart.cart.discountitem_set.count())
