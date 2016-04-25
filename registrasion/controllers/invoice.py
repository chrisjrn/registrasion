from decimal import Decimal
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from registrasion.models import commerce
from registrasion.models import conditions
from registrasion.models import people

from cart import CartController
from credit_note import CreditNoteController
from for_id import ForId


class InvoiceController(ForId, object):

    __MODEL__ = commerce.Invoice

    def __init__(self, invoice):
        self.invoice = invoice
        self.update_status()
        self.update_validity()  # Make sure this invoice is up-to-date

    @classmethod
    def for_cart(cls, cart):
        ''' Returns an invoice object for a given cart at its current revision.
        If such an invoice does not exist, the cart is validated, and if valid,
        an invoice is generated.'''

        try:
            invoice = commerce.Invoice.objects.exclude(
                status=commerce.Invoice.STATUS_VOID,
            ).get(
                cart=cart,
                cart_revision=cart.revision,
            )
        except ObjectDoesNotExist:
            cart_controller = CartController(cart)
            cart_controller.validate_cart()  # Raises ValidationError on fail.

            cls.void_all_invoices(cart)
            invoice = cls._generate(cart)

        return cls(invoice)

    @classmethod
    def void_all_invoices(cls, cart):
        invoices = commerce.Invoice.objects.filter(cart=cart).all()
        for invoice in invoices:
            cls(invoice).void()

    @classmethod
    def resolve_discount_value(cls, item):
        try:
            condition = conditions.DiscountForProduct.objects.get(
                discount=item.discount,
                product=item.product
            )
        except ObjectDoesNotExist:
            condition = conditions.DiscountForCategory.objects.get(
                discount=item.discount,
                category=item.product.category
            )
        if condition.percentage is not None:
            value = item.product.price * (condition.percentage / 100)
        else:
            value = condition.price
        return value

    @classmethod
    @transaction.atomic
    def _generate(cls, cart):
        ''' Generates an invoice for the given cart. '''

        issued = timezone.now()
        reservation_limit = cart.reservation_duration + cart.time_last_updated
        # Never generate a due time that is before the issue time
        due = max(issued, reservation_limit)

        # Get the invoice recipient
        profile = people.AttendeeProfileBase.objects.get_subclass(
            id=cart.user.attendee.attendeeprofilebase.id,
        )
        recipient = profile.invoice_recipient()
        invoice = commerce.Invoice.objects.create(
            user=cart.user,
            cart=cart,
            cart_revision=cart.revision,
            status=commerce.Invoice.STATUS_UNPAID,
            value=Decimal(),
            issue_time=issued,
            due_time=due,
            recipient=recipient,
        )

        product_items = commerce.ProductItem.objects.filter(cart=cart)

        if len(product_items) == 0:
            raise ValidationError("Your cart is empty.")

        product_items = product_items.order_by(
            "product__category__order", "product__order"
        )
        discount_items = commerce.DiscountItem.objects.filter(cart=cart)
        invoice_value = Decimal()
        for item in product_items:
            product = item.product
            line_item = commerce.LineItem.objects.create(
                invoice=invoice,
                description="%s - %s" % (product.category.name, product.name),
                quantity=item.quantity,
                price=product.price,
                product=product,
            )
            invoice_value += line_item.quantity * line_item.price

        for item in discount_items:
            line_item = commerce.LineItem.objects.create(
                invoice=invoice,
                description=item.discount.description,
                quantity=item.quantity,
                price=cls.resolve_discount_value(item) * -1,
                product=item.product,
            )
            invoice_value += line_item.quantity * line_item.price

        invoice.value = invoice_value

        invoice.save()

        return invoice

    def can_view(self, user=None, access_code=None):
        ''' Returns true if the accessing user is allowed to view this invoice,
        or if the given access code matches this invoice's user's access code.
        '''

        if user == self.invoice.user:
            return True

        if user.is_staff:
            return True

        if self.invoice.user.attendee.access_code == access_code:
            return True

        return False

    def _refresh(self):
        ''' Refreshes the underlying invoice and cart objects. '''
        self.invoice.refresh_from_db()
        if self.invoice.cart:
            self.invoice.cart.refresh_from_db()

    def validate_allowed_to_pay(self):
        ''' Passes cleanly if we're allowed to pay, otherwise raise
        a ValidationError. '''

        self._refresh()

        if not self.invoice.is_unpaid:
            raise ValidationError("You can only pay for unpaid invoices.")

        if not self.invoice.cart:
            return

        if not self._invoice_matches_cart():
            raise ValidationError("The registration has been amended since "
                                  "generating this invoice.")

        CartController(self.invoice.cart).validate_cart()

    def total_payments(self):
        ''' Returns the total amount paid towards this invoice. '''

        payments = commerce.PaymentBase.objects.filter(invoice=self.invoice)
        total_paid = payments.aggregate(Sum("amount"))["amount__sum"] or 0
        return total_paid

    def update_status(self):
        ''' Updates the status of this invoice based upon the total
        payments.'''

        old_status = self.invoice.status
        total_paid = self.total_payments()
        num_payments = commerce.PaymentBase.objects.filter(
            invoice=self.invoice,
        ).count()
        remainder = self.invoice.value - total_paid

        if old_status == commerce.Invoice.STATUS_UNPAID:
            # Invoice had an amount owing
            if remainder <= 0:
                # Invoice no longer has amount owing
                self._mark_paid()

            elif total_paid == 0 and num_payments > 0:
                # Invoice has multiple payments totalling zero
                self._mark_void()
        elif old_status == commerce.Invoice.STATUS_PAID:
            if remainder > 0:
                # Invoice went from having a remainder of zero or less
                # to having a positive remainder -- must be a refund
                self._mark_refunded()
        elif old_status == commerce.Invoice.STATUS_REFUNDED:
            # Should not ever change from here
            pass
        elif old_status == commerce.Invoice.STATUS_VOID:
            # Should not ever change from here
            pass

        # Generate credit notes from residual payments
        residual = 0
        if self.invoice.is_paid:
            if remainder < 0:
                residual = 0 - remainder
        elif self.invoice.is_void or self.invoice.is_refunded:
            residual = total_paid

        if residual != 0:
            CreditNoteController.generate_from_invoice(self.invoice, residual)

    def _mark_paid(self):
        ''' Marks the invoice as paid, and updates the attached cart if
        necessary. '''
        cart = self.invoice.cart
        if cart:
            cart.status = commerce.Cart.STATUS_PAID
            cart.save()
        self.invoice.status = commerce.Invoice.STATUS_PAID
        self.invoice.save()

    def _mark_refunded(self):
        ''' Marks the invoice as refunded, and updates the attached cart if
        necessary. '''
        cart = self.invoice.cart
        if cart:
            cart.status = commerce.Cart.STATUS_RELEASED
            cart.save()
        self.invoice.status = commerce.Invoice.STATUS_REFUNDED
        self.invoice.save()

    def _mark_void(self):
        ''' Marks the invoice as refunded, and updates the attached cart if
        necessary. '''
        self.invoice.status = commerce.Invoice.STATUS_VOID
        self.invoice.save()

    def _invoice_matches_cart(self):
        ''' Returns true if there is no cart, or if the revision of this
        invoice matches the current revision of the cart. '''
        cart = self.invoice.cart
        if not cart:
            return True

        return cart.revision == self.invoice.cart_revision

    def update_validity(self):
        ''' Voids this invoice if the cart it is attached to has updated. '''
        if not self._invoice_matches_cart():
            self.void()

    def void(self):
        ''' Voids the invoice if it is valid to do so. '''
        if self.total_payments() > 0:
            raise ValidationError("Invoices with payments must be refunded.")
        elif self.invoice.is_refunded:
            raise ValidationError("Refunded invoices may not be voided.")
        self._mark_void()

    @transaction.atomic
    def refund(self):
        ''' Refunds the invoice by generating a CreditNote for the value of
        all of the payments against the cart.

        The invoice is marked as refunded, and the underlying cart is marked
        as released.

        '''

        if self.invoice.is_void:
            raise ValidationError("Void invoices cannot be refunded")

        # Raises a credit note fot the value of the invoice.
        amount = self.total_payments()

        if amount == 0:
            self.void()
            return

        CreditNoteController.generate_from_invoice(self.invoice, amount)
        self.update_status()
