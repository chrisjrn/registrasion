import pytz

from decimal import Decimal

from registrasion.models import commerce
from registrasion.models import conditions
from registrasion.controllers import discount
from controller_helpers import TestingCartController

from test_cart import RegistrationCartTestCase

UTC = pytz.timezone('UTC')


class DiscountTestCase(RegistrationCartTestCase):

    @classmethod
    def add_discount_prod_1_includes_prod_2(
            cls,
            amount=Decimal(100),
            quantity=2,
            ):
        discount = conditions.IncludedProductDiscount.objects.create(
            description="PROD_1 includes PROD_2 " + str(amount) + "%",
        )
        discount.enabling_products.add(cls.PROD_1)
        conditions.DiscountForProduct.objects.create(
            discount=discount,
            product=cls.PROD_2,
            percentage=amount,
            quantity=quantity,
        )
        return discount

    @classmethod
    def add_discount_prod_1_includes_cat_2(
            cls,
            amount=Decimal(100),
            quantity=2,
            ):
        discount = conditions.IncludedProductDiscount.objects.create(
            description="PROD_1 includes CAT_2 " + str(amount) + "%",
        )
        discount.enabling_products.add(cls.PROD_1)
        conditions.DiscountForCategory.objects.create(
            discount=discount,
            category=cls.CAT_2,
            percentage=amount,
            quantity=quantity,
        )
        return discount

    @classmethod
    def add_discount_prod_1_includes_prod_3_and_prod_4(
            cls,
            amount=Decimal(100),
            quantity=2,
            ):
        discount = conditions.IncludedProductDiscount.objects.create(
            description="PROD_1 includes PROD_3 and PROD_4 " +
                        str(amount) + "%",
        )
        discount.enabling_products.add(cls.PROD_1)
        conditions.DiscountForProduct.objects.create(
            discount=discount,
            product=cls.PROD_3,
            percentage=amount,
            quantity=quantity,
        )
        conditions.DiscountForProduct.objects.create(
            discount=discount,
            product=cls.PROD_4,
            percentage=amount,
            quantity=quantity,
        )
        return discount

    def test_discount_is_applied(self):
        self.add_discount_prod_1_includes_prod_2()

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)
        cart.add_to_cart(self.PROD_2, 1)

        # Discounts should be applied at this point...
        self.assertEqual(1, len(cart.cart.discountitem_set.all()))

    def test_discount_is_applied_for_category(self):
        self.add_discount_prod_1_includes_cat_2()

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)
        cart.add_to_cart(self.PROD_3, 1)

        # Discounts should be applied at this point...
        self.assertEqual(1, len(cart.cart.discountitem_set.all()))

    def test_discount_does_not_apply_if_not_met(self):
        self.add_discount_prod_1_includes_prod_2()

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_2, 1)

        # No discount should be applied as the condition is not met
        self.assertEqual(0, len(cart.cart.discountitem_set.all()))

    def test_discount_applied_out_of_order(self):
        self.add_discount_prod_1_includes_prod_2()

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_2, 1)
        cart.add_to_cart(self.PROD_1, 1)

        # No discount should be applied as the condition is not met
        self.assertEqual(1, len(cart.cart.discountitem_set.all()))

    def test_discounts_collapse(self):
        self.add_discount_prod_1_includes_prod_2()

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)
        cart.add_to_cart(self.PROD_2, 1)
        cart.add_to_cart(self.PROD_2, 1)

        # Discounts should be applied and collapsed at this point...
        self.assertEqual(1, len(cart.cart.discountitem_set.all()))

    def test_discounts_respect_quantity(self):
        self.add_discount_prod_1_includes_prod_2()

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)
        cart.add_to_cart(self.PROD_2, 3)

        # There should be three items in the cart, but only two should
        # attract a discount.
        discount_items = list(cart.cart.discountitem_set.all())
        self.assertEqual(2, discount_items[0].quantity)

    def test_multiple_discounts_apply_in_order(self):
        discount_full = self.add_discount_prod_1_includes_prod_2()
        discount_half = self.add_discount_prod_1_includes_prod_2(Decimal(50))

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)
        cart.add_to_cart(self.PROD_2, 3)

        # There should be two discounts
        discount_items = list(cart.cart.discountitem_set.all())
        discount_items.sort(key=lambda item: item.quantity)
        self.assertEqual(2, len(discount_items))
        # The half discount should be applied only once
        self.assertEqual(1, discount_items[0].quantity)
        self.assertEqual(discount_half.pk, discount_items[0].discount.pk)
        # The full discount should be applied twice
        self.assertEqual(2, discount_items[1].quantity)
        self.assertEqual(discount_full.pk, discount_items[1].discount.pk)

    def test_discount_applies_across_carts(self):
        self.add_discount_prod_1_includes_prod_2()

        # Enable the discount during the first cart.
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)

        cart.next_cart()

        # Use the discount in the second cart
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_2, 1)

        # The discount should be applied.
        self.assertEqual(1, len(cart.cart.discountitem_set.all()))

        cart.next_cart()

        # The discount should respect the total quantity across all
        # of the user's carts.
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_2, 2)

        # Having one item in the second cart leaves one more item where
        # the discount is applicable. The discount should apply, but only for
        # quantity=1
        discount_items = list(cart.cart.discountitem_set.all())
        self.assertEqual(1, discount_items[0].quantity)

    def test_discount_applies_only_once_enabled(self):
        # Enable the discount during the first cart.
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)
        # This would exhaust discount if present
        cart.add_to_cart(self.PROD_2, 2)

        cart.next_cart()

        self.add_discount_prod_1_includes_prod_2()
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_2, 2)

        discount_items = list(cart.cart.discountitem_set.all())
        self.assertEqual(2, discount_items[0].quantity)

    def test_category_discount_applies_once_per_category(self):
        self.add_discount_prod_1_includes_cat_2(quantity=1)
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)

        # Add two items from category 2
        cart.add_to_cart(self.PROD_3, 1)
        cart.add_to_cart(self.PROD_4, 1)

        discount_items = list(cart.cart.discountitem_set.all())
        # There is one discount, and it should apply to one item.
        self.assertEqual(1, len(discount_items))
        self.assertEqual(1, discount_items[0].quantity)

    def test_category_discount_applies_to_highest_value(self):
        self.add_discount_prod_1_includes_cat_2(quantity=1)
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)

        # Add two items from category 2, add the less expensive one first
        cart.add_to_cart(self.PROD_4, 1)
        cart.add_to_cart(self.PROD_3, 1)

        discount_items = list(cart.cart.discountitem_set.all())
        # There is one discount, and it should apply to the more expensive.
        self.assertEqual(1, len(discount_items))
        self.assertEqual(self.PROD_3, discount_items[0].product)

    def test_discount_quantity_is_per_user(self):
        self.add_discount_prod_1_includes_cat_2(quantity=1)

        # Both users should be able to apply the same discount
        # in the same way
        for user in (self.USER_1, self.USER_2):
            cart = TestingCartController.for_user(user)
            cart.add_to_cart(self.PROD_1, 1)  # Enable the discount
            cart.add_to_cart(self.PROD_3, 1)

            discount_items = list(cart.cart.discountitem_set.all())
            # The discount is applied.
            self.assertEqual(1, len(discount_items))

    # Tests for the discount.available_discounts enumerator
    def test_enumerate_no_discounts_for_no_input(self):
        discounts = discount.available_discounts(self.USER_1, [], [])
        self.assertEqual(0, len(discounts))

    def test_enumerate_no_discounts_if_condition_not_met(self):
        self.add_discount_prod_1_includes_cat_2(quantity=1)

        discounts = discount.available_discounts(
            self.USER_1,
            [],
            [self.PROD_3],
        )
        self.assertEqual(0, len(discounts))

        discounts = discount.available_discounts(self.USER_1, [self.CAT_2], [])
        self.assertEqual(0, len(discounts))

    def test_category_discount_appears_once_if_met_twice(self):
        self.add_discount_prod_1_includes_cat_2(quantity=1)

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)  # Enable the discount

        discounts = discount.available_discounts(
            self.USER_1,
            [self.CAT_2],
            [self.PROD_3],
        )
        self.assertEqual(1, len(discounts))

    def test_category_discount_appears_with_category(self):
        self.add_discount_prod_1_includes_cat_2(quantity=1)

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)  # Enable the discount

        discounts = discount.available_discounts(self.USER_1, [self.CAT_2], [])
        self.assertEqual(1, len(discounts))

    def test_category_discount_appears_with_product(self):
        self.add_discount_prod_1_includes_cat_2(quantity=1)

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)  # Enable the discount

        discounts = discount.available_discounts(
            self.USER_1,
            [],
            [self.PROD_3],
        )
        self.assertEqual(1, len(discounts))

    def test_category_discount_appears_once_with_two_valid_product(self):
        self.add_discount_prod_1_includes_cat_2(quantity=1)

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)  # Enable the discount

        discounts = discount.available_discounts(
            self.USER_1,
            [],
            [self.PROD_3, self.PROD_4]
        )
        self.assertEqual(1, len(discounts))

    def test_product_discount_appears_with_product(self):
        self.add_discount_prod_1_includes_prod_2(quantity=1)

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)  # Enable the discount

        discounts = discount.available_discounts(
            self.USER_1,
            [],
            [self.PROD_2],
        )
        self.assertEqual(1, len(discounts))

    def test_product_discount_does_not_appear_with_category(self):
        self.add_discount_prod_1_includes_prod_2(quantity=1)

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)  # Enable the discount

        discounts = discount.available_discounts(self.USER_1, [self.CAT_1], [])
        self.assertEqual(0, len(discounts))

    def test_discount_quantity_is_correct_before_first_purchase(self):
        self.add_discount_prod_1_includes_cat_2(quantity=2)

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)  # Enable the discount
        cart.add_to_cart(self.PROD_3, 1)  # Exhaust the quantity

        discounts = discount.available_discounts(self.USER_1, [self.CAT_2], [])
        self.assertEqual(2, discounts[0].quantity)

        cart.next_cart()

    def test_discount_quantity_is_correct_after_first_purchase(self):
        self.test_discount_quantity_is_correct_before_first_purchase()

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_3, 1)  # Exhaust the quantity

        discounts = discount.available_discounts(self.USER_1, [self.CAT_2], [])
        self.assertEqual(1, discounts[0].quantity)

        cart.next_cart()

    def test_discount_is_gone_after_quantity_exhausted(self):
        self.test_discount_quantity_is_correct_after_first_purchase()
        discounts = discount.available_discounts(self.USER_1, [self.CAT_2], [])
        self.assertEqual(0, len(discounts))

    def test_product_discount_enabled_twice_appears_twice(self):
        self.add_discount_prod_1_includes_prod_3_and_prod_4(quantity=2)
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)  # Enable the discount
        discounts = discount.available_discounts(
            self.USER_1,
            [],
            [self.PROD_3, self.PROD_4],
        )
        self.assertEqual(2, len(discounts))

    def test_discounts_are_released_by_refunds(self):
        self.add_discount_prod_1_includes_prod_2(quantity=2)
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)  # Enable the discount
        discounts = discount.available_discounts(
            self.USER_1,
            [],
            [self.PROD_2],
        )
        self.assertEqual(1, len(discounts))

        cart.next_cart()

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_2, 2)  # The discount will be exhausted

        cart.next_cart()

        discounts = discount.available_discounts(
            self.USER_1,
            [],
            [self.PROD_2],
        )
        self.assertEqual(0, len(discounts))

        cart.cart.status = commerce.Cart.STATUS_RELEASED
        cart.cart.save()

        discounts = discount.available_discounts(
            self.USER_1,
            [],
            [self.PROD_2],
        )
        self.assertEqual(1, len(discounts))
