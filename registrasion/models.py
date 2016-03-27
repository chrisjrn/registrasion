from __future__ import unicode_literals

import datetime

from django.core.exceptions import ValidationError
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import User
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _
from model_utils.managers import InheritanceManager


# User models

@python_2_unicode_compatible
class Attendee(models.Model):
    ''' Miscellaneous user-related data. '''

    def __str__(self):
        return "%s" % self.user

    @staticmethod
    def get_instance(user):
        ''' Returns the instance of attendee for the given user, or creates
        a new one. '''
        attendees = Attendee.objects.filter(user=user)
        if len(attendees) > 0:
            return attendees[0]
        else:
            attendee = Attendee(user=user)
            attendee.save()
            return attendee

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    # Badge/profile is linked
    completed_registration = models.BooleanField(default=False)
    highest_complete_category = models.IntegerField(default=0)


@python_2_unicode_compatible
class BadgeAndProfile(models.Model):
    ''' Information for an attendee's badge and related preferences '''

    def __str__(self):
        return "Badge for: %s of %s" % (self.name, self.company)

    @staticmethod
    def get_instance(attendee):
        ''' Returns either None, or the instance that belongs
        to this attendee. '''
        try:
            return BadgeAndProfile.objects.get(attendee=attendee)
        except ObjectDoesNotExist:
            return None

    attendee = models.OneToOneField(Attendee, on_delete=models.CASCADE)

    # Things that appear on badge
    name = models.CharField(
        verbose_name="Your name (for your conference nametag)",
        max_length=64,
        help_text="Your name, as you'd like it to appear on your badge. ",
    )
    company = models.CharField(
        max_length=64,
        help_text="The name of your company, as you'd like it on your badge",
        blank=True,
    )
    free_text_1 = models.CharField(
        max_length=64,
        verbose_name="Free text line 1",
        help_text="A line of free text that will appear on your badge. Use "
                  "this for your Twitter handle, IRC nick, your preferred "
                  "pronouns or anything else you'd like people to see on "
                  "your badge.",
        blank=True,
    )
    free_text_2 = models.CharField(
        max_length=64,
        verbose_name="Free text line 2",
        blank=True,
    )

    # Other important Information
    name_per_invoice = models.CharField(
        verbose_name="Your legal name (for invoicing purposes)",
        max_length=64,
        help_text="If your legal name is different to the name on your badge, "
                  "fill this in, and we'll put it on your invoice. Otherwise, "
                  "leave it blank.",
        blank=True,
        )
    of_legal_age = models.BooleanField(
        default=False,
        verbose_name="18+?",
        blank=True,
    )
    dietary_requirements = models.CharField(
        max_length=256,
        blank=True,
    )
    accessibility_requirements = models.CharField(
        max_length=256,
        blank=True,
    )
    gender = models.CharField(
        max_length=64,
        blank=True,
    )


# Inventory Models

@python_2_unicode_compatible
class Category(models.Model):
    ''' Registration product categories '''

    def __str__(self):
        return self.name

    RENDER_TYPE_RADIO = 1
    RENDER_TYPE_QUANTITY = 2

    CATEGORY_RENDER_TYPES = [
        (RENDER_TYPE_RADIO, _("Radio button")),
        (RENDER_TYPE_QUANTITY, _("Quantity boxes")),
    ]

    name = models.CharField(max_length=65, verbose_name=_("Name"))
    description = models.CharField(max_length=255,
                                   verbose_name=_("Description"))
    limit_per_user = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Limit per user"))
    required = models.BooleanField(blank=True)
    order = models.PositiveIntegerField(verbose_name=("Display order"))
    render_type = models.IntegerField(choices=CATEGORY_RENDER_TYPES,
                                      verbose_name=_("Render type"))


@python_2_unicode_compatible
class Product(models.Model):
    ''' Registration products '''

    def __str__(self):
        return self.name

    name = models.CharField(max_length=65, verbose_name=_("Name"))
    description = models.CharField(max_length=255,
                                   verbose_name=_("Description"))
    category = models.ForeignKey(Category, verbose_name=_("Product category"))
    price = models.DecimalField(max_digits=8,
                                decimal_places=2,
                                verbose_name=_("Price"))
    limit_per_user = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Limit per user"))
    reservation_duration = models.DurationField(
        default=datetime.timedelta(hours=1),
        verbose_name=_("Reservation duration"))
    order = models.PositiveIntegerField(verbose_name=("Display order"))


@python_2_unicode_compatible
class Voucher(models.Model):
    ''' Registration vouchers '''

    # Vouchers reserve a cart for a fixed amount of time, so that
    # items may be added without the voucher being swiped by someone else
    RESERVATION_DURATION = datetime.timedelta(hours=1)

    def __str__(self):
        return "Voucher for %s" % self.recipient

    @classmethod
    def normalise_code(cls, code):
        return code.upper()

    def save(self, *a, **k):
        ''' Normalise the voucher code to be uppercase '''
        self.code = self.normalise_code(self.code)
        super(Voucher, self).save(*a, **k)

    recipient = models.CharField(max_length=64, verbose_name=_("Recipient"))
    code = models.CharField(max_length=16,
                            unique=True,
                            verbose_name=_("Voucher code"))
    limit = models.PositiveIntegerField(verbose_name=_("Voucher use limit"))


# Product Modifiers

@python_2_unicode_compatible
class DiscountBase(models.Model):
    ''' Base class for discounts. Each subclass has controller code that
    determines whether or not the given discount is available to be added to
    the current cart. '''

    objects = InheritanceManager()

    def __str__(self):
        return "Discount: " + self.description

    description = models.CharField(max_length=255,
                                   verbose_name=_("Description"))


@python_2_unicode_compatible
class DiscountForProduct(models.Model):
    ''' Represents a discount on an individual product. Each Discount can
    contain multiple products and categories. Discounts can either be a
    percentage or a fixed amount, but not both. '''

    def __str__(self):
        if self.percentage:
            return "%s%% off %s" % (self.percentage, self.product)
        elif self.price:
            return "$%s off %s" % (self.price, self.product)

    def clean(self):
        if self.percentage is None and self.price is None:
            raise ValidationError(
                _("Discount must have a percentage or a price."))
        elif self.percentage is not None and self.price is not None:
            raise ValidationError(
                _("Discount may only have a percentage or only a price."))

        prods = DiscountForProduct.objects.filter(
            discount=self.discount,
            product=self.product)
        cats = DiscountForCategory.objects.filter(
            discount=self.discount,
            category=self.product.category)
        if len(prods) > 1:
            raise ValidationError(
                _("You may only have one discount line per product"))
        if len(cats) != 0:
            raise ValidationError(
                _("You may only have one discount for "
                    "a product or its category"))

    discount = models.ForeignKey(DiscountBase, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    percentage = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True)
    price = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True)
    quantity = models.PositiveIntegerField()


@python_2_unicode_compatible
class DiscountForCategory(models.Model):
    ''' Represents a discount for a category of products. Each discount can
    contain multiple products. Category discounts can only be a percentage. '''

    def __str__(self):
        return "%s%% off %s" % (self.percentage, self.category)

    def clean(self):
        prods = DiscountForProduct.objects.filter(
            discount=self.discount,
            product__category=self.category)
        cats = DiscountForCategory.objects.filter(
            discount=self.discount,
            category=self.category)
        if len(prods) != 0:
            raise ValidationError(
                _("You may only have one discount for "
                    "a product or its category"))
        if len(cats) > 1:
            raise ValidationError(
                _("You may only have one discount line per category"))

    discount = models.ForeignKey(DiscountBase, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    percentage = models.DecimalField(
        max_digits=4,
        decimal_places=1)
    quantity = models.PositiveIntegerField()


class TimeOrStockLimitDiscount(DiscountBase):
    ''' Discounts that are generally available, but are limited by timespan or
    usage count. This is for e.g. Early Bird discounts. '''

    class Meta:
        verbose_name = _("Promotional discount")

    start_time = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Start time"))
    end_time = models.DateTimeField(
        null=True, blank=True, verbose_name=_("End time"))
    limit = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_("Limit"))


class VoucherDiscount(DiscountBase):
    ''' Discounts that are enabled when a voucher code is in the current
    cart. '''

    voucher = models.OneToOneField(
        Voucher,
        on_delete=models.CASCADE,
        verbose_name=_("Voucher"))


class IncludedProductDiscount(DiscountBase):
    ''' Discounts that are enabled because another product has been purchased.
    e.g. A conference ticket includes a free t-shirt. '''

    class Meta:
        verbose_name = _("Product inclusion")

    enabling_products = models.ManyToManyField(
        Product,
        verbose_name=_("Including product"))


class RoleDiscount(object):
    ''' Discounts that are enabled because the active user has a specific
    role. This is for e.g. volunteers who can get a discount ticket. '''
    # TODO: implement RoleDiscount
    pass


@python_2_unicode_compatible
class EnablingConditionBase(models.Model):
    ''' This defines a condition which allows products or categories to
    be made visible. If there is at least one mandatory enabling condition
    defined on a Product or Category, it will only be enabled if *all*
    mandatory conditions are met, otherwise, if there is at least one enabling
    condition defined on a Product or Category, it will only be enabled if at
    least one condition is met. '''

    objects = InheritanceManager()

    def __str__(self):
        return self.name

    description = models.CharField(max_length=255)
    mandatory = models.BooleanField(default=False)
    products = models.ManyToManyField(Product, blank=True)
    categories = models.ManyToManyField(Category, blank=True)


class TimeOrStockLimitEnablingCondition(EnablingConditionBase):
    ''' Registration product ceilings '''

    start_time = models.DateTimeField(null=True, verbose_name=_("Start time"))
    end_time = models.DateTimeField(null=True, verbose_name=_("End time"))
    limit = models.PositiveIntegerField(null=True, verbose_name=_("Limit"))


@python_2_unicode_compatible
class ProductEnablingCondition(EnablingConditionBase):
    ''' The condition is met because a specific product is purchased. '''

    def __str__(self):
        return "Enabled by product: "

    enabling_products = models.ManyToManyField(Product)


@python_2_unicode_compatible
class CategoryEnablingCondition(EnablingConditionBase):
    ''' The condition is met because a product in a particular product is
    purchased. '''

    def __str__(self):
        return "Enabled by product in category: "

    enabling_category = models.ForeignKey(Category)


@python_2_unicode_compatible
class VoucherEnablingCondition(EnablingConditionBase):
    ''' The condition is met because a Voucher is present. This is for e.g.
    enabling sponsor tickets. '''

    def __str__(self):
        return "Enabled by voucher: %s" % self.voucher

    voucher = models.OneToOneField(Voucher)


# @python_2_unicode_compatible
class RoleEnablingCondition(object):
    ''' The condition is met because the active user has a particular Role.
    This is for e.g. enabling Team tickets. '''
    # TODO: implement RoleEnablingCondition
    pass


# Commerce Models

@python_2_unicode_compatible
class Cart(models.Model):
    ''' Represents a set of product items that have been purchased, or are
    pending purchase. '''

    def __str__(self):
        return "%d rev #%d" % (self.id, self.revision)

    user = models.ForeignKey(User)
    # ProductItems (foreign key)
    vouchers = models.ManyToManyField(Voucher, blank=True)
    time_last_updated = models.DateTimeField()
    reservation_duration = models.DurationField()
    revision = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)
    released = models.BooleanField(default=False)  # Refunds etc

    @classmethod
    def reserved_carts(cls):
        ''' Gets all carts that are 'reserved' '''
        return Cart.objects.filter(
            (Q(active=True) &
                Q(time_last_updated__gt=(
                    timezone.now()-F('reservation_duration')
                                        ))) |
            (Q(active=False) & Q(released=False))
        )


@python_2_unicode_compatible
class ProductItem(models.Model):
    ''' Represents a product-quantity pair in a Cart. '''

    def __str__(self):
        return "product: %s * %d in Cart: %s" % (
            self.product, self.quantity, self.cart)

    cart = models.ForeignKey(Cart)
    product = models.ForeignKey(Product)
    quantity = models.PositiveIntegerField()


@python_2_unicode_compatible
class DiscountItem(models.Model):
    ''' Represents a discount-product-quantity relation in a Cart. '''

    def __str__(self):
        return "%s: %s * %d in Cart: %s" % (
            self.discount, self.product, self.quantity, self.cart)

    cart = models.ForeignKey(Cart)
    product = models.ForeignKey(Product)
    discount = models.ForeignKey(DiscountBase)
    quantity = models.PositiveIntegerField()


@python_2_unicode_compatible
class Invoice(models.Model):
    ''' An invoice. Invoices can be automatically generated when checking out
    a Cart, in which case, it is attached to a given revision of a Cart. '''

    def __str__(self):
        return "Invoice #%d" % self.id

    def clean(self):
        if self.cart is not None and self.cart_revision is None:
            raise ValidationError(
                "If this is a cart invoice, it must have a revision")

    # Invoice Number
    user = models.ForeignKey(User)
    cart = models.ForeignKey(Cart, null=True)
    cart_revision = models.IntegerField(null=True)
    # Line Items (foreign key)
    void = models.BooleanField(default=False)
    paid = models.BooleanField(default=False)
    value = models.DecimalField(max_digits=8, decimal_places=2)


@python_2_unicode_compatible
class LineItem(models.Model):
    ''' Line items for an invoice. These are denormalised from the ProductItems
    and DiscountItems that belong to a cart (for consistency), but also allow
    for arbitrary line items when required. '''

    def __str__(self):
        return "Line: %s * %d @ %s" % (
            self.description, self.quantity, self.price)

    invoice = models.ForeignKey(Invoice)
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=8, decimal_places=2)


@python_2_unicode_compatible
class Payment(models.Model):
    ''' A payment for an invoice. Each invoice can have multiple payments
    attached to it.'''

    def __str__(self):
        return "Payment: ref=%s amount=%s" % (self.reference, self.amount)

    invoice = models.ForeignKey(Invoice)
    time = models.DateTimeField(default=timezone.now)
    reference = models.CharField(max_length=64)
    amount = models.DecimalField(max_digits=8, decimal_places=2)
