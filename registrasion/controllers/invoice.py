from decimal import Decimal
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Sum

from registrasion import models as rego

from cart import CartController


class InvoiceController(object):

    def __init__(self, invoice):
        self.invoice = invoice

    @classmethod
    def for_cart(cls, cart):
        ''' Returns an invoice object for a given cart at its current revision.
        If such an invoice does not exist, the cart is validated, and if valid,
        an invoice is generated.'''

        try:
            invoice = rego.Invoice.objects.get(
                cart=cart, cart_revision=cart.revision)
        except ObjectDoesNotExist:
            cart_controller = CartController(cart)
            cart_controller.validate_cart()  # Raises ValidationError on fail.
            invoice = cls._generate(cart)

        return InvoiceController(invoice)

    @classmethod
    def resolve_discount_value(cls, item):
        try:
            condition = rego.DiscountForProduct.objects.get(
                discount=item.discount,
                product=item.product
            )
        except ObjectDoesNotExist:
            condition = rego.DiscountForCategory.objects.get(
                discount=item.discount,
                category=item.product.category
            )
        if condition.percentage is not None:
            value = item.product.price * (condition.percentage / 100)
        else:
            value = condition.price
        return value

    @classmethod
    def _generate(cls, cart):
        ''' Generates an invoice for the given cart. '''
        invoice = rego.Invoice.objects.create(
            user=cart.user,
            cart=cart,
            cart_revision=cart.revision,
            value=Decimal()
        )
        invoice.save()

        # TODO: calculate line items.
        product_items = rego.ProductItem.objects.filter(cart=cart)
        discount_items = rego.DiscountItem.objects.filter(cart=cart)
        invoice_value = Decimal()
        for item in product_items:
            line_item = rego.LineItem.objects.create(
                invoice=invoice,
                description=item.product.name,
                quantity=item.quantity,
                price=item.product.price,
            )
            line_item.save()
            invoice_value += line_item.quantity * line_item.price

        for item in discount_items:

            line_item = rego.LineItem.objects.create(
                invoice=invoice,
                description=item.discount.description,
                quantity=item.quantity,
                price=cls.resolve_discount_value(item) * -1,
            )
            line_item.save()
            invoice_value += line_item.quantity * line_item.price

        # TODO: calculate line items from discounts
        invoice.value = invoice_value
        invoice.save()

        return invoice

    def is_valid(self):
        ''' Returns true if the attached invoice is not void and it represents
        a valid cart. '''
        if self.invoice.void:
            return False
        if self.invoice.cart is not None:
            if self.invoice.cart.revision != self.invoice.cart_revision:
                return False
        return True

    def void(self):
        ''' Voids the invoice. '''
        self.invoice.void = True

    def pay(self, reference, amount):
        ''' Pays the invoice by the given amount. If the payment
        equals the total on the invoice, finalise the invoice.
        (NB should be transactional.)
        '''
        if self.invoice.cart is not None:
            cart = CartController(self.invoice.cart)
            cart.validate_cart()  # Raises ValidationError if invalid

        ''' Adds a payment '''
        payment = rego.Payment.objects.create(
            invoice=self.invoice,
            reference=reference,
            amount=amount,
        )
        payment.save()

        payments = rego.Payment.objects .filter(invoice=self.invoice)
        agg = payments.aggregate(Sum("amount"))
        total = agg["amount__sum"]

        if total == self.invoice.value:
            self.invoice.paid = True

            cart = self.invoice.cart
            cart.active = False
            cart.save()

            self.invoice.save()
