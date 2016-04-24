import datetime
import pytz

from decimal import Decimal
from django.core.exceptions import ValidationError

from registrasion.models import commerce
from registrasion.models import conditions
from registrasion.models import inventory
from controller_helpers import TestingCartController
from controller_helpers import TestingCreditNoteController
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
        current_cart = TestingCartController.for_user(self.USER_1)
        current_cart.add_to_cart(self.PROD_1, 1)

        invoice = TestingInvoiceController.for_cart(current_cart.cart)

        id_ = invoice.invoice.id

        invoice1 = TestingInvoiceController.for_id(id_)
        invoice2 = TestingInvoiceController.for_id(str(id_))

        self.assertEqual(invoice.invoice, invoice1.invoice)
        self.assertEqual(invoice.invoice, invoice2.invoice)

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

    def test_zero_value_invoice_is_automatically_paid(self):
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
        invoice = TestingInvoiceController.for_cart(current_cart.cart)

        invoice.pay("Reference", invoice.invoice.value)

        with self.assertRaises(ValidationError):
            invoice.void()

    def test_cannot_void_partially_paid_invoice(self):
        current_cart = TestingCartController.for_user(self.USER_1)

        # Should be able to create an invoice after the product is added
        current_cart.add_to_cart(self.PROD_1, 1)
        invoice = TestingInvoiceController.for_cart(current_cart.cart)

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

    def test_overpaid_invoice_results_in_credit_note(self):
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)

        invoice = TestingInvoiceController.for_cart(self.reget(cart.cart))

        # Invoice is overpaid by 1 unit
        to_pay = invoice.invoice.value + 1
        invoice.pay("Reference", to_pay)

        # The total paid should be equal to the value of the invoice only
        self.assertEqual(invoice.invoice.value, invoice.total_payments())
        self.assertTrue(invoice.invoice.is_paid)

        # There should be a credit note generated out of the invoice.
        credit_notes = commerce.CreditNote.objects.filter(
            invoice=invoice.invoice,
        )
        self.assertEqual(1, credit_notes.count())
        self.assertEqual(to_pay - invoice.invoice.value, credit_notes[0].value)

    def test_full_paid_invoice_does_not_generate_credit_note(self):
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)

        invoice = TestingInvoiceController.for_cart(self.reget(cart.cart))

        # Invoice is paid evenly
        invoice.pay("Reference", invoice.invoice.value)

        # The total paid should be equal to the value of the invoice only
        self.assertEqual(invoice.invoice.value, invoice.total_payments())
        self.assertTrue(invoice.invoice.is_paid)

        # There should be no credit notes
        credit_notes = commerce.CreditNote.objects.filter(
            invoice=invoice.invoice,
        )
        self.assertEqual(0, credit_notes.count())

    def test_refund_partially_paid_invoice_generates_correct_credit_note(self):
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)

        invoice = TestingInvoiceController.for_cart(self.reget(cart.cart))

        # Invoice is underpaid by 1 unit
        to_pay = invoice.invoice.value - 1
        invoice.pay("Reference", to_pay)
        invoice.refund()

        # The total paid should be zero
        self.assertEqual(0, invoice.total_payments())
        self.assertTrue(invoice.invoice.is_void)

        # There should be a credit note generated out of the invoice.
        credit_notes = commerce.CreditNote.objects.filter(
            invoice=invoice.invoice,
        )
        self.assertEqual(1, credit_notes.count())
        self.assertEqual(to_pay, credit_notes[0].value)

    def test_refund_fully_paid_invoice_generates_correct_credit_note(self):
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)

        invoice = TestingInvoiceController.for_cart(self.reget(cart.cart))

        to_pay = invoice.invoice.value
        invoice.pay("Reference", to_pay)
        self.assertTrue(invoice.invoice.is_paid)

        invoice.refund()

        # The total paid should be zero
        self.assertEqual(0, invoice.total_payments())
        self.assertTrue(invoice.invoice.is_refunded)

        # There should be a credit note generated out of the invoice.
        credit_notes = commerce.CreditNote.objects.filter(
            invoice=invoice.invoice,
        )
        self.assertEqual(1, credit_notes.count())
        self.assertEqual(to_pay, credit_notes[0].value)

    def test_apply_credit_note_pays_invoice(self):
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)

        invoice = TestingInvoiceController.for_cart(self.reget(cart.cart))

        to_pay = invoice.invoice.value
        invoice.pay("Reference", to_pay)
        self.assertTrue(invoice.invoice.is_paid)

        invoice.refund()

        # There should be one credit note generated out of the invoice.
        credit_note = commerce.CreditNote.objects.get(invoice=invoice.invoice)
        cn = TestingCreditNoteController(credit_note)

        # That credit note should be in the unclaimed pile
        self.assertEquals(1, commerce.CreditNote.unclaimed().count())

        # Create a new (identical) cart with invoice
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)

        invoice2 = TestingInvoiceController.for_cart(self.reget(cart.cart))

        cn.apply_to_invoice(invoice2.invoice)
        self.assertTrue(invoice2.invoice.is_paid)

        # That invoice should not show up as unclaimed any more
        self.assertEquals(0, commerce.CreditNote.unclaimed().count())

    def test_apply_credit_note_generates_new_credit_note_if_overpaying(self):
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 2)

        invoice = TestingInvoiceController.for_cart(self.reget(cart.cart))

        to_pay = invoice.invoice.value
        invoice.pay("Reference", to_pay)
        self.assertTrue(invoice.invoice.is_paid)

        invoice.refund()

        # There should be one credit note generated out of the invoice.
        credit_note = commerce.CreditNote.objects.get(invoice=invoice.invoice)
        cn = TestingCreditNoteController(credit_note)

        self.assertEquals(1, commerce.CreditNote.unclaimed().count())

        # Create a new cart (of half value of inv 1) and get invoice
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)

        invoice2 = TestingInvoiceController.for_cart(self.reget(cart.cart))

        cn.apply_to_invoice(invoice2.invoice)
        self.assertTrue(invoice2.invoice.is_paid)

        # We generated a new credit note, and spent the old one,
        # unclaimed should still be 1.
        self.assertEquals(1, commerce.CreditNote.unclaimed().count())

        credit_note2 = commerce.CreditNote.objects.get(
            invoice=invoice2.invoice,
        )

        # The new credit note should be the residual of the cost of cart 1
        # minus the cost of cart 2.
        self.assertEquals(
            invoice.invoice.value - invoice2.invoice.value,
            credit_note2.value,
        )

    def test_cannot_apply_credit_note_on_invalid_invoices(self):
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)

        invoice = TestingInvoiceController.for_cart(self.reget(cart.cart))

        to_pay = invoice.invoice.value
        invoice.pay("Reference", to_pay)
        self.assertTrue(invoice.invoice.is_paid)

        invoice.refund()

        # There should be one credit note generated out of the invoice.
        credit_note = commerce.CreditNote.objects.get(invoice=invoice.invoice)
        cn = TestingCreditNoteController(credit_note)

        # Create a new cart with invoice, pay it
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)

        invoice_2 = TestingInvoiceController.for_cart(self.reget(cart.cart))
        invoice_2.pay("LOL", invoice_2.invoice.value)

        # Cannot pay paid invoice
        with self.assertRaises(ValidationError):
            cn.apply_to_invoice(invoice_2.invoice)

        invoice_2.refund()
        # Cannot pay refunded invoice
        with self.assertRaises(ValidationError):
            cn.apply_to_invoice(invoice_2.invoice)

        # Create a new cart with invoice
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)

        invoice_2 = TestingInvoiceController.for_cart(self.reget(cart.cart))
        invoice_2.void()
        # Cannot pay void invoice
        with self.assertRaises(ValidationError):
            cn.apply_to_invoice(invoice_2.invoice)

    def test_cannot_apply_a_refunded_credit_note(self):
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)

        invoice = TestingInvoiceController.for_cart(self.reget(cart.cart))

        to_pay = invoice.invoice.value
        invoice.pay("Reference", to_pay)
        self.assertTrue(invoice.invoice.is_paid)

        invoice.refund()

        self.assertEquals(1, commerce.CreditNote.unclaimed().count())

        credit_note = commerce.CreditNote.objects.get(invoice=invoice.invoice)

        cn = TestingCreditNoteController(credit_note)
        cn.refund()

        # Refunding a credit note should mark it as claimed
        self.assertEquals(0, commerce.CreditNote.unclaimed().count())

        # Create a new cart with invoice
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)

        invoice_2 = TestingInvoiceController.for_cart(self.reget(cart.cart))

        # Cannot pay with this credit note.
        with self.assertRaises(ValidationError):
            cn.apply_to_invoice(invoice_2.invoice)

    def test_cannot_refund_an_applied_credit_note(self):
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)

        invoice = TestingInvoiceController.for_cart(self.reget(cart.cart))

        to_pay = invoice.invoice.value
        invoice.pay("Reference", to_pay)
        self.assertTrue(invoice.invoice.is_paid)

        invoice.refund()

        self.assertEquals(1, commerce.CreditNote.unclaimed().count())

        credit_note = commerce.CreditNote.objects.get(invoice=invoice.invoice)

        cn = TestingCreditNoteController(credit_note)

        # Create a new cart with invoice
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)

        invoice_2 = TestingInvoiceController.for_cart(self.reget(cart.cart))
        cn.apply_to_invoice(invoice_2.invoice)

        self.assertEquals(0, commerce.CreditNote.unclaimed().count())

        # Cannot refund this credit note as it is already applied.
        with self.assertRaises(ValidationError):
            cn.refund()
