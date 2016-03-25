import pytz

from decimal import Decimal

from registrasion import models as rego
from registrasion.controllers.cart import CartController

from test_cart import RegistrationCartTestCase

UTC = pytz.timezone('UTC')


class DiscountTestCase(RegistrationCartTestCase):

    @classmethod
    def add_discount_prod_1_includes_prod_2(cls, amount=Decimal(100)):
        discount = rego.IncludedProductDiscount.objects.create(
            description="PROD_1 includes PROD_2 " + str(amount) + "%",
        )
        discount.save()
        discount.enabling_products.add(cls.PROD_1)
        discount.save()
        rego.DiscountForProduct.objects.create(
            discount=discount,
            product=cls.PROD_2,
            percentage=amount,
            quantity=2
        ).save()
        return discount

    @classmethod
    def add_discount_prod_1_includes_cat_2(
            cls,
            amount=Decimal(100),
            quantity=2):
        discount = rego.IncludedProductDiscount.objects.create(
            description="PROD_1 includes CAT_2 " + str(amount) + "%",
        )
        discount.save()
        discount.enabling_products.add(cls.PROD_1)
        discount.save()
        rego.DiscountForCategory.objects.create(
            discount=discount,
            category=cls.CAT_2,
            percentage=amount,
            quantity=quantity,
        ).save()
        return discount

    def test_discount_is_applied(self):
        self.add_discount_prod_1_includes_prod_2()

        cart = CartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)
        cart.add_to_cart(self.PROD_2, 1)

        # Discounts should be applied at this point...
        self.assertEqual(1, len(cart.cart.discountitem_set.all()))

    def test_discount_is_applied_for_category(self):
        self.add_discount_prod_1_includes_cat_2()

        cart = CartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)
        cart.add_to_cart(self.PROD_3, 1)

        # Discounts should be applied at this point...
        self.assertEqual(1, len(cart.cart.discountitem_set.all()))

    def test_discount_does_not_apply_if_not_met(self):
        self.add_discount_prod_1_includes_prod_2()

        cart = CartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_2, 1)

        # No discount should be applied as the condition is not met
        self.assertEqual(0, len(cart.cart.discountitem_set.all()))

    def test_discount_applied_out_of_order(self):
        self.add_discount_prod_1_includes_prod_2()

        cart = CartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_2, 1)
        cart.add_to_cart(self.PROD_1, 1)

        # No discount should be applied as the condition is not met
        self.assertEqual(1, len(cart.cart.discountitem_set.all()))

    def test_discounts_collapse(self):
        self.add_discount_prod_1_includes_prod_2()

        cart = CartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)
        cart.add_to_cart(self.PROD_2, 1)
        cart.add_to_cart(self.PROD_2, 1)

        # Discounts should be applied and collapsed at this point...
        self.assertEqual(1, len(cart.cart.discountitem_set.all()))

    def test_discounts_respect_quantity(self):
        self.add_discount_prod_1_includes_prod_2()

        cart = CartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)
        cart.add_to_cart(self.PROD_2, 3)

        # There should be three items in the cart, but only two should
        # attract a discount.
        discount_items = list(cart.cart.discountitem_set.all())
        self.assertEqual(2, discount_items[0].quantity)

    def test_multiple_discounts_apply_in_order(self):
        discount_full = self.add_discount_prod_1_includes_prod_2()
        discount_half = self.add_discount_prod_1_includes_prod_2(Decimal(50))

        cart = CartController.for_user(self.USER_1)
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
        cart = CartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)
        cart.cart.active = False
        cart.cart.save()

        # Use the discount in the second cart
        cart = CartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_2, 1)

        # The discount should be applied.
        self.assertEqual(1, len(cart.cart.discountitem_set.all()))
        cart.cart.active = False
        cart.cart.save()

        # The discount should respect the total quantity across all
        # of the user's carts.
        cart = CartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_2, 2)

        # Having one item in the second cart leaves one more item where
        # the discount is applicable. The discount should apply, but only for
        # quantity=1
        discount_items = list(cart.cart.discountitem_set.all())
        self.assertEqual(1, discount_items[0].quantity)

    def test_discount_applies_only_once_enabled(self):
        # Enable the discount during the first cart.
        cart = CartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)
        # This would exhaust discount if present
        cart.add_to_cart(self.PROD_2, 2)
        cart.cart.active = False
        cart.cart.save()

        self.add_discount_prod_1_includes_prod_2()
        cart = CartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_2, 2)

        discount_items = list(cart.cart.discountitem_set.all())
        self.assertEqual(2, discount_items[0].quantity)

    def test_category_discount_applies_once_per_category(self):
        self.add_discount_prod_1_includes_cat_2(quantity=1)
        cart = CartController.for_user(self.USER_1)
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
        cart = CartController.for_user(self.USER_1)
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
            cart = CartController.for_user(user)
            cart.add_to_cart(self.PROD_1, 1) # Enable the discount
            cart.add_to_cart(self.PROD_3, 1)

            discount_items = list(cart.cart.discountitem_set.all())
            # The discount is applied.
            self.assertEqual(1, len(discount_items))
