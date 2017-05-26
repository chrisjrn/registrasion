import datetime

from django.db import transaction

from registrasion.models import commerce

from .for_id import ForId


class CreditNoteController(ForId, object):

    __MODEL__ = commerce.CreditNote

    def __init__(self, credit_note):
        self.credit_note = credit_note

    @classmethod
    def generate_from_invoice(cls, invoice, value):
        ''' Generates a credit note of the specified value and pays it against
        the given invoice. You need to call InvoiceController.update_status()
        to set the status correctly, if appropriate. '''

        credit_note = commerce.CreditNote.objects.create(
            invoice=invoice,
            amount=0-value,  # Credit notes start off as a payment against inv.
            reference="ONE MOMENT",
        )
        credit_note.reference = "Generated credit note %d" % credit_note.id
        credit_note.save()

        return cls(credit_note)

    @transaction.atomic
    def apply_to_invoice(self, invoice):
        ''' Applies the total value of this credit note to the specified
        invoice. If this credit note overpays the invoice, a new credit note
        containing the residual value will be created.

        Raises ValidationError if the given invoice is not allowed to be
        paid.
        '''

        # Local import to fix import cycles. Can we do better?
        from .invoice import InvoiceController
        inv = InvoiceController(invoice)
        inv.validate_allowed_to_pay()

        # Apply payment to invoice
        commerce.CreditNoteApplication.objects.create(
            parent=self.credit_note,
            invoice=invoice,
            amount=self.credit_note.value,
            reference="Applied credit note #%d" % self.credit_note.id,
        )

        inv.update_status()

    # TODO: Add administration fee generator.
    @transaction.atomic
    def cancellation_fee(self, percentage):
        ''' Generates an invoice with a cancellation fee, and applies
        credit to the invoice.

        percentage (Decimal): The percentage of the credit note to turn into
        a cancellation fee. Must be 0 <= percentage <= 100.
        '''

        # Local import to fix import cycles. Can we do better?
        from .invoice import InvoiceController

        assert(percentage >= 0 and percentage <= 100)

        cancellation_fee = self.credit_note.value * percentage / 100
        due = datetime.timedelta(days=1)
        item = [("Cancellation fee", cancellation_fee)]
        invoice = InvoiceController.manual_invoice(
            self.credit_note.invoice.user, due, item
        )

        if not invoice.is_paid:
            self.apply_to_invoice(invoice)

        return InvoiceController(invoice)
