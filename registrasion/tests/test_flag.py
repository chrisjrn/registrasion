import pytz

from django.core.exceptions import ValidationError

from registrasion.models import commerce
from registrasion.models import conditions
from registrasion.controllers.category import CategoryController
from controller_helpers import TestingCartController
from registrasion.controllers.product import ProductController

from test_cart import RegistrationCartTestCase

UTC = pytz.timezone('UTC')


class FlagTestCases(RegistrationCartTestCase):

    @classmethod
    def add_product_flag(cls, condition=conditions.FlagBase.ENABLE_IF_TRUE):
        ''' Adds a product flag condition: adding PROD_1 to a cart is
        predicated on adding PROD_2 beforehand. '''
        flag = conditions.ProductFlag.objects.create(
            description="Product condition",
            condition=condition,
        )
        flag.products.add(cls.PROD_1)
        flag.enabling_products.add(cls.PROD_2)

    @classmethod
    def add_product_flag_on_category(
            cls,
            condition=conditions.FlagBase.ENABLE_IF_TRUE,
            ):
        ''' Adds a product flag condition that operates on a category:
        adding an item from CAT_1 is predicated on adding PROD_3 beforehand '''
        flag = conditions.ProductFlag.objects.create(
            description="Product condition",
            condition=condition,
        )
        flag.categories.add(cls.CAT_1)
        flag.enabling_products.add(cls.PROD_3)

    def add_category_flag(cls, condition=conditions.FlagBase.ENABLE_IF_TRUE):
        ''' Adds a category flag condition: adding PROD_1 to a cart is
        predicated on adding an item from CAT_2 beforehand.'''
        flag = conditions.CategoryFlag.objects.create(
            description="Category condition",
            condition=condition,
            enabling_category=cls.CAT_2,
        )
        flag.products.add(cls.PROD_1)

    def test_product_flag_enables_product(self):
        self.add_product_flag()

        # Cannot buy PROD_1 without buying PROD_2
        current_cart = TestingCartController.for_user(self.USER_1)
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_1, 1)

        current_cart.add_to_cart(self.PROD_2, 1)
        current_cart.add_to_cart(self.PROD_1, 1)

    def test_product_enabled_by_product_in_previous_cart(self):
        self.add_product_flag()

        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.add_to_cart(self.PROD_2, 1)

        current_cart.next_cart()

        # Create new cart and try to add PROD_1
        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.add_to_cart(self.PROD_1, 1)

    def test_product_flag_enables_category(self):
        self.add_product_flag_on_category()

        # Cannot buy PROD_1 without buying item from CAT_2
        current_cart = TestingCartController.for_user(self.USER_1)
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_1, 1)

        current_cart.add_to_cart(self.PROD_3, 1)
        current_cart.add_to_cart(self.PROD_1, 1)

    def test_category_flag_enables_product(self):
        self.add_category_flag()

        # Cannot buy PROD_1 without buying PROD_2
        current_cart = TestingCartController.for_user(self.USER_1)
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_1, 1)

        # PROD_3 is in CAT_2
        current_cart.add_to_cart(self.PROD_3, 1)
        current_cart.add_to_cart(self.PROD_1, 1)

    def test_product_enabled_by_category_in_previous_cart(self):
        self.add_category_flag()

        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.add_to_cart(self.PROD_3, 1)

        current_cart.next_cart()

        # Create new cart and try to add PROD_1
        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.add_to_cart(self.PROD_1, 1)

    def test_multiple_eit_conditions(self):
        self.add_product_flag()
        self.add_category_flag()

        # User 1 is testing the product flag condition
        cart_1 = TestingCartController.for_user(self.USER_1)
        # Cannot add PROD_1 until a condition is met
        with self.assertRaises(ValidationError):
            cart_1.add_to_cart(self.PROD_1, 1)
        cart_1.add_to_cart(self.PROD_2, 1)
        cart_1.add_to_cart(self.PROD_1, 1)

        # User 2 is testing the category flag condition
        cart_2 = TestingCartController.for_user(self.USER_2)
        # Cannot add PROD_1 until a condition is met
        with self.assertRaises(ValidationError):
            cart_2.add_to_cart(self.PROD_1, 1)
        cart_2.add_to_cart(self.PROD_3, 1)
        cart_2.add_to_cart(self.PROD_1, 1)

    def test_multiple_dif_conditions(self):
        self.add_product_flag(condition=conditions.FlagBase.DISABLE_IF_FALSE)
        self.add_category_flag(condition=conditions.FlagBase.DISABLE_IF_FALSE)

        cart_1 = TestingCartController.for_user(self.USER_1)
        # Cannot add PROD_1 until both conditions are met
        with self.assertRaises(ValidationError):
            cart_1.add_to_cart(self.PROD_1, 1)
        cart_1.add_to_cart(self.PROD_2, 1)  # Meets the product condition
        with self.assertRaises(ValidationError):
            cart_1.add_to_cart(self.PROD_1, 1)
        cart_1.add_to_cart(self.PROD_3, 1)  # Meets the category condition
        cart_1.add_to_cart(self.PROD_1, 1)

    def test_eit_and_dif_conditions_work_together(self):
        self.add_product_flag(condition=conditions.FlagBase.ENABLE_IF_TRUE)
        self.add_category_flag(condition=conditions.FlagBase.DISABLE_IF_FALSE)

        cart_1 = TestingCartController.for_user(self.USER_1)
        # Cannot add PROD_1 until both conditions are met
        with self.assertRaises(ValidationError):
            cart_1.add_to_cart(self.PROD_1, 1)

        cart_1.add_to_cart(self.PROD_2, 1)  # Meets the EIT condition

        # Need to meet both conditions before you can add
        with self.assertRaises(ValidationError):
            cart_1.add_to_cart(self.PROD_1, 1)

        cart_1.set_quantity(self.PROD_2, 0)  # Un-meets the EIT condition

        cart_1.add_to_cart(self.PROD_3, 1)  # Meets the DIF condition

        # Need to meet both conditions before you can add
        with self.assertRaises(ValidationError):
            cart_1.add_to_cart(self.PROD_1, 1)

        cart_1.add_to_cart(self.PROD_2, 1)  # Meets the EIT condition

        # Now that both conditions are met, we can add the product
        cart_1.add_to_cart(self.PROD_1, 1)

    def test_available_products_works_with_no_conditions_set(self):
        prods = ProductController.available_products(
            self.USER_1,
            category=self.CAT_1,
        )

        self.assertTrue(self.PROD_1 in prods)
        self.assertTrue(self.PROD_2 in prods)

        prods = ProductController.available_products(
            self.USER_1,
            category=self.CAT_2,
        )

        self.assertTrue(self.PROD_3 in prods)
        self.assertTrue(self.PROD_4 in prods)

        prods = ProductController.available_products(
            self.USER_1,
            products=[self.PROD_1, self.PROD_2, self.PROD_3, self.PROD_4],
        )

        self.assertTrue(self.PROD_1 in prods)
        self.assertTrue(self.PROD_2 in prods)
        self.assertTrue(self.PROD_3 in prods)
        self.assertTrue(self.PROD_4 in prods)

    def test_available_products_on_category_works_when_condition_not_met(self):
        self.add_product_flag(condition=conditions.FlagBase.ENABLE_IF_TRUE)

        prods = ProductController.available_products(
            self.USER_1,
            category=self.CAT_1,
        )

        self.assertTrue(self.PROD_1 not in prods)
        self.assertTrue(self.PROD_2 in prods)

    def test_available_products_on_category_works_when_condition_is_met(self):
        self.add_product_flag(condition=conditions.FlagBase.ENABLE_IF_TRUE)

        cart_1 = TestingCartController.for_user(self.USER_1)
        cart_1.add_to_cart(self.PROD_2, 1)

        prods = ProductController.available_products(
            self.USER_1,
            category=self.CAT_1,
        )

        self.assertTrue(self.PROD_1 in prods)
        self.assertTrue(self.PROD_2 in prods)

    def test_available_products_on_products_works_when_condition_not_met(self):
        self.add_product_flag(condition=conditions.FlagBase.ENABLE_IF_TRUE)

        prods = ProductController.available_products(
            self.USER_1,
            products=[self.PROD_1, self.PROD_2],
        )

        self.assertTrue(self.PROD_1 not in prods)
        self.assertTrue(self.PROD_2 in prods)

    def test_available_products_on_products_works_when_condition_is_met(self):
        self.add_product_flag(condition=conditions.FlagBase.ENABLE_IF_TRUE)

        cart_1 = TestingCartController.for_user(self.USER_1)
        cart_1.add_to_cart(self.PROD_2, 1)

        prods = ProductController.available_products(
            self.USER_1,
            products=[self.PROD_1, self.PROD_2],
        )

        self.assertTrue(self.PROD_1 in prods)
        self.assertTrue(self.PROD_2 in prods)

    def test_category_flag_fails_if_cart_refunded(self):
        self.add_category_flag(condition=conditions.FlagBase.ENABLE_IF_TRUE)

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_3, 1)

        cart.next_cart()

        cart_2 = TestingCartController.for_user(self.USER_1)
        cart_2.add_to_cart(self.PROD_1, 1)
        cart_2.set_quantity(self.PROD_1, 0)

        cart.cart.status = commerce.Cart.STATUS_RELEASED
        cart.cart.save()

        with self.assertRaises(ValidationError):
            cart_2.set_quantity(self.PROD_1, 1)

    def test_product_flag_fails_if_cart_refunded(self):
        self.add_product_flag(condition=conditions.FlagBase.ENABLE_IF_TRUE)

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_2, 1)

        cart.next_cart()

        cart_2 = TestingCartController.for_user(self.USER_1)
        cart_2.add_to_cart(self.PROD_1, 1)
        cart_2.set_quantity(self.PROD_1, 0)

        cart.cart.status = commerce.Cart.STATUS_RELEASED
        cart.cart.save()

        with self.assertRaises(ValidationError):
            cart_2.set_quantity(self.PROD_1, 1)

    def test_available_categories(self):
        self.add_product_flag_on_category(
            condition=conditions.FlagBase.ENABLE_IF_TRUE,
        )

        cart_1 = TestingCartController.for_user(self.USER_1)

        cats = CategoryController.available_categories(
            self.USER_1,
        )

        self.assertFalse(self.CAT_1 in cats)
        self.assertTrue(self.CAT_2 in cats)

        cart_1.add_to_cart(self.PROD_3, 1)

        cats = CategoryController.available_categories(
            self.USER_1,
        )

        self.assertTrue(self.CAT_1 in cats)
        self.assertTrue(self.CAT_2 in cats)

    def test_validate_cart_when_flags_become_unmet(self):
        self.add_product_flag(condition=conditions.FlagBase.ENABLE_IF_TRUE)

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_2, 1)
        cart.add_to_cart(self.PROD_1, 1)

        # Should pass
        cart.validate_cart()

        cart.set_quantity(self.PROD_2, 0)

        # Should fail
        with self.assertRaises(ValidationError):
            cart.validate_cart()

    def test_fix_simple_errors_resolves_unavailable_products(self):
        self.test_validate_cart_when_flags_become_unmet()
        cart = TestingCartController.for_user(self.USER_1)

        # Should just remove all of the unavailable products
        cart.fix_simple_errors()
        # Should now succeed
        cart.validate_cart()

        # Should keep PROD_2 in the cart
        items = commerce.ProductItem.objects.filter(cart=cart.cart)
        self.assertFalse([i for i in items if i.product == self.PROD_1])

    def test_fix_simple_errors_does_not_remove_limited_items(self):
        cart = TestingCartController.for_user(self.USER_1)

        cart.add_to_cart(self.PROD_2, 1)
        cart.add_to_cart(self.PROD_1, 10)

        # Should just remove all of the unavailable products
        cart.fix_simple_errors()
        # Should now succeed
        cart.validate_cart()

        # Should keep PROD_2 in the cart
        # and also PROD_1, which is now exhausted for user.
        items = commerce.ProductItem.objects.filter(cart=cart.cart)
        self.assertTrue([i for i in items if i.product == self.PROD_1])
