import datetime
import pytz

from decimal import Decimal
from django.core.exceptions import ValidationError

from registrasion import models as rego
from registrasion.controllers.cart import CartController
from registrasion.controllers.invoice import InvoiceController

from test_cart import RegistrationCartTestCase

UTC = pytz.timezone('UTC')


class InvoiceTestCase(RegistrationCartTestCase):

    def test_create_invoice(self):
        current_cart = CartController.for_user(self.USER_1)

        # Should be able to create an invoice after the product is added
        current_cart.add_to_cart(self.PROD_1, 1)
        invoice_1 = InvoiceController.for_cart(current_cart.cart)
        # That invoice should have a single line item
        line_items = rego.LineItem.objects.filter(invoice=invoice_1.invoice)
        self.assertEqual(1, len(line_items))
        # That invoice should have a value equal to cost of PROD_1
        self.assertEqual(self.PROD_1.price, invoice_1.invoice.value)

        # Adding item to cart should void all active invoices and produce
        # a new invoice
        current_cart.add_to_cart(self.PROD_2, 1)
        invoice_2 = InvoiceController.for_cart(current_cart.cart)
        self.assertNotEqual(invoice_1.invoice, invoice_2.invoice)
        # Invoice should have two line items
        line_items = rego.LineItem.objects.filter(invoice=invoice_2.invoice)
        self.assertEqual(2, len(line_items))
        # Invoice should have a value equal to cost of PROD_1 and PROD_2
        self.assertEqual(
            self.PROD_1.price + self.PROD_2.price,
            invoice_2.invoice.value)

    def test_create_invoice_fails_if_cart_invalid(self):
        self.make_ceiling("Limit ceiling", limit=1)
        self.set_time(datetime.datetime(2015, 01, 01, tzinfo=UTC))
        current_cart = CartController.for_user(self.USER_1)
        current_cart.add_to_cart(self.PROD_1, 1)

        self.add_timedelta(self.RESERVATION * 2)
        cart_2 = CartController.for_user(self.USER_2)
        cart_2.add_to_cart(self.PROD_1, 1)

        # Now try to invoice the first user
        with self.assertRaises(ValidationError):
            InvoiceController.for_cart(current_cart.cart)

    def test_paying_invoice_makes_new_cart(self):
        current_cart = CartController.for_user(self.USER_1)
        current_cart.add_to_cart(self.PROD_1, 1)

        invoice = InvoiceController.for_cart(current_cart.cart)
        invoice.pay("A payment!", invoice.invoice.value)

        # This payment is for the correct amount invoice should be paid.
        self.assertTrue(invoice.invoice.paid)

        # Cart should not be active
        self.assertFalse(invoice.invoice.cart.active)

        # Asking for a cart should generate a new one
        new_cart = CartController.for_user(self.USER_1)
        self.assertNotEqual(current_cart.cart, new_cart.cart)

    def test_invoice_includes_discounts(self):
        voucher = rego.Voucher.objects.create(
            recipient="Voucher recipient",
            code="VOUCHER",
            limit=1
        )
        voucher.save()
        discount = rego.VoucherDiscount.objects.create(
            description="VOUCHER RECIPIENT",
            voucher=voucher,
        )
        discount.save()
        rego.DiscountForProduct.objects.create(
            discount=discount,
            product=self.PROD_1,
            percentage=Decimal(50),
            quantity=1
        ).save()

        current_cart = CartController.for_user(self.USER_1)
        current_cart.apply_voucher(voucher)

        # Should be able to create an invoice after the product is added
        current_cart.add_to_cart(self.PROD_1, 1)
        invoice_1 = InvoiceController.for_cart(current_cart.cart)

        # That invoice should have two line items
        line_items = rego.LineItem.objects.filter(invoice=invoice_1.invoice)
        self.assertEqual(2, len(line_items))
        # That invoice should have a value equal to 50% of the cost of PROD_1
        self.assertEqual(
            self.PROD_1.price * Decimal("0.5"),
            invoice_1.invoice.value)
