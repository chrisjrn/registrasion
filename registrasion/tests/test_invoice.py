import datetime
import pytz

from decimal import Decimal
from django.core.exceptions import ValidationError

from registrasion import models as rego
from controller_helpers import TestingCartController
from controller_helpers import TestingInvoiceController

from test_cart import RegistrationCartTestCase

UTC = pytz.timezone('UTC')


class InvoiceTestCase(RegistrationCartTestCase):

    def test_create_invoice(self):
        current_cart = TestingCartController.for_user(self.USER_1)

        # Should be able to create an invoice after the product is added
        current_cart.add_to_cart(self.PROD_1, 1)
        invoice_1 = TestingInvoiceController.for_cart(current_cart.cart)
        # That invoice should have a single line item
        line_items = rego.LineItem.objects.filter(invoice=invoice_1.invoice)
        self.assertEqual(1, len(line_items))
        # That invoice should have a value equal to cost of PROD_1
        self.assertEqual(self.PROD_1.price, invoice_1.invoice.value)

        # Adding item to cart should produce a new invoice
        current_cart.add_to_cart(self.PROD_2, 1)
        invoice_2 = TestingInvoiceController.for_cart(current_cart.cart)
        self.assertNotEqual(invoice_1.invoice, invoice_2.invoice)

        # The old invoice should automatically be voided
        invoice_1_new = rego.Invoice.objects.get(pk=invoice_1.invoice.id)
        invoice_2_new = rego.Invoice.objects.get(pk=invoice_2.invoice.id)
        self.assertTrue(invoice_1_new.is_void)
        self.assertFalse(invoice_2_new.is_void)

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
        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.add_to_cart(self.PROD_1, 1)

        self.add_timedelta(self.RESERVATION * 2)
        cart_2 = TestingCartController.for_user(self.USER_2)
        cart_2.add_to_cart(self.PROD_1, 1)

        # Now try to invoice the first user
        with self.assertRaises(ValidationError):
            TestingInvoiceController.for_cart(current_cart.cart)

    def test_paying_invoice_makes_new_cart(self):
        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.add_to_cart(self.PROD_1, 1)

        invoice = TestingInvoiceController.for_cart(current_cart.cart)
        invoice.pay("A payment!", invoice.invoice.value)

        # This payment is for the correct amount invoice should be paid.
        self.assertTrue(invoice.invoice.is_paid)

        # Cart should not be active
        self.assertFalse(invoice.invoice.cart.active)

        # Asking for a cart should generate a new one
        new_cart = TestingCartController.for_user(self.USER_1)
        self.assertNotEqual(current_cart.cart, new_cart.cart)

    def test_invoice_includes_discounts(self):
        voucher = rego.Voucher.objects.create(
            recipient="Voucher recipient",
            code="VOUCHER",
            limit=1
        )
        discount = rego.VoucherDiscount.objects.create(
            description="VOUCHER RECIPIENT",
            voucher=voucher,
        )
        rego.DiscountForProduct.objects.create(
            discount=discount,
            product=self.PROD_1,
            percentage=Decimal(50),
            quantity=1
        )

        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.apply_voucher(voucher.code)

        # Should be able to create an invoice after the product is added
        current_cart.add_to_cart(self.PROD_1, 1)
        invoice_1 = TestingInvoiceController.for_cart(current_cart.cart)

        # That invoice should have two line items
        line_items = rego.LineItem.objects.filter(invoice=invoice_1.invoice)
        self.assertEqual(2, len(line_items))
        # That invoice should have a value equal to 50% of the cost of PROD_1
        self.assertEqual(
            self.PROD_1.price * Decimal("0.5"),
            invoice_1.invoice.value)

    def test_zero_value_invoice_is_automatically_paid(self):
        voucher = rego.Voucher.objects.create(
            recipient="Voucher recipient",
            code="VOUCHER",
            limit=1
        )
        discount = rego.VoucherDiscount.objects.create(
            description="VOUCHER RECIPIENT",
            voucher=voucher,
        )
        rego.DiscountForProduct.objects.create(
            discount=discount,
            product=self.PROD_1,
            percentage=Decimal(100),
            quantity=1
        )

        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.apply_voucher(voucher.code)

        # Should be able to create an invoice after the product is added
        current_cart.add_to_cart(self.PROD_1, 1)
        invoice_1 = TestingInvoiceController.for_cart(current_cart.cart)

        self.assertTrue(invoice_1.invoice.is_paid)

    def test_invoice_voids_self_if_cart_is_invalid(self):
        current_cart = TestingCartController.for_user(self.USER_1)

        # Should be able to create an invoice after the product is added
        current_cart.add_to_cart(self.PROD_1, 1)
        invoice_1 = TestingInvoiceController.for_cart(current_cart.cart)

        self.assertFalse(invoice_1.invoice.is_void)

        # Adding item to cart should produce a new invoice
        current_cart.add_to_cart(self.PROD_2, 1)
        invoice_2 = TestingInvoiceController.for_cart(current_cart.cart)
        self.assertNotEqual(invoice_1.invoice, invoice_2.invoice)

        # Viewing invoice_1's invoice should show it as void
        invoice_1_new = TestingInvoiceController(invoice_1.invoice)
        self.assertTrue(invoice_1_new.invoice.is_void)

        # Viewing invoice_2's invoice should *not* show it as void
        invoice_2_new = TestingInvoiceController(invoice_2.invoice)
        self.assertFalse(invoice_2_new.invoice.is_void)

    def test_voiding_invoice_creates_new_invoice(self):
        current_cart = TestingCartController.for_user(self.USER_1)

        # Should be able to create an invoice after the product is added
        current_cart.add_to_cart(self.PROD_1, 1)
        invoice_1 = TestingInvoiceController.for_cart(current_cart.cart)

        self.assertFalse(invoice_1.invoice.is_void)
        invoice_1.void()

        invoice_2 = TestingInvoiceController.for_cart(current_cart.cart)
        self.assertNotEqual(invoice_1.invoice, invoice_2.invoice)

    def test_cannot_pay_void_invoice(self):
        current_cart = TestingCartController.for_user(self.USER_1)

        # Should be able to create an invoice after the product is added
        current_cart.add_to_cart(self.PROD_1, 1)
        invoice_1 = TestingInvoiceController.for_cart(current_cart.cart)

        invoice_1.void()

        with self.assertRaises(ValidationError):
            invoice_1.validate_allowed_to_pay()

    def test_cannot_void_paid_invoice(self):
        current_cart = TestingCartController.for_user(self.USER_1)

        # Should be able to create an invoice after the product is added
        current_cart.add_to_cart(self.PROD_1, 1)
        invoice_1 = TestingInvoiceController.for_cart(current_cart.cart)

        invoice_1.pay("Reference", invoice_1.invoice.value)

        with self.assertRaises(ValidationError):
            invoice_1.void()

    def test_cannot_generate_blank_invoice(self):
        current_cart = TestingCartController.for_user(self.USER_1)
        with self.assertRaises(ValidationError):
            TestingInvoiceController.for_cart(current_cart.cart)

    def test_cannot_pay_implicitly_void_invoice(self):
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)
        invoice = TestingInvoiceController.for_cart(self.reget(cart.cart))

        # Implicitly void the invoice
        cart.add_to_cart(self.PROD_1, 1)

        with self.assertRaises(ValidationError):
            invoice.validate_allowed_to_pay()

    # TODO: test partially paid invoice cannot be void until payments
    # are refunded

    # TODO: test overpaid invoice results in credit note

    # TODO: test credit note generation more generally
