import datetime
import pytz

from decimal import Decimal
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from registrasion.models import commerce
from registrasion.models import conditions
from registrasion.models import inventory
from registrasion.models import people
from registrasion.controllers.batch import BatchController
from registrasion.controllers.product import ProductController

from registrasion.tests.controller_helpers import TestingCartController
from registrasion.tests.patches import MixInPatches

UTC = pytz.timezone('UTC')


class RegistrationCartTestCase(MixInPatches, TestCase):

    def setUp(self):
        super(RegistrationCartTestCase, self).setUp()

    def tearDown(self):
        if True:
            # If you're seeing segfaults in tests, enable this.
            call_command(
                'flush',
                verbosity=0,
                interactive=False,
                reset_sequences=False,
                allow_cascade=False,
                inhibit_post_migrate=False
            )

        super(RegistrationCartTestCase, self).tearDown()

    @classmethod
    def setUpTestData(cls):

        super(RegistrationCartTestCase, cls).setUpTestData()

        cls.USER_1 = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='top_secret')

        cls.USER_2 = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='top_secret')

        attendee1 = people.Attendee.get_instance(cls.USER_1)
        people.AttendeeProfileBase.objects.create(
            attendee=attendee1,
        )
        attendee2 = people.Attendee.get_instance(cls.USER_2)
        people.AttendeeProfileBase.objects.create(
            attendee=attendee2,
        )

        cls.RESERVATION = datetime.timedelta(hours=1)

        cls.categories = []
        for i in range(2):
            cat = inventory.Category.objects.create(
                name="Category " + str(i + 1),
                description="This is a test category",
                order=i,
                render_type=inventory.Category.RENDER_TYPE_RADIO,
                required=False,
            )
            cls.categories.append(cat)

        cls.CAT_1 = cls.categories[0]
        cls.CAT_2 = cls.categories[1]

        cls.products = []
        for i in range(4):
            prod = inventory.Product.objects.create(
                name="Product " + str(i + 1),
                description="This is a test product.",
                category=cls.categories[i / 2],  # 2 products per category
                price=Decimal("10.00"),
                reservation_duration=cls.RESERVATION,
                limit_per_user=10,
                order=1,
            )
            cls.products.append(prod)

        cls.PROD_1 = cls.products[0]
        cls.PROD_2 = cls.products[1]
        cls.PROD_3 = cls.products[2]
        cls.PROD_4 = cls.products[3]

        cls.PROD_4.price = Decimal("5.00")
        cls.PROD_4.save()

        # Burn through some carts -- this made some past flag tests fail
        current_cart = TestingCartController.for_user(cls.USER_1)

        current_cart.next_cart()

        current_cart = TestingCartController.for_user(cls.USER_2)

        current_cart.next_cart()

    @classmethod
    def make_ceiling(cls, name, limit=None, start_time=None, end_time=None):
        limit_ceiling = conditions.TimeOrStockLimitFlag.objects.create(
            description=name,
            condition=conditions.FlagBase.DISABLE_IF_FALSE,
            limit=limit,
            start_time=start_time,
            end_time=end_time
        )
        limit_ceiling.products.add(cls.PROD_1, cls.PROD_2)

    @classmethod
    def make_category_ceiling(
            cls, name, limit=None, start_time=None, end_time=None):
        limit_ceiling = conditions.TimeOrStockLimitFlag.objects.create(
            description=name,
            condition=conditions.FlagBase.DISABLE_IF_FALSE,
            limit=limit,
            start_time=start_time,
            end_time=end_time
        )
        limit_ceiling.categories.add(cls.CAT_1)

    @classmethod
    def make_discount_ceiling(
            cls, name, limit=None, start_time=None, end_time=None,
            percentage=100):
        limit_ceiling = conditions.TimeOrStockLimitDiscount.objects.create(
            description=name,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
        conditions.DiscountForProduct.objects.create(
            discount=limit_ceiling,
            product=cls.PROD_1,
            percentage=percentage,
            quantity=10,
        )

    @classmethod
    def new_voucher(self, code="VOUCHER", limit=1):
        voucher = inventory.Voucher.objects.create(
            recipient="Voucher recipient",
            code=code,
            limit=limit,
        )
        return voucher

    @classmethod
    def reget(cls, object):
        return type(object).objects.get(id=object.id)


class BasicCartTests(RegistrationCartTestCase):

    def test_get_cart(self):
        current_cart = TestingCartController.for_user(self.USER_1)

        current_cart.next_cart()

        old_cart = current_cart

        current_cart = TestingCartController.for_user(self.USER_1)
        self.assertNotEqual(old_cart.cart, current_cart.cart)

        current_cart2 = TestingCartController.for_user(self.USER_1)
        self.assertEqual(current_cart.cart, current_cart2.cart)

    def test_add_to_cart_collapses_product_items(self):
        current_cart = TestingCartController.for_user(self.USER_1)

        # Add a product twice
        current_cart.add_to_cart(self.PROD_1, 1)
        current_cart.add_to_cart(self.PROD_1, 1)

        # Count of products for a given user should be collapsed.
        items = commerce.ProductItem.objects.filter(
            cart=current_cart.cart,
            product=self.PROD_1)
        self.assertEqual(1, len(items))
        item = items[0]
        self.assertEquals(2, item.quantity)

    def test_set_quantity(self):
        current_cart = TestingCartController.for_user(self.USER_1)

        def get_item():
            return commerce.ProductItem.objects.get(
                cart=current_cart.cart,
                product=self.PROD_1)

        current_cart.set_quantity(self.PROD_1, 1)
        self.assertEqual(1, get_item().quantity)

        # Setting the quantity to zero should remove the entry from the cart.
        current_cart.set_quantity(self.PROD_1, 0)
        with self.assertRaises(ObjectDoesNotExist):
            get_item()

        current_cart.set_quantity(self.PROD_1, 9)
        self.assertEqual(9, get_item().quantity)

        with self.assertRaises(ValidationError):
            current_cart.set_quantity(self.PROD_1, 11)

        self.assertEqual(9, get_item().quantity)

        with self.assertRaises(ValidationError):
            current_cart.set_quantity(self.PROD_1, -1)

        self.assertEqual(9, get_item().quantity)

        current_cart.set_quantity(self.PROD_1, 2)
        self.assertEqual(2, get_item().quantity)

    def test_add_to_cart_product_per_user_limit(self):
        current_cart = TestingCartController.for_user(self.USER_1)

        # User should be able to add 1 of PROD_1 to the current cart.
        current_cart.add_to_cart(self.PROD_1, 1)

        # User should be able to add 1 of PROD_1 to the current cart.
        current_cart.add_to_cart(self.PROD_1, 1)

        # User should not be able to add 10 of PROD_1 to the current cart now,
        # because they have a limit of 10.
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_1, 10)

        current_cart.next_cart()

        current_cart = TestingCartController.for_user(self.USER_1)
        # User should not be able to add 10 of PROD_1 to the current cart now,
        # even though it's a new cart.
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_1, 10)

        # Second user should not be affected by first user's limits
        second_user_cart = TestingCartController.for_user(self.USER_2)
        second_user_cart.add_to_cart(self.PROD_1, 10)

    def set_limits(self):
        self.CAT_2.limit_per_user = 10
        self.PROD_2.limit_per_user = None
        self.PROD_3.limit_per_user = None
        self.PROD_4.limit_per_user = 6

        self.CAT_2.save()
        self.PROD_2.save()
        self.PROD_3.save()
        self.PROD_4.save()

    def test_per_user_product_limit_ignored_if_blank(self):
        self.set_limits()

        current_cart = TestingCartController.for_user(self.USER_1)
        # There is no product limit on PROD_2, and there is no cat limit
        current_cart.add_to_cart(self.PROD_2, 1)
        # There is no product limit on PROD_3, but there is a cat limit
        current_cart.add_to_cart(self.PROD_3, 1)

    def test_per_user_category_limit_ignored_if_blank(self):
        self.set_limits()
        current_cart = TestingCartController.for_user(self.USER_1)
        # There is no product limit on PROD_2, and there is no cat limit
        current_cart.add_to_cart(self.PROD_2, 1)
        # There is no cat limit on PROD_1, but there is a prod limit
        current_cart.add_to_cart(self.PROD_1, 1)

    def test_per_user_category_limit_only(self):
        self.set_limits()

        current_cart = TestingCartController.for_user(self.USER_1)

        # Cannot add to cart if category limit is filled by one product.
        current_cart.set_quantity(self.PROD_3, 10)
        with self.assertRaises(ValidationError):
            current_cart.set_quantity(self.PROD_4, 1)

        # Can add to cart if category limit is not filled by one product
        current_cart.set_quantity(self.PROD_3, 5)
        current_cart.set_quantity(self.PROD_4, 5)
        # Cannot add to cart if category limit is filled by two products
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_3, 1)

        current_cart.next_cart()

        current_cart = TestingCartController.for_user(self.USER_1)
        # The category limit should extend across carts
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_3, 10)

    def test_per_user_category_and_product_limits(self):
        self.set_limits()

        current_cart = TestingCartController.for_user(self.USER_1)

        # Hit both the product and category edges:
        current_cart.set_quantity(self.PROD_3, 4)
        current_cart.set_quantity(self.PROD_4, 6)
        with self.assertRaises(ValidationError):
            # There's unlimited PROD_3, but limited in the category
            current_cart.add_to_cart(self.PROD_3, 1)

        current_cart.set_quantity(self.PROD_3, 0)
        with self.assertRaises(ValidationError):
            # There's only 6 allowed of PROD_4
            current_cart.add_to_cart(self.PROD_4, 1)

        # The limits should extend across carts...

        current_cart.next_cart()

        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.set_quantity(self.PROD_3, 4)

        with self.assertRaises(ValidationError):
            current_cart.set_quantity(self.PROD_3, 5)

        with self.assertRaises(ValidationError):
            current_cart.set_quantity(self.PROD_4, 1)

    def __available_products_test(self, item, quantity):
        self.set_limits()

        def get_prods():
            return ProductController.available_products(
                self.USER_1,
                products=[self.PROD_2, self.PROD_3, self.PROD_4],
            )

        current_cart = TestingCartController.for_user(self.USER_1)
        prods = get_prods()
        self.assertTrue(item in prods)
        current_cart.add_to_cart(item, quantity)
        self.assertTrue(item in prods)

        current_cart.next_cart()

        current_cart = TestingCartController.for_user(self.USER_1)

        prods = get_prods()
        self.assertTrue(item not in prods)

    def test_available_products_respects_category_limits(self):
        self.__available_products_test(self.PROD_3, 10)

    def test_available_products_respects_product_limits(self):
        self.__available_products_test(self.PROD_4, 6)

    def test_cart_controller_for_user_is_memoised(self):
        # - that for_user is memoised
        with BatchController.batch(self.USER_1):
            cart = TestingCartController.for_user(self.USER_1)
            cart_2 = TestingCartController.for_user(self.USER_1)
        self.assertIs(cart, cart_2)

    def test_cart_revision_does_not_increment_if_not_modified(self):
        cart = TestingCartController.for_user(self.USER_1)
        rev_0 = cart.cart.revision

        with BatchController.batch(self.USER_1):
            # Memoise the cart
            TestingCartController.for_user(self.USER_1)
            # Do nothing on exit

        rev_1 = self.reget(cart.cart).revision
        self.assertEqual(rev_0, rev_1)

    def test_cart_revision_only_increments_at_end_of_batches(self):
        cart = TestingCartController.for_user(self.USER_1)
        rev_0 = cart.cart.revision

        with BatchController.batch(self.USER_1):
            # Memoise the cart
            same_cart = TestingCartController.for_user(self.USER_1)
            same_cart.add_to_cart(self.PROD_1, 1)
            rev_1 = self.reget(same_cart.cart).revision

        rev_2 = self.reget(cart.cart).revision

        self.assertEqual(rev_0, rev_1)
        self.assertNotEqual(rev_0, rev_2)

    def test_cart_discounts_only_calculated_at_end_of_batches(self):
        def count_discounts(cart):
            return cart.cart.discountitem_set.count()

        cart = TestingCartController.for_user(self.USER_1)
        self.make_discount_ceiling("FLOOZLE")
        count_0 = count_discounts(cart)

        with BatchController.batch(self.USER_1):
            # Memoise the cart
            same_cart = TestingCartController.for_user(self.USER_1)

            with BatchController.batch(self.USER_1):
                # Memoise the cart
                same_cart_2 = TestingCartController.for_user(self.USER_1)

                same_cart_2.add_to_cart(self.PROD_1, 1)
                count_1 = count_discounts(same_cart_2)

            count_2 = count_discounts(same_cart)

        count_3 = count_discounts(cart)

        self.assertEqual(0, count_0)
        self.assertEqual(0, count_1)
        self.assertEqual(0, count_2)
        self.assertEqual(1, count_3)

    def test_reservation_duration_forwards(self):
        ''' Reservation duration should be the maximum of the durations (small)
        '''

        new_res = self.RESERVATION * 2
        self.PROD_2.reservation_duration = new_res
        self.PROD_2.save()

        cart = TestingCartController.for_user(self.USER_1)

        cart.add_to_cart(self.PROD_1, 1)
        cart.cart.refresh_from_db()
        self.assertEqual(cart.cart.reservation_duration, self.RESERVATION)

        cart.add_to_cart(self.PROD_2, 1)
        cart.cart.refresh_from_db()
        self.assertEqual(cart.cart.reservation_duration, new_res)

    def test_reservation_duration_backwards(self):
        ''' Reservation duration should be the maximum of the durations (big)
        '''

        new_res = self.RESERVATION * 2
        self.PROD_2.reservation_duration = new_res
        self.PROD_2.save()

        cart = TestingCartController.for_user(self.USER_1)

        cart.add_to_cart(self.PROD_2, 1)
        cart.cart.refresh_from_db()
        self.assertEqual(cart.cart.reservation_duration, new_res)

        cart.add_to_cart(self.PROD_1, 1)
        cart.cart.refresh_from_db()
        self.assertEqual(cart.cart.reservation_duration, new_res)

    def test_reservation_duration_removals(self):
        ''' Reservation duration should update with removals
        '''

        new_res = self.RESERVATION * 2
        self.PROD_2.reservation_duration = new_res
        self.PROD_2.save()

        self.set_time(datetime.datetime(2015, 1, 1, tzinfo=UTC))
        cart = TestingCartController.for_user(self.USER_1)

        one_third = new_res / 3

        cart.add_to_cart(self.PROD_2, 1)
        cart.cart.refresh_from_db()
        self.assertEqual(cart.cart.reservation_duration, new_res)

        # Reservation duration should not decrease if time hasn't decreased
        cart.set_quantity(self.PROD_2, 0)
        cart.cart.refresh_from_db()
        self.assertEqual(cart.cart.reservation_duration, new_res)

        # Adding a new product should not reset the reservation duration below
        # the old one
        cart.add_to_cart(self.PROD_1, 1)
        cart.cart.refresh_from_db()
        self.assertEqual(cart.cart.reservation_duration, new_res)

        self.add_timedelta(one_third)

        # The old reservation duration is still longer than PROD_1's
        cart.add_to_cart(self.PROD_1, 1)
        cart.cart.refresh_from_db()
        self.assertEqual(cart.cart.reservation_duration, new_res - one_third)

        self.add_timedelta(one_third)
        cart.add_to_cart(self.PROD_1, 1)
        cart.cart.refresh_from_db()
        self.assertEqual(cart.cart.reservation_duration, self.RESERVATION)

    def test_reservation_extension_less_than_current(self):
        ''' Reservation extension should have no effect if it's too small
        '''

        self.set_time(datetime.datetime(2015, 1, 1, tzinfo=UTC))
        cart = TestingCartController.for_user(self.USER_1)

        cart.add_to_cart(self.PROD_1, 1)
        cart.cart.refresh_from_db()
        self.assertEqual(cart.cart.reservation_duration, self.RESERVATION)

        cart.extend_reservation(datetime.timedelta(minutes=30))

        cart.cart.refresh_from_db()
        self.assertEqual(cart.cart.reservation_duration, self.RESERVATION)

    def test_reservation_extension(self):
        ''' Test various reservation extension bits.
        '''

        self.set_time(datetime.datetime(2015, 1, 1, tzinfo=UTC))
        cart = TestingCartController.for_user(self.USER_1)

        cart.add_to_cart(self.PROD_1, 1)
        cart.cart.refresh_from_db()
        self.assertEqual(cart.cart.reservation_duration, self.RESERVATION)

        hours = datetime.timedelta(hours=1)
        cart.extend_reservation(24 * hours)

        cart.cart.refresh_from_db()
        self.assertEqual(cart.cart.reservation_duration, 24 * hours)

        self.add_timedelta(1 * hours)

        # PROD_1's reservation is less than what we've added to the cart
        cart.add_to_cart(self.PROD_1, 1)
        cart.cart.refresh_from_db()
        self.assertEqual(cart.cart.reservation_duration, 23 * hours)

        # Now the extension should only have 59 minutes remaining
        # so the autoextend behaviour should kick in
        self.add_timedelta(datetime.timedelta(hours=22, minutes=1))
        cart.add_to_cart(self.PROD_1, 1)
        cart.cart.refresh_from_db()
        self.assertEqual(
            cart.cart.reservation_duration,
            self.PROD_1.reservation_duration,
        )
