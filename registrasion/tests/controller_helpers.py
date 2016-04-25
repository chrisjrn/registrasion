from registrasion.controllers.cart import CartController
from registrasion.controllers.credit_note import CreditNoteController
from registrasion.controllers.invoice import InvoiceController
from registrasion.models import commerce

from django.core.exceptions import ObjectDoesNotExist


class TestingCartController(CartController):

    def set_quantity(self, product, quantity, batched=False):
        ''' Sets the _quantity_ of the given _product_ in the cart to the given
        _quantity_. '''

        self.set_quantities(((product, quantity),))

    def add_to_cart(self, product, quantity):
        ''' Adds _quantity_ of the given _product_ to the cart. Raises
        ValidationError if constraints are violated.'''

        try:
            product_item = commerce.ProductItem.objects.get(
                cart=self.cart,
                product=product)
            old_quantity = product_item.quantity
        except ObjectDoesNotExist:
            old_quantity = 0
        self.set_quantity(product, old_quantity + quantity)

    def next_cart(self):
        if self.cart.status == commerce.Cart.STATUS_ACTIVE:
            self.cart.status = commerce.Cart.STATUS_PAID
            self.cart.save()


class TestingInvoiceController(InvoiceController):

    def pay(self, reference, amount, pre_validate=True):
        ''' Testing method for simulating an invoice paymenht by the given
        amount. '''

        if pre_validate:
            # Manual payments don't pre-validate; we should test that things
            # still work if we do silly things.
            self.validate_allowed_to_pay()

        ''' Adds a payment '''
        commerce.PaymentBase.objects.create(
            invoice=self.invoice,
            reference=reference,
            amount=amount,
        )

        self.update_status()


class TestingCreditNoteController(CreditNoteController):

    def refund(self):
        commerce.CreditNoteRefund.objects.create(
            parent=self.credit_note,
            reference="Whoops."
        )
