from decimal import Decimal
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from registrasion.contrib.mail import send_email

from registrasion.models import commerce
from registrasion.models import conditions
from registrasion.models import people

from .cart import CartController
from .credit_note import CreditNoteController
from .for_id import ForId


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

        cart.refresh_from_db()
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

            cls.update_old_invoices(cart)
            invoice = cls._generate_from_cart(cart)

        return cls(invoice)

    @classmethod
    def update_old_invoices(cls, cart):
        invoices = commerce.Invoice.objects.filter(cart=cart).all()
        for invoice in invoices:
            cls(invoice).update_status()

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
    def manual_invoice(cls, user, due_delta, description_price_pairs):
        ''' Generates an invoice for arbitrary items, not held in a user's
        cart.

        Arguments:
            user (User): The user the invoice is being generated for.
            due_delta (datetime.timedelta): The length until the invoice is
                due.
            description_price_pairs ([(str, long or Decimal), ...]): A list of
                pairs. Each pair consists of the description for each line item
                and the price for that line item. The price will be cast to
                Decimal.

        Returns:
            an Invoice.
        '''

        line_items = []
        for description, price in description_price_pairs:
            line_item = commerce.LineItem(
                description=description,
                quantity=1,
                price=Decimal(price),
                product=None,
            )
            line_items.append(line_item)

        min_due_time = timezone.now() + due_delta
        return cls._generate(user, None, min_due_time, line_items)

    @classmethod
    @transaction.atomic
    def _generate_from_cart(cls, cart):
        ''' Generates an invoice for the given cart. '''

        cart.refresh_from_db()

        # Generate the line items from the cart.

        product_items = commerce.ProductItem.objects.filter(cart=cart)
        product_items = product_items.select_related(
            "product",
            "product__category",
        )
        product_items = product_items.order_by(
            "product__category__order", "product__order"
        )

        if len(product_items) == 0:
            raise ValidationError("Your cart is empty.")

        discount_items = commerce.DiscountItem.objects.filter(cart=cart)
        discount_items = discount_items.select_related(
            "discount",
            "product",
            "product__category",
        )

        def format_product(product):
            return "%s - %s" % (product.category.name, product.name)

        def format_discount(discount, product):
            description = discount.description
            return "%s (%s)" % (description, format_product(product))

        line_items = []

        for item in product_items:
            product = item.product
            line_item = commerce.LineItem(
                description=format_product(product),
                quantity=item.quantity,
                price=product.price,
                product=product,
            )
            line_items.append(line_item)
        for item in discount_items:
            line_item = commerce.LineItem(
                description=format_discount(item.discount, item.product),
                quantity=item.quantity,
                price=cls.resolve_discount_value(item) * -1,
                product=item.product,
            )
            line_items.append(line_item)

        # Generate the invoice

        min_due_time = cart.reservation_duration + cart.time_last_updated

        return cls._generate(cart.user, cart, min_due_time, line_items)

    @classmethod
    @transaction.atomic
    def _generate(cls, user, cart, min_due_time, line_items):

        # Never generate a due time that is before the issue time
        issued = timezone.now()
        due = max(issued, min_due_time)

        # Get the invoice recipient
        profile = people.AttendeeProfileBase.objects.get_subclass(
            id=user.attendee.attendeeprofilebase.id,
        )
        recipient = profile.invoice_recipient()

        invoice_value = sum(item.quantity * item.price for item in line_items)

        invoice = commerce.Invoice.objects.create(
            user=user,
            cart=cart,
            cart_revision=cart.revision if cart else None,
            status=commerce.Invoice.STATUS_UNPAID,
            value=invoice_value,
            issue_time=issued,
            due_time=due,
            recipient=recipient,
        )

        # Associate the line items with the invoice
        for line_item in line_items:
            line_item.invoice = invoice

        commerce.LineItem.objects.bulk_create(line_items)

        cls._apply_credit_notes(invoice)
        cls.email_on_invoice_creation(invoice)

        return invoice

    @classmethod
    def _apply_credit_notes(cls, invoice):
        ''' Applies the user's credit notes to the given invoice on creation.
        '''

        # We only automatically apply credit notes if this is the *only*
        # unpaid invoice for this user.
        invoices = commerce.Invoice.objects.filter(
            user=invoice.user,
            status=commerce.Invoice.STATUS_UNPAID,
        )
        if invoices.count() > 1:
            return

        notes = commerce.CreditNote.unclaimed().filter(
            invoice__user=invoice.user
        )
        for note in notes:
            try:
                CreditNoteController(note).apply_to_invoice(invoice)
            except ValidationError:
                # ValidationError will get raised once we're overpaying.
                break

        invoice.refresh_from_db()

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

    def update_status(self):
        ''' Updates the status of this invoice based upon the total
        payments.'''

        old_status = self.invoice.status
        total_paid = self.invoice.total_payments()
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

        self.email_on_invoice_change(
            self.invoice,
            old_status,
            self.invoice.status,
        )

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
        self._release_cart()
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

        self._refresh()

        cart = self.invoice.cart
        if not cart:
            return True

        return cart.revision == self.invoice.cart_revision

    def _release_cart(self):
        cart = self.invoice.cart
        if cart:
            cart.status = commerce.Cart.STATUS_RELEASED
            cart.save()

    def update_validity(self):
        ''' Voids this invoice if the attached cart is no longer valid because
        the cart revision has changed, or the reservations have expired. '''

        is_valid = self._invoice_matches_cart()
        cart = self.invoice.cart
        if self.invoice.is_unpaid and is_valid and cart:
            try:
                CartController(cart).validate_cart()
            except ValidationError:
                is_valid = False

        if not is_valid:
            if self.invoice.total_payments() > 0:
                # Free up the payments made to this invoice
                self.refund()
            else:
                self.void()

    def void(self):
        ''' Voids the invoice if it is valid to do so. '''
        if self.invoice.total_payments() > 0:
            raise ValidationError("Invoices with payments must be refunded.")
        elif self.invoice.is_refunded:
            raise ValidationError("Refunded invoices may not be voided.")
        if self.invoice.is_paid:
            self._release_cart()

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
        amount = self.invoice.total_payments()

        if amount == 0:
            self.void()
            return

        CreditNoteController.generate_from_invoice(self.invoice, amount)
        self.update_status()

    @classmethod
    def email(cls, invoice, kind):
        ''' Sends out an e-mail notifying the user about something to do
        with that invoice. '''

        context = {
            "invoice": invoice,
        }

        send_email([invoice.user.email], kind, context=context)

    @classmethod
    def email_on_invoice_creation(cls, invoice):
        ''' Sends out an e-mail notifying the user that an invoice has been
        created. '''

        cls.email(invoice, "invoice_created")

    @classmethod
    def email_on_invoice_change(cls, invoice, old_status, new_status):
        ''' Sends out all of the necessary notifications that the status of the
        invoice has changed to:

        - Invoice is now paid
        - Invoice is now refunded

        '''

        # The statuses that we don't care about.
        silent_status = [
            commerce.Invoice.STATUS_VOID,
            commerce.Invoice.STATUS_UNPAID,
        ]

        if old_status == new_status:
            return
        if False and new_status in silent_status:
            pass

        cls.email(invoice, "invoice_updated")
