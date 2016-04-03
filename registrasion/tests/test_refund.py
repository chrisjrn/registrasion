import pytz

from cart_controller_helper import TestingCartController
from registrasion.controllers.invoice import InvoiceController

from test_cart import RegistrationCartTestCase

UTC = pytz.timezone('UTC')


class RefundTestCase(RegistrationCartTestCase):

    def test_refund_marks_void_and_unpaid_and_cart_released(self):
        current_cart = TestingCartController.for_user(self.USER_1)

        # Should be able to create an invoice after the product is added
        current_cart.add_to_cart(self.PROD_1, 1)
        invoice = InvoiceController.for_cart(current_cart.cart)

        invoice.pay("A Payment!", invoice.invoice.value)
        self.assertFalse(invoice.invoice.void)
        self.assertTrue(invoice.invoice.paid)
        self.assertFalse(invoice.invoice.cart.released)

        invoice.refund("A Refund!", invoice.invoice.value)
        self.assertTrue(invoice.invoice.void)
        self.assertFalse(invoice.invoice.paid)
        self.assertTrue(invoice.invoice.cart.released)
