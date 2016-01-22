import datetime
import pytz

from decimal import Decimal
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from registrasion import models as rego
from registrasion.controllers.cart import CartController

from patch_datetime import SetTimeMixin

UTC = pytz.timezone('UTC')


class RegistrationCartTestCase(SetTimeMixin, TestCase):

    def setUp(self):
        super(RegistrationCartTestCase, self).setUp()

    @classmethod
    def setUpTestData(cls):
        cls.USER_1 = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='top_secret')

        cls.USER_2 = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='top_secret')

        cls.CAT_1 = rego.Category.objects.create(
            name="Category 1",
            description="This is a test category",
            order=10,
            render_type=rego.Category.RENDER_TYPE_RADIO,
        )
        cls.CAT_1.save()

        cls.CAT_2 = rego.Category.objects.create(
            name="Category 2",
            description="This is a test category",
            order=10,
            render_type=rego.Category.RENDER_TYPE_RADIO,
        )
        cls.CAT_2.save()

        cls.RESERVATION = datetime.timedelta(hours=1)

        cls.PROD_1 = rego.Product.objects.create(
            name="Product 1",
            description="This is a test product. It costs $10. "
                        "A user may have 10 of them.",
            category=cls.CAT_1,
            price=Decimal("10.00"),
            reservation_duration=cls.RESERVATION,
            limit_per_user=10,
            order=10,
        )
        cls.PROD_1.save()

        cls.PROD_2 = rego.Product.objects.create(
            name="Product 2",
            description="This is a test product. It costs $10. "
                        "A user may have 10 of them.",
            category=cls.CAT_1,
            price=Decimal("10.00"),
            limit_per_user=10,
            order=10,
        )
        cls.PROD_2.save()

        cls.PROD_3 = rego.Product.objects.create(
            name="Product 3",
            description="This is a test product. It costs $10. "
                        "A user may have 10 of them.",
            category=cls.CAT_2,
            price=Decimal("10.00"),
            limit_per_user=10,
            order=10,
        )
        cls.PROD_2.save()

    @classmethod
    def make_ceiling(cls, name, limit=None, start_time=None, end_time=None):
        limit_ceiling = rego.TimeOrStockLimitEnablingCondition.objects.create(
            description=name,
            mandatory=True,
            limit=limit,
            start_time=start_time,
            end_time=end_time
        )
        limit_ceiling.save()
        limit_ceiling.products.add(cls.PROD_1, cls.PROD_2)
        limit_ceiling.save()

    @classmethod
    def make_category_ceiling(
            cls, name, limit=None, start_time=None, end_time=None):
        limit_ceiling = rego.TimeOrStockLimitEnablingCondition.objects.create(
            description=name,
            mandatory=True,
            limit=limit,
            start_time=start_time,
            end_time=end_time
        )
        limit_ceiling.save()
        limit_ceiling.categories.add(cls.CAT_1)
        limit_ceiling.save()

    @classmethod
    def make_discount_ceiling(
            cls, name, limit=None, start_time=None, end_time=None):
        limit_ceiling = rego.TimeOrStockLimitDiscount.objects.create(
            description=name,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )
        limit_ceiling.save()
        rego.DiscountForProduct.objects.create(
            discount=limit_ceiling,
            product=cls.PROD_1,
            percentage=100,
            quantity=10,
        ).save()


class BasicCartTests(RegistrationCartTestCase):

    def test_get_cart(self):
        current_cart = CartController.for_user(self.USER_1)

        current_cart.cart.active = False
        current_cart.cart.save()

        old_cart = current_cart

        current_cart = CartController.for_user(self.USER_1)
        self.assertNotEqual(old_cart.cart, current_cart.cart)

        current_cart2 = CartController.for_user(self.USER_1)
        self.assertEqual(current_cart.cart, current_cart2.cart)

    def test_add_to_cart_collapses_product_items(self):
        current_cart = CartController.for_user(self.USER_1)

        # Add a product twice
        current_cart.add_to_cart(self.PROD_1, 1)
        current_cart.add_to_cart(self.PROD_1, 1)

        # Count of products for a given user should be collapsed.
        items = rego.ProductItem.objects.filter(
            cart=current_cart.cart,
            product=self.PROD_1)
        self.assertEqual(1, len(items))
        item = items[0]
        self.assertEquals(2, item.quantity)

    def test_add_to_cart_per_user_limit(self):
        current_cart = CartController.for_user(self.USER_1)

        # User should be able to add 1 of PROD_1 to the current cart.
        current_cart.add_to_cart(self.PROD_1, 1)

        # User should be able to add 1 of PROD_1 to the current cart.
        current_cart.add_to_cart(self.PROD_1, 1)

        # User should not be able to add 10 of PROD_1 to the current cart now,
        # because they have a limit of 10.
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_1, 10)

        current_cart.cart.active = False
        current_cart.cart.save()

        current_cart = CartController.for_user(self.USER_1)
        # User should not be able to add 10 of PROD_1 to the current cart now,
        # even though it's a new cart.
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_1, 10)

        # Second user should not be affected by first user's limits
        second_user_cart = CartController.for_user(self.USER_2)
        second_user_cart.add_to_cart(self.PROD_1, 10)
