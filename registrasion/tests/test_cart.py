import datetime
import pytz

from decimal import Decimal
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.test import TestCase

from registrasion import models as rego
from registrasion.controllers.cart import CartController
from registrasion.controllers.product import ProductController

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

        cls.RESERVATION = datetime.timedelta(hours=1)

        cls.categories = []
        for i in xrange(2):
            cat = rego.Category.objects.create(
                name="Category " + str(i + 1),
                description="This is a test category",
                order=i,
                render_type=rego.Category.RENDER_TYPE_RADIO,
                required=False,
            )
            cat.save()
            cls.categories.append(cat)

        cls.CAT_1 = cls.categories[0]
        cls.CAT_2 = cls.categories[1]

        cls.products = []
        for i in xrange(4):
            prod = rego.Product.objects.create(
                name="Product " + str(i + 1),
                description="This is a test product.",
                category=cls.categories[i / 2],  # 2 products per category
                price=Decimal("10.00"),
                reservation_duration=cls.RESERVATION,
                limit_per_user=10,
                order=1,
            )
            prod.save()
            cls.products.append(prod)

        cls.PROD_1 = cls.products[0]
        cls.PROD_2 = cls.products[1]
        cls.PROD_3 = cls.products[2]
        cls.PROD_4 = cls.products[3]

        cls.PROD_4.price = Decimal("5.00")
        cls.PROD_4.save()

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

    def test_set_quantity(self):
        current_cart = CartController.for_user(self.USER_1)

        def get_item():
            return rego.ProductItem.objects.get(
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

        current_cart = CartController.for_user(self.USER_1)
        # There is no product limit on PROD_2, and there is no cat limit
        current_cart.add_to_cart(self.PROD_2, 1)
        # There is no product limit on PROD_3, but there is a cat limit
        current_cart.add_to_cart(self.PROD_3, 1)

    def test_per_user_category_limit_ignored_if_blank(self):
        self.set_limits()
        current_cart = CartController.for_user(self.USER_1)
        # There is no product limit on PROD_2, and there is no cat limit
        current_cart.add_to_cart(self.PROD_2, 1)
        # There is no cat limit on PROD_1, but there is a prod limit
        current_cart.add_to_cart(self.PROD_1, 1)

    def test_per_user_category_limit_only(self):
        self.set_limits()

        current_cart = CartController.for_user(self.USER_1)

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

        current_cart.cart.active = False
        current_cart.cart.save()

        current_cart = CartController.for_user(self.USER_1)
        # The category limit should extend across carts
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_3, 10)

    def test_per_user_category_and_product_limits(self):
        self.set_limits()

        current_cart = CartController.for_user(self.USER_1)

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
        current_cart.cart.active = False
        current_cart.cart.save()

        current_cart = CartController.for_user(self.USER_1)
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

        current_cart = CartController.for_user(self.USER_1)
        prods = get_prods()
        self.assertTrue(item in prods)
        current_cart.add_to_cart(item, quantity)
        self.assertTrue(item in prods)

        current_cart.cart.active = False
        current_cart.cart.save()

        current_cart = CartController.for_user(self.USER_1)

        prods = get_prods()
        self.assertTrue(item not in prods)

    def test_available_products_respects_category_limits(self):
        self.__available_products_test(self.PROD_3, 10)

    def test_available_products_respects_product_limits(self):
        self.__available_products_test(self.PROD_4, 6)
