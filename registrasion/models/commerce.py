from . import conditions
from . import inventory

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _
from model_utils.managers import InheritanceManager


# Commerce Models

@python_2_unicode_compatible
class Cart(models.Model):
    ''' Represents a set of product items that have been purchased, or are
    pending purchase. '''

    class Meta:
        app_label = "registrasion"
        index_together = [
            ("status", "time_last_updated"),
            ("status", "user"),
        ]

    def __str__(self):
        return "%d rev #%d" % (self.id, self.revision)

    STATUS_ACTIVE = 1
    STATUS_PAID = 2
    STATUS_RELEASED = 3

    STATUS_TYPES = [
        (STATUS_ACTIVE, _("Active")),
        (STATUS_PAID, _("Paid")),
        (STATUS_RELEASED, _("Released")),
    ]

    user = models.ForeignKey(User)
    # ProductItems (foreign key)
    vouchers = models.ManyToManyField(inventory.Voucher, blank=True)
    time_last_updated = models.DateTimeField(
        db_index=True,
    )
    reservation_duration = models.DurationField()
    revision = models.PositiveIntegerField(default=1)
    status = models.IntegerField(
        choices=STATUS_TYPES,
        db_index=True,
        default=STATUS_ACTIVE,
    )

    @classmethod
    def reserved_carts(cls):
        ''' Gets all carts that are 'reserved' '''
        return Cart.objects.filter(
            (Q(status=Cart.STATUS_ACTIVE) &
                Q(time_last_updated__gt=(
                    timezone.now()-F('reservation_duration')
                                        ))) |
            Q(status=Cart.STATUS_PAID)
        )


@python_2_unicode_compatible
class ProductItem(models.Model):
    ''' Represents a product-quantity pair in a Cart. '''

    class Meta:
        app_label = "registrasion"
        ordering = ("product", )

    def __str__(self):
        return "product: %s * %d in Cart: %s" % (
            self.product, self.quantity, self.cart)

    cart = models.ForeignKey(Cart)
    product = models.ForeignKey(inventory.Product)
    quantity = models.PositiveIntegerField(db_index=True)


@python_2_unicode_compatible
class DiscountItem(models.Model):
    ''' Represents a discount-product-quantity relation in a Cart. '''

    class Meta:
        app_label = "registrasion"
        ordering = ("product", )

    def __str__(self):
        return "%s: %s * %d in Cart: %s" % (
            self.discount, self.product, self.quantity, self.cart)

    cart = models.ForeignKey(Cart)
    product = models.ForeignKey(inventory.Product)
    discount = models.ForeignKey(conditions.DiscountBase)
    quantity = models.PositiveIntegerField()


@python_2_unicode_compatible
class Invoice(models.Model):
    ''' An invoice. Invoices can be automatically generated when checking out
    a Cart, in which case, it is attached to a given revision of a Cart.

    Attributes:

        user (User): The owner of this invoice.

        cart (commerce.Cart): The cart that was used to generate this invoice.

        cart_revision (int): The value of ``cart.revision`` at the time of this
            invoice's creation. If a change is made to the underlying cart,
            this invoice is automatically void -- this change is detected
            when ``cart.revision != cart_revision``.

        status (int): One of ``STATUS_UNPAID``, ``STATUS_PAID``,
            ``STATUS_REFUNDED``, OR ``STATUS_VOID``. Call
            ``get_status_display`` for a human-readable representation.

        recipient (str): A rendered representation of the invoice's recipient.

        issue_time (datetime): When the invoice was issued.

        due_time (datetime): When the invoice is due.

        value (Decimal): The total value of the line items attached to the
            invoice.

        lineitem_set (Queryset[LineItem]): The set of line items that comprise
            this invoice.

        paymentbase_set(Queryset[PaymentBase]): The set of PaymentBase objects
            that have been applied to this invoice.

    '''

    class Meta:
        app_label = "registrasion"

    STATUS_UNPAID = 1
    STATUS_PAID = 2
    STATUS_REFUNDED = 3
    STATUS_VOID = 4

    STATUS_TYPES = [
        (STATUS_UNPAID, _("Unpaid")),
        (STATUS_PAID, _("Paid")),
        (STATUS_REFUNDED, _("Refunded")),
        (STATUS_VOID, _("VOID")),
    ]

    def __str__(self):
        return "Invoice #%d" % self.id

    def clean(self):
        if self.cart is not None and self.cart_revision is None:
            raise ValidationError(
                "If this is a cart invoice, it must have a revision")

    @property
    def is_unpaid(self):
        return self.status == self.STATUS_UNPAID

    @property
    def is_void(self):
        return self.status == self.STATUS_VOID

    @property
    def is_paid(self):
        return self.status == self.STATUS_PAID

    @property
    def is_refunded(self):
        return self.status == self.STATUS_REFUNDED

    # Invoice Number
    user = models.ForeignKey(User)
    cart = models.ForeignKey(Cart, null=True)
    cart_revision = models.IntegerField(
        null=True,
        db_index=True,
    )
    # Line Items (foreign key)
    status = models.IntegerField(
        choices=STATUS_TYPES,
        db_index=True,
    )
    recipient = models.CharField(max_length=1024)
    issue_time = models.DateTimeField()
    due_time = models.DateTimeField()
    value = models.DecimalField(max_digits=8, decimal_places=2)


@python_2_unicode_compatible
class LineItem(models.Model):
    ''' Line items for an invoice. These are denormalised from the ProductItems
    and DiscountItems that belong to a cart (for consistency), but also allow
    for arbitrary line items when required.

    Attributes:

        invoice (commerce.Invoice): The invoice to which this LineItem is
            attached.

        description (str): A human-readable description of the line item.

        quantity (int): The quantity of items represented by this line.

        price (Decimal): The per-unit price for this line item.

        product (Optional[inventory.Product]): The product that this LineItem
            applies to. This allows you to do reports on sales and applied
            discounts to individual products.

    '''

    class Meta:
        app_label = "registrasion"
        ordering = ("id", )

    def __str__(self):
        return "Line: %s * %d @ %s" % (
            self.description, self.quantity, self.price)

    invoice = models.ForeignKey(Invoice)
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=8, decimal_places=2)
    product = models.ForeignKey(inventory.Product, null=True, blank=True)


@python_2_unicode_compatible
class PaymentBase(models.Model):
    ''' The base payment type for invoices. Payment apps should subclass this
    class to handle implementation-specific issues.

    Attributes:
        invoice (inventory.Invoice): The invoice that this payment applies to.

        time (datetime): The time that this payment was generated. Note that
            this will default to the current time when the model is created.

        reference (str): A human-readable reference for the payment, this will
            be displayed alongside the invoice.

        amount (Decimal): The amount the payment is for.

    '''

    class Meta:
        ordering = ("time", )

    objects = InheritanceManager()

    def __str__(self):
        return "Payment: ref=%s amount=%s" % (self.reference, self.amount)

    invoice = models.ForeignKey(Invoice)
    time = models.DateTimeField(default=timezone.now)
    reference = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=8, decimal_places=2)


class ManualPayment(PaymentBase):
    ''' Payments that are manually entered by staff. '''

    class Meta:
        app_label = "registrasion"

    entered_by = models.ForeignKey(User)


class CreditNote(PaymentBase):
    ''' Credit notes represent money accounted for in the system that do not
    belong to specific invoices. They may be paid into other invoices, or
    cashed out as refunds.

    Each CreditNote may either be used to pay towards another Invoice in the
    system (by attaching a CreditNoteApplication), or may be marked as
    refunded (by attaching a CreditNoteRefund).'''

    class Meta:
        app_label = "registrasion"

    @classmethod
    def unclaimed(cls):
        return cls.objects.filter(
            creditnoteapplication=None,
            creditnoterefund=None,
        )

    @property
    def status(self):
        if self.is_unclaimed:
            return "Unclaimed"

        if hasattr(self, 'creditnoteapplication'):
            destination = self.creditnoteapplication.invoice.id
            return "Applied to invoice %d" % destination

        elif hasattr(self, 'creditnoterefund'):
            reference = self.creditnoterefund.reference
            print reference
            return "Refunded with reference: %s" % reference

        raise ValueError("This should never happen.")

    @property
    def is_unclaimed(self):
        return not (
            hasattr(self, 'creditnoterefund') or
            hasattr(self, 'creditnoteapplication')
        )

    @property
    def value(self):
        ''' Returns the value of the credit note. Because CreditNotes are
        implemented as PaymentBase objects internally, the amount is a
        negative payment against an invoice. '''
        return -self.amount


class CleanOnSave(object):

    def save(self, *a, **k):
        self.full_clean()
        super(CleanOnSave, self).save(*a, **k)


class CreditNoteApplication(CleanOnSave, PaymentBase):
    ''' Represents an application of a credit note to an Invoice. '''

    class Meta:
        app_label = "registrasion"

    def clean(self):
        if not hasattr(self, "parent"):
            return
        if hasattr(self.parent, 'creditnoterefund'):
            raise ValidationError(
                "Cannot apply a refunded credit note to an invoice"
            )

    parent = models.OneToOneField(CreditNote)


class CreditNoteRefund(CleanOnSave, models.Model):
    ''' Represents a refund of a credit note to an external payment.
    Credit notes may only be refunded in full. How those refunds are handled
    is left as an exercise to the payment app.

    Attributes:
        parent (commerce.CreditNote): The CreditNote that this refund
            corresponds to.

        time (datetime): The time that this refund was generated.

        reference (str): A human-readable reference for the refund, this should
            allow the user to identify the refund in their records.

    '''

    def clean(self):
        if not hasattr(self, "parent"):
            return
        if hasattr(self.parent, 'creditnoteapplication'):
            raise ValidationError(
                "Cannot refund a credit note that has been paid to an invoice"
            )

    parent = models.OneToOneField(CreditNote)
    time = models.DateTimeField(default=timezone.now)
    reference = models.CharField(max_length=255)


class ManualCreditNoteRefund(CreditNoteRefund):
    ''' Credit notes that are entered by a staff member. '''

    class Meta:
        app_label = "registrasion"

    entered_by = models.ForeignKey(User)
