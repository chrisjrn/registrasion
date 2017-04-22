import datetime

from registrasion.models import commerce

from registrasion.tests.controller_helpers import TestingCartController
from registrasion.tests.controller_helpers import TestingCreditNoteController
from registrasion.tests.controller_helpers import TestingInvoiceController


class TestHelperMixin(object):

    def _invoice_containing_prod_1(self, qty=1):
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, qty)

        return TestingInvoiceController.for_cart(self.reget(cart.cart))

    def _manual_invoice(self, value=1):
        items = [("Item", value)]
        due = datetime.timedelta(hours=1)
        inv = TestingInvoiceController.manual_invoice(self.USER_1, due, items)

        return TestingInvoiceController(inv)

    def _credit_note_for_invoice(self, invoice):
        note = commerce.CreditNote.objects.get(invoice=invoice)
        return TestingCreditNoteController(note)
