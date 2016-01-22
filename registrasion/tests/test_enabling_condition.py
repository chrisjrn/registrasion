import datetime
import pytz

from decimal import Decimal
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from registrasion import models as rego
from registrasion.cart import CartController

from test_cart import RegistrationCartTestCase

UTC = pytz.timezone('UTC')

class EnablingConditionTestCases(RegistrationCartTestCase):

    @classmethod
    def add_product_enabling_condition(cls, mandatory=False):
        ''' Adds a product enabling condition: adding PROD_1 to a cart is
        predicated on adding PROD_2 beforehand. '''
        enabling_condition = rego.ProductEnablingCondition.objects.create(
            description="Product condition",
            mandatory=mandatory,
        )
        enabling_condition.save()
        enabling_condition.products.add(cls.PROD_1)
        enabling_condition.enabling_products.add(cls.PROD_2)
        enabling_condition.save()


    @classmethod
    def add_product_enabling_condition_on_category(cls, mandatory=False):
        ''' Adds a product enabling condition that operates on a category:
        adding an item from CAT_1 is predicated on adding PROD_3 beforehand '''
        enabling_condition = rego.ProductEnablingCondition.objects.create(
            description="Product condition",
            mandatory=mandatory,
        )
        enabling_condition.save()
        enabling_condition.categories.add(cls.CAT_1)
        enabling_condition.enabling_products.add(cls.PROD_3)
        enabling_condition.save()


    def add_category_enabling_condition(cls, mandatory=False):
        ''' Adds a category enabling condition: adding PROD_1 to a cart is
        predicated on adding an item from CAT_2 beforehand.'''
        enabling_condition = rego.CategoryEnablingCondition.objects.create(
            description="Category condition",
            mandatory=mandatory,
            enabling_category=cls.CAT_2,
        )
        enabling_condition.save()
        enabling_condition.products.add(cls.PROD_1)
        enabling_condition.save()


    def test_product_enabling_condition_enables_product(self):
        self.add_product_enabling_condition()

        # Cannot buy PROD_1 without buying PROD_2
        current_cart = CartController.for_user(self.USER_1)
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_1, 1)

        current_cart.add_to_cart(self.PROD_2, 1)
        current_cart.add_to_cart(self.PROD_1, 1)


    def test_product_enabled_by_product_in_previous_cart(self):
        self.add_product_enabling_condition()

        current_cart = CartController.for_user(self.USER_1)
        current_cart.add_to_cart(self.PROD_2, 1)
        current_cart.cart.active = False
        current_cart.cart.save()

        # Create new cart and try to add PROD_1
        current_cart = CartController.for_user(self.USER_1)
        current_cart.add_to_cart(self.PROD_1, 1)


    def test_product_enabling_condition_enables_category(self):
        self.add_product_enabling_condition_on_category()

        # Cannot buy PROD_1 without buying item from CAT_2
        current_cart = CartController.for_user(self.USER_1)
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_1, 1)

        current_cart.add_to_cart(self.PROD_3, 1)
        current_cart.add_to_cart(self.PROD_1, 1)


    def test_category_enabling_condition_enables_product(self):
        self.add_category_enabling_condition()

        # Cannot buy PROD_1 without buying PROD_2
        current_cart = CartController.for_user(self.USER_1)
        with self.assertRaises(ValidationError):
            current_cart.add_to_cart(self.PROD_1, 1)

        # PROD_3 is in CAT_2
        current_cart.add_to_cart(self.PROD_3, 1)
        current_cart.add_to_cart(self.PROD_1, 1)


    def test_product_enabled_by_category_in_previous_cart(self):
        self.add_category_enabling_condition()

        current_cart = CartController.for_user(self.USER_1)
        current_cart.add_to_cart(self.PROD_3, 1)
        current_cart.cart.active = False
        current_cart.cart.save()

        # Create new cart and try to add PROD_1
        current_cart = CartController.for_user(self.USER_1)
        current_cart.add_to_cart(self.PROD_1, 1)


    def test_multiple_non_mandatory_conditions(self):
        self.add_product_enabling_condition()
        self.add_category_enabling_condition()

        # User 1 is testing the product enabling condition
        cart_1 = CartController.for_user(self.USER_1)
        # Cannot add PROD_1 until a condition is met
        with self.assertRaises(ValidationError):
            cart_1.add_to_cart(self.PROD_1, 1)
        cart_1.add_to_cart(self.PROD_2, 1)
        cart_1.add_to_cart(self.PROD_1, 1)

        # User 2 is testing the category enabling condition
        cart_2 = CartController.for_user(self.USER_2)
        # Cannot add PROD_1 until a condition is met
        with self.assertRaises(ValidationError):
            cart_2.add_to_cart(self.PROD_1, 1)
        cart_2.add_to_cart(self.PROD_3, 1)
        cart_2.add_to_cart(self.PROD_1, 1)


    def test_multiple_mandatory_conditions(self):
        self.add_product_enabling_condition(mandatory=True)
        self.add_category_enabling_condition(mandatory=True)

        cart_1 = CartController.for_user(self.USER_1)
        # Cannot add PROD_1 until both conditions are met
        with self.assertRaises(ValidationError):
            cart_1.add_to_cart(self.PROD_1, 1)
        cart_1.add_to_cart(self.PROD_2, 1) # Meets the product condition
        with self.assertRaises(ValidationError):
            cart_1.add_to_cart(self.PROD_1, 1)
        cart_1.add_to_cart(self.PROD_3, 1) # Meets the category condition
        cart_1.add_to_cart(self.PROD_1, 1)


    def test_mandatory_conditions_are_mandatory(self):
        self.add_product_enabling_condition(mandatory=False)
        self.add_category_enabling_condition(mandatory=True)

        cart_1 = CartController.for_user(self.USER_1)
        # Cannot add PROD_1 until both conditions are met
        with self.assertRaises(ValidationError):
            cart_1.add_to_cart(self.PROD_1, 1)
        cart_1.add_to_cart(self.PROD_2, 1) # Meets the product condition
        with self.assertRaises(ValidationError):
            cart_1.add_to_cart(self.PROD_1, 1)
        cart_1.add_to_cart(self.PROD_3, 1) # Meets the category condition
        cart_1.add_to_cart(self.PROD_1, 1)
