import datetime
import pytz

from django.core.exceptions import ValidationError

from registrasion.models import commerce
from registrasion.tests.controller_helpers import TestingCartController
from registrasion.tests.controller_helpers import TestingInvoiceController
from registrasion.tests.test_helpers import TestHelperMixin

from registrasion.tests.test_cart import RegistrationCartTestCase


UTC = pytz.timezone('UTC')

HOURS = datetime.timedelta(hours=1)


class CreditNoteTestCase(TestHelperMixin, RegistrationCartTestCase):

    def test_overpaid_invoice_results_in_credit_note(self):
        invoice = self._invoice_containing_prod_1(1)

        # Invoice is overpaid by 1 unit
        to_pay = invoice.invoice.value + 1
        invoice.pay("Reference", to_pay)

        # The total paid should be equal to the value of the invoice only
        self.assertEqual(
            invoice.invoice.value, invoice.invoice.total_payments()
        )
        self.assertTrue(invoice.invoice.is_paid)

        # There should be a credit note generated out of the invoice.
        credit_notes = commerce.CreditNote.objects.filter(
            invoice=invoice.invoice,
        )
        self.assertEqual(1, credit_notes.count())
        self.assertEqual(to_pay - invoice.invoice.value, credit_notes[0].value)

    def test_full_paid_invoice_does_not_generate_credit_note(self):
        invoice = self._invoice_containing_prod_1(1)

        # Invoice is paid evenly
        invoice.pay("Reference", invoice.invoice.value)

        # The total paid should be equal to the value of the invoice only
        self.assertEqual(
            invoice.invoice.value, invoice.invoice.total_payments()
        )
        self.assertTrue(invoice.invoice.is_paid)

        # There should be no credit notes
        credit_notes = commerce.CreditNote.objects.filter(
            invoice=invoice.invoice,
        )
        self.assertEqual(0, credit_notes.count())

    def test_refund_partially_paid_invoice_generates_correct_credit_note(self):
        invoice = self._invoice_containing_prod_1(1)

        # Invoice is underpaid by 1 unit
        to_pay = invoice.invoice.value - 1
        invoice.pay("Reference", to_pay)
        invoice.refund()

        # The total paid should be zero
        self.assertEqual(0, invoice.invoice.total_payments())
        self.assertTrue(invoice.invoice.is_void)

        # There should be a credit note generated out of the invoice.
        credit_notes = commerce.CreditNote.objects.filter(
            invoice=invoice.invoice,
        )
        self.assertEqual(1, credit_notes.count())
        self.assertEqual(to_pay, credit_notes[0].value)

    def test_refund_fully_paid_invoice_generates_correct_credit_note(self):
        invoice = self._invoice_containing_prod_1(1)

        to_pay = invoice.invoice.value
        invoice.pay("Reference", to_pay)
        self.assertTrue(invoice.invoice.is_paid)

        invoice.refund()

        # The total paid should be zero
        self.assertEqual(0, invoice.invoice.total_payments())
        self.assertTrue(invoice.invoice.is_refunded)

        # There should be a credit note generated out of the invoice.
        credit_notes = commerce.CreditNote.objects.filter(
            invoice=invoice.invoice,
        )
        self.assertEqual(1, credit_notes.count())
        self.assertEqual(to_pay, credit_notes[0].value)

    def test_apply_credit_note_pays_invoice(self):

        # Create a manual invoice (stops credit notes from being auto-applied)
        self._manual_invoice(1)

        # Begin the test

        invoice = self._invoice_containing_prod_1(1)

        to_pay = invoice.invoice.value
        invoice.pay("Reference", to_pay)
        self.assertTrue(invoice.invoice.is_paid)

        invoice.refund()

        # There should be one credit note generated out of the invoice.
        cn = self._credit_note_for_invoice(invoice.invoice)

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

        # Create and refund an invoice, generating a credit note.
        invoice = self._invoice_containing_prod_1(2)

        invoice.pay("Reference", invoice.invoice.value)
        self.assertTrue(invoice.invoice.is_paid)

        invoice.refund()

        # There should be one credit note generated out of the invoice.
        cn = self._credit_note_for_invoice(invoice.invoice)  # noqa

        self.assertEquals(1, commerce.CreditNote.unclaimed().count())

        # Create a new invoice for a cart of half value of inv 1
        invoice2 = self._invoice_containing_prod_1(1)
        # Credit note is automatically applied by generating the new invoice
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

        # Disable auto-application of invoices.
        self._manual_invoice(1)

        # And now start the actual test.

        invoice = self._invoice_containing_prod_1(1)

        to_pay = invoice.invoice.value
        invoice.pay("Reference", to_pay)
        self.assertTrue(invoice.invoice.is_paid)

        invoice.refund()

        # There should be one credit note generated out of the invoice.
        cn = self._credit_note_for_invoice(invoice.invoice)

        # Create a new cart with invoice, pay it
        invoice_2 = self._invoice_containing_prod_1(1)
        invoice_2.pay("LOL", invoice_2.invoice.value)

        # Cannot pay paid invoice
        with self.assertRaises(ValidationError):
            cn.apply_to_invoice(invoice_2.invoice)

        invoice_2.refund()
        # Cannot pay refunded invoice
        with self.assertRaises(ValidationError):
            cn.apply_to_invoice(invoice_2.invoice)

        # Create a new cart with invoice
        invoice_2 = self._invoice_containing_prod_1(1)
        invoice_2.void()
        # Cannot pay void invoice
        with self.assertRaises(ValidationError):
            cn.apply_to_invoice(invoice_2.invoice)

    def test_cannot_apply_a_refunded_credit_note(self):
        invoice = self._invoice_containing_prod_1(1)

        to_pay = invoice.invoice.value
        invoice.pay("Reference", to_pay)
        self.assertTrue(invoice.invoice.is_paid)

        invoice.refund()

        self.assertEquals(1, commerce.CreditNote.unclaimed().count())

        cn = self._credit_note_for_invoice(invoice.invoice)

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
        invoice = self._invoice_containing_prod_1(1)

        to_pay = invoice.invoice.value
        invoice.pay("Reference", to_pay)
        self.assertTrue(invoice.invoice.is_paid)

        invoice.refund()

        self.assertEquals(1, commerce.CreditNote.unclaimed().count())

        cn = self._credit_note_for_invoice(invoice.invoice)

        # Create a new cart with invoice
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 1)

        invoice_2 = TestingInvoiceController.for_cart(self.reget(cart.cart))
        with self.assertRaises(ValidationError):
            # Creating `invoice_2` will automatically apply `cn`.
            cn.apply_to_invoice(invoice_2.invoice)

        self.assertEquals(0, commerce.CreditNote.unclaimed().count())

        # Cannot refund this credit note as it is already applied.
        with self.assertRaises(ValidationError):
            cn.refund()

    def test_money_into_void_invoice_generates_credit_note(self):
        invoice = self._invoice_containing_prod_1(1)
        invoice.void()

        val = invoice.invoice.value

        invoice.pay("Paying into the void.", val, pre_validate=False)
        cn = self._credit_note_for_invoice(invoice.invoice)
        self.assertEqual(val, cn.credit_note.value)

    def test_money_into_refunded_invoice_generates_credit_note(self):
        invoice = self._invoice_containing_prod_1(1)

        val = invoice.invoice.value

        invoice.pay("Paying the first time.", val)
        invoice.refund()

        cnval = val - 1
        invoice.pay("Paying into the void.", cnval, pre_validate=False)

        notes = commerce.CreditNote.objects.filter(invoice=invoice.invoice)
        notes = sorted(notes, key=lambda note: note.value)

        self.assertEqual(cnval, notes[0].value)
        self.assertEqual(val, notes[1].value)

    def test_money_into_paid_invoice_generates_credit_note(self):
        invoice = self._invoice_containing_prod_1(1)

        val = invoice.invoice.value

        invoice.pay("Paying the first time.", val)

        invoice.pay("Paying into the void.", val, pre_validate=False)
        cn = self._credit_note_for_invoice(invoice.invoice)
        self.assertEqual(val, cn.credit_note.value)

    def test_invoice_with_credit_note_applied_is_refunded(self):
        ''' Invoices with partial payments should void when cart is updated.

        Test for issue #64 -- applying a credit note to an invoice
        means that invoice cannot be voided, and new invoices cannot be
        created. '''

        invoice = self._invoice_containing_prod_1(1)

        # Now get a credit note
        invoice.pay("Lol", invoice.invoice.value)
        invoice.refund()
        cn = self._credit_note_for_invoice(invoice.invoice)

        # Create a cart of higher value than the credit note
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, 2)

        # Create a current invoice
        # This will automatically apply `cn` to the invoice
        invoice = TestingInvoiceController.for_cart(cart.cart)

        # Adding to cart will mean that the old invoice for this cart
        # will be invalidated. A new invoice should be generated.
        cart.add_to_cart(self.PROD_1, 1)
        invoice = TestingInvoiceController.for_id(invoice.invoice.id)
        invoice2 = TestingInvoiceController.for_cart(cart.cart)  # noqa
        cn2 = self._credit_note_for_invoice(invoice.invoice)

        invoice._refresh()

        # The first invoice should be refunded
        self.assertEquals(
            commerce.Invoice.STATUS_VOID,
            invoice.invoice.status,
        )

        # Both credit notes should be for the same amount
        self.assertEquals(
            cn.credit_note.value,
            cn2.credit_note.value,
        )

    def test_creating_invoice_automatically_applies_credit_note(self):
        ''' Single credit note is automatically applied to new invoices. '''

        invoice = self._invoice_containing_prod_1(1)
        invoice.pay("boop", invoice.invoice.value)
        invoice.refund()

        # Generate a new invoice to the same value as first invoice
        # Should be paid, because we're applying credit notes automatically
        invoice2 = self._invoice_containing_prod_1(1)
        self.assertTrue(invoice2.invoice.is_paid)

    def _generate_multiple_credit_notes(self):
        invoice1 = self._manual_invoice(11)
        invoice2 = self._manual_invoice(11)
        invoice1.pay("Pay", invoice1.invoice.value)
        invoice1.refund()
        invoice2.pay("Pay", invoice2.invoice.value)
        invoice2.refund()
        return invoice1.invoice.value + invoice2.invoice.value

    def test_mutiple_credit_notes_are_applied_when_generating_invoice_1(self):
        ''' Tests (1) that multiple credit notes are applied to new invoice.

        Sum of credit note values will be *LESS* than the new invoice.
        '''

        notes_value = self._generate_multiple_credit_notes()
        invoice = self._manual_invoice(notes_value + 1)

        self.assertEqual(notes_value, invoice.invoice.total_payments())
        self.assertTrue(invoice.invoice.is_unpaid)

        user_unclaimed = commerce.CreditNote.unclaimed()
        user_unclaimed = user_unclaimed.filter(invoice__user=self.USER_1)
        self.assertEqual(0, user_unclaimed.count())

    def test_mutiple_credit_notes_are_applied_when_generating_invoice_2(self):
        ''' Tests (2) that multiple credit notes are applied to new invoice.

        Sum of credit note values will be *GREATER* than the new invoice.
        '''

        notes_value = self._generate_multiple_credit_notes()
        invoice = self._manual_invoice(notes_value - 1)

        self.assertEqual(notes_value - 1, invoice.invoice.total_payments())
        self.assertTrue(invoice.invoice.is_paid)

        user_unclaimed = commerce.CreditNote.unclaimed().filter(
            invoice__user=self.USER_1
        )
        self.assertEqual(1, user_unclaimed.count())

        excess = self._credit_note_for_invoice(invoice.invoice)
        self.assertEqual(excess.credit_note.value, 1)

    def test_credit_notes_are_left_over_if_not_all_are_needed(self):
        ''' Tests that excess credit notes are untouched if they're not needed
        '''

        notes_value = self._generate_multiple_credit_notes()  # noqa
        notes_old = commerce.CreditNote.unclaimed().filter(
            invoice__user=self.USER_1
        )

        # Create a manual invoice whose value is smaller than any of the
        # credit notes we created
        invoice = self._manual_invoice(1)  # noqa
        notes_new = commerce.CreditNote.unclaimed().filter(
            invoice__user=self.USER_1
        )

        # Item is True if the note was't consumed when generating invoice.
        note_was_unused = [(i in notes_old) for i in notes_new]
        self.assertIn(True, note_was_unused)

    def test_credit_notes_are_not_applied_if_user_has_multiple_invoices(self):

        # Have an invoice pending with no credit notes; no payment will be made
        invoice1 = self._invoice_containing_prod_1(1)  # noqa
        # Create some credit notes.
        self._generate_multiple_credit_notes()

        invoice = self._manual_invoice(2)

        # Because there's already an invoice open for this user
        # The credit notes are not automatically applied.
        self.assertEqual(0, invoice.invoice.total_payments())
        self.assertTrue(invoice.invoice.is_unpaid)

    def test_credit_notes_are_applied_even_if_some_notes_are_claimed(self):

        for i in range(10):
            # Generate credit note
            invoice1 = self._manual_invoice(1)
            invoice1.pay("Pay", invoice1.invoice.value)
            invoice1.refund()

            # Generate invoice that should be automatically paid
            invoice2 = self._manual_invoice(1)
            self.assertTrue(invoice2.invoice.is_paid)

    def test_cancellation_fee_is_applied(self):

        invoice1 = self._manual_invoice(1)
        invoice1.pay("Pay", invoice1.invoice.value)
        invoice1.refund()

        percentage = 15

        cn = self._credit_note_for_invoice(invoice1.invoice)
        canc = cn.cancellation_fee(15)

        # Cancellation fee exceeds the amount for the invoice.
        self.assertTrue(canc.invoice.is_paid)

        # Cancellation fee is equal to 15% of credit note's value
        self.assertEqual(
            canc.invoice.value,
            cn.credit_note.value * percentage / 100
        )

    def test_cancellation_fee_is_applied_when_another_invoice_is_unpaid(self):

        extra_invoice = self._manual_invoice(23)  # noqa
        self.test_cancellation_fee_is_applied()
