import datetime
import pytz

from decimal import Decimal
from django.core.exceptions import ValidationError

from registrasion.models import commerce
from registrasion.models import conditions
from registrasion.models import inventory
from registrasion.tests.controller_helpers import TestingCartController
from registrasion.tests.controller_helpers import TestingInvoiceController
from registrasion.tests.test_helpers import TestHelperMixin

from registrasion.tests.test_cart import RegistrationCartTestCase

UTC = pytz.timezone('UTC')


class InvoiceTestCase(TestHelperMixin, RegistrationCartTestCase):

    def test_create_invoice(self):
        current_cart = TestingCartController.for_user(self.USER_1)

        # Should be able to create an invoice after the product is added
        current_cart.add_to_cart(self.PROD_1, 1)
        invoice_1 = TestingInvoiceController.for_cart(current_cart.cart)
        # That invoice should have a single line item
        line_items = commerce.LineItem.objects.filter(
            invoice=invoice_1.invoice,
        )
        self.assertEqual(1, len(line_items))
        # That invoice should have a value equal to cost of PROD_1
        self.assertEqual(self.PROD_1.price, invoice_1.invoice.value)

        # Adding item to cart should produce a new invoice
        current_cart.add_to_cart(self.PROD_2, 1)
        invoice_2 = TestingInvoiceController.for_cart(current_cart.cart)
        self.assertNotEqual(invoice_1.invoice, invoice_2.invoice)

        # The old invoice should automatically be voided
        invoice_1_new = commerce.Invoice.objects.get(pk=invoice_1.invoice.id)
        invoice_2_new = commerce.Invoice.objects.get(pk=invoice_2.invoice.id)
        self.assertTrue(invoice_1_new.is_void)
        self.assertFalse(invoice_2_new.is_void)

        # Invoice should have two line items
        line_items = commerce.LineItem.objects.filter(
            invoice=invoice_2.invoice,
        )
        self.assertEqual(2, len(line_items))
        # Invoice should have a value equal to cost of PROD_1 and PROD_2
        self.assertEqual(
            self.PROD_1.price + self.PROD_2.price,
            invoice_2.invoice.value)

    def test_invoice_controller_for_id_works(self):
        invoice = self._invoice_containing_prod_1(1)

        id_ = invoice.invoice.id

        invoice1 = TestingInvoiceController.for_id(id_)
        invoice2 = TestingInvoiceController.for_id(str(id_))

        self.assertEqual(invoice.invoice, invoice1.invoice)
        self.assertEqual(invoice.invoice, invoice2.invoice)

    def test_create_invoice_fails_if_cart_invalid(self):
        self.make_ceiling("Limit ceiling", limit=1)
        self.set_time(datetime.datetime(2015, 1, 1, tzinfo=UTC))
        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.add_to_cart(self.PROD_1, 1)

        self.add_timedelta(self.RESERVATION * 2)
        cart_2 = TestingCartController.for_user(self.USER_2)
        cart_2.add_to_cart(self.PROD_1, 1)

        # Now try to invoice the first user
        with self.assertRaises(ValidationError):
            TestingInvoiceController.for_cart(current_cart.cart)

    def test_paying_invoice_makes_new_cart(self):
        invoice = self._invoice_containing_prod_1(1)

        invoice.pay("A payment!", invoice.invoice.value)

        # This payment is for the correct amount invoice should be paid.
        self.assertTrue(invoice.invoice.is_paid)

        # Cart should not be active
        self.assertNotEqual(
            commerce.Cart.STATUS_ACTIVE,
            invoice.invoice.cart.status,
        )

        # Asking for a cart should generate a new one
        new_cart = TestingCartController.for_user(self.USER_1)
        self.assertNotEqual(invoice.invoice.cart, new_cart.cart)

    def test_total_payments_balance_due(self):
        invoice = self._invoice_containing_prod_1(2)
        for i in xrange(0, invoice.invoice.value):
            self.assertTrue(
                i + 1, invoice.invoice.total_payments()
            )
            self.assertTrue(
                invoice.invoice.value - i, invoice.invoice.balance_due()
            )
            invoice.pay("Pay 1", 1)

    def test_invoice_includes_discounts(self):
        voucher = inventory.Voucher.objects.create(
            recipient="Voucher recipient",
            code="VOUCHER",
            limit=1
        )
        discount = conditions.VoucherDiscount.objects.create(
            description="VOUCHER RECIPIENT",
            voucher=voucher,
        )
        conditions.DiscountForProduct.objects.create(
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
        line_items = commerce.LineItem.objects.filter(
            invoice=invoice_1.invoice,
        )
        self.assertEqual(2, len(line_items))
        # That invoice should have a value equal to 50% of the cost of PROD_1
        self.assertEqual(
            self.PROD_1.price * Decimal("0.5"),
            invoice_1.invoice.value)

    def _make_zero_value_invoice(self):
        voucher = inventory.Voucher.objects.create(
            recipient="Voucher recipient",
            code="VOUCHER",
            limit=1
        )
        discount = conditions.VoucherDiscount.objects.create(
            description="VOUCHER RECIPIENT",
            voucher=voucher,
        )
        conditions.DiscountForProduct.objects.create(
            discount=discount,
            product=self.PROD_1,
            percentage=Decimal(100),
            quantity=1
        )

        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.apply_voucher(voucher.code)

        # Should be able to create an invoice after the product is added
        current_cart.add_to_cart(self.PROD_1, 1)
        return TestingInvoiceController.for_cart(current_cart.cart)

    def test_zero_value_invoice_is_automatically_paid(self):
        invoice_1 = self._make_zero_value_invoice()
        self.assertTrue(invoice_1.invoice.is_paid)

    def test_refunding_zero_value_invoice_releases_cart(self):
        invoice_1 = self._make_zero_value_invoice()
        cart = invoice_1.invoice.cart
        invoice_1.refund()

        cart.refresh_from_db()
        self.assertEquals(commerce.Cart.STATUS_RELEASED, cart.status)

    def test_invoice_voids_self_if_cart_changes(self):
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

    def test_invoice_voids_self_if_cart_becomes_invalid(self):
        ''' Invoices should be void if cart becomes invalid over time '''

        self.make_ceiling("Limit ceiling", limit=1)
        self.set_time(datetime.datetime(
            year=2015, month=1, day=1, hour=0, minute=0, tzinfo=UTC,
        ))

        cart1 = TestingCartController.for_user(self.USER_1)
        cart2 = TestingCartController.for_user(self.USER_2)

        # Create a valid invoice for USER_1
        cart1.add_to_cart(self.PROD_1, 1)
        inv1 = TestingInvoiceController.for_cart(cart1.cart)

        # Expire the reservations, and have USER_2 take up PROD_1's ceiling
        # generate an invoice
        self.add_timedelta(self.RESERVATION * 2)
        cart2.add_to_cart(self.PROD_2, 1)
        TestingInvoiceController.for_cart(cart2.cart)

        # Re-get inv1's invoice; it should void itself on loading.
        inv1 = TestingInvoiceController(inv1.invoice)
        self.assertTrue(inv1.invoice.is_void)

    def test_voiding_invoice_creates_new_invoice(self):
        invoice_1 = self._invoice_containing_prod_1(1)

        self.assertFalse(invoice_1.invoice.is_void)
        invoice_1.void()

        invoice_2 = TestingInvoiceController.for_cart(invoice_1.invoice.cart)
        self.assertNotEqual(invoice_1.invoice, invoice_2.invoice)

    def test_cannot_pay_void_invoice(self):
        invoice_1 = self._invoice_containing_prod_1(1)

        invoice_1.void()

        with self.assertRaises(ValidationError):
            invoice_1.validate_allowed_to_pay()

    def test_cannot_void_paid_invoice(self):
        invoice = self._invoice_containing_prod_1(1)

        invoice.pay("Reference", invoice.invoice.value)

        with self.assertRaises(ValidationError):
            invoice.void()

    def test_cannot_void_partially_paid_invoice(self):
        invoice = self._invoice_containing_prod_1(1)

        invoice.pay("Reference", invoice.invoice.value - 1)
        self.assertTrue(invoice.invoice.is_unpaid)

        with self.assertRaises(ValidationError):
            invoice.void()

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

    def test_required_category_constraints_prevent_invoicing(self):
        self.CAT_1.required = True
        self.CAT_1.save()

        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_3, 1)

        # CAT_1 is required, we don't have CAT_1 yet
        with self.assertRaises(ValidationError):
            invoice = TestingInvoiceController.for_cart(cart.cart)

        # Now that we have CAT_1, we can check out the cart
        cart.add_to_cart(self.PROD_1, 1)
        invoice = TestingInvoiceController.for_cart(cart.cart)

        # Paying for the invoice should work fine
        invoice.pay("Boop", invoice.invoice.value)

        # We have an item in the first cart, so should be able to invoice
        # for the second cart, even without CAT_1 in it.
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_3, 1)

        invoice2 = TestingInvoiceController.for_cart(cart.cart)

        # Void invoice2, and release the first cart
        # now we don't have any CAT_1
        invoice2.void()
        invoice.refund()

        # Now that we don't have CAT_1, we can't checkout this cart
        with self.assertRaises(ValidationError):
            invoice = TestingInvoiceController.for_cart(cart.cart)

    def test_can_generate_manual_invoice(self):

        description_price_pairs = [
            ("Item 1", 15),
            ("Item 2", 30),
        ]

        due_delta = datetime.timedelta(hours=24)

        _invoice = TestingInvoiceController.manual_invoice(
            self.USER_1, due_delta, description_price_pairs
        )
        inv = TestingInvoiceController(_invoice)

        self.assertEquals(
            inv.invoice.value,
            sum(i[1] for i in description_price_pairs)
        )

        self.assertEquals(
            len(inv.invoice.lineitem_set.all()),
            len(description_price_pairs)
        )

        inv.pay("Demo payment", inv.invoice.value)

    def test_sends_email_on_invoice_creation(self):
        invoice = self._invoice_containing_prod_1(1)
        self.assertEquals(1, len(self.emails))
        email = self.emails[0]
        self.assertEquals([self.USER_1.email], email["to"])
        self.assertEquals("invoice_created", email["kind"])
        self.assertEquals(invoice.invoice, email["context"]["invoice"])

    def test_sends_first_change_email_on_invoice_fully_paid(self):
        invoice = self._invoice_containing_prod_1(1)

        self.assertEquals(1, len(self.emails))
        invoice.pay("Partial", invoice.invoice.value - 1)
        # Should have an "invoice_created" email and nothing else.
        self.assertEquals(1, len(self.emails))
        invoice.pay("Remainder", 1)
        self.assertEquals(2, len(self.emails))

        email = self.emails[1]
        self.assertEquals([self.USER_1.email], email["to"])
        self.assertEquals("invoice_updated", email["kind"])
        self.assertEquals(invoice.invoice, email["context"]["invoice"])

    def test_sends_email_when_invoice_refunded(self):
        invoice = self._invoice_containing_prod_1(1)

        self.assertEquals(1, len(self.emails))
        invoice.pay("Payment", invoice.invoice.value)
        self.assertEquals(2, len(self.emails))
        invoice.refund()
        self.assertEquals(3, len(self.emails))

        email = self.emails[2]
        self.assertEquals([self.USER_1.email], email["to"])
        self.assertEquals("invoice_updated", email["kind"])
        self.assertEquals(invoice.invoice, email["context"]["invoice"])
