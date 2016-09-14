from registrasion.models import commerce

from controller_helpers import TestingCartController
from controller_helpers import TestingCreditNoteController
from controller_helpers import TestingInvoiceController

class TestHelperMixin(object):

    def _invoice_containing_prod_1(self, qty=1):
        cart = TestingCartController.for_user(self.USER_1)
        cart.add_to_cart(self.PROD_1, qty)

        return TestingInvoiceController.for_cart(self.reget(cart.cart))

    def _credit_note_for_invoice(self, invoice):
        note = commerce.CreditNote.objects.get(invoice=invoice)
        return TestingCreditNoteController(note)
