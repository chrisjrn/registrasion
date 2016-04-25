import pytz

from controller_helpers import TestingCartController
from controller_helpers import TestingInvoiceController

from test_cart import RegistrationCartTestCase

from registrasion.models import commerce

UTC = pytz.timezone('UTC')


class RefundTestCase(RegistrationCartTestCase):

    def test_refund_marks_void_and_unpaid_and_cart_released(self):
        current_cart = TestingCartController.for_user(self.USER_1)

        # Should be able to create an invoice after the product is added
        current_cart.add_to_cart(self.PROD_1, 1)
        invoice = TestingInvoiceController.for_cart(current_cart.cart)

        invoice.pay("A Payment!", invoice.invoice.value)
        self.assertFalse(invoice.invoice.is_void)
        self.assertTrue(invoice.invoice.is_paid)
        self.assertFalse(invoice.invoice.is_refunded)
        self.assertNotEqual(
            commerce.Cart.STATUS_RELEASED,
            invoice.invoice.cart.status,
        )

        invoice.refund()
        self.assertFalse(invoice.invoice.is_void)
        self.assertFalse(invoice.invoice.is_paid)
        self.assertTrue(invoice.invoice.is_refunded)
        self.assertEqual(
            commerce.Cart.STATUS_RELEASED,
            invoice.invoice.cart.status,
        )
