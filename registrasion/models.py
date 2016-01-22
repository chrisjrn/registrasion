from __future__ import unicode_literals

import datetime

from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _
from model_utils.managers import InheritanceManager


from symposion.markdown_parser import parse
from symposion.proposals.models import ProposalBase


# User models

@python_2_unicode_compatible
class Profile(models.Model):
    ''' Miscellaneous user-related data. '''

    def __str__(self):
        return "%s" % self.user

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    # Badge is linked
    completed_registration = models.BooleanField(default=False)
    highest_complete_category = models.IntegerField(default=0)


@python_2_unicode_compatible
class Badge(models.Model):
    ''' Information for an attendee's badge. '''

    def __str__(self):
        return "Badge for: %s of %s" % (self.name, self.company)

    profile = models.OneToOneField(Profile, on_delete=models.CASCADE)

    name = models.CharField(max_length=256)
    company = models.CharField(max_length=256)


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
    description = models.CharField(max_length=255, verbose_name=_("Description"))
    order = models.PositiveIntegerField(verbose_name=("Display order"))
    render_type = models.IntegerField(choices=CATEGORY_RENDER_TYPES, verbose_name=_("Render type"))


@python_2_unicode_compatible
class Product(models.Model):
    ''' Registration products '''

    def __str__(self):
        return self.name

    name = models.CharField(max_length=65, verbose_name=_("Name"))
    description = models.CharField(max_length=255, verbose_name=_("Description"))
    category = models.ForeignKey(Category, verbose_name=_("Product category"))
    price = models.DecimalField(max_digits=8, decimal_places=2, verbose_name=_("Price"))
    limit_per_user = models.PositiveIntegerField(blank=True, verbose_name=_("Limit per user"))
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

    recipient = models.CharField(max_length=64, verbose_name=_("Recipient"))
    code = models.CharField(max_length=16, unique=True, verbose_name=_("Voucher code"))
    limit = models.PositiveIntegerField(verbose_name=_("Voucher use limit"))


# Product Modifiers

@python_2_unicode_compatible
class DiscountBase(models.Model):
    ''' Base class for discounts. Each subclass has controller code that
    determines whether or not the given discount is available to be added to the
    current cart. '''

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

    discount = models.ForeignKey(DiscountBase, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    percentage = models.DecimalField(max_digits=4, decimal_places=1, null=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, null=True)
    quantity = models.PositiveIntegerField()


@python_2_unicode_compatible
class DiscountForCategory(models.Model):
    ''' Represents a discount for a category of products. Each discount can
    contain multiple products. Category discounts can only be a percentage. '''

    def __str__(self):
        return "%s%% off %s" % (self.percentage, self.category)

    discount = models.ForeignKey(DiscountBase, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    percentage = models.DecimalField(max_digits=4, decimal_places=1, blank=True)
    quantity = models.PositiveIntegerField()


class TimeOrStockLimitDiscount(DiscountBase):
    ''' Discounts that are generally available, but are limited by timespan or
    usage count. This is for e.g. Early Bird discounts. '''

    class Meta:
        verbose_name = _("Promotional discount")

    start_time = models.DateTimeField(null=True, verbose_name=_("Start time"))
    end_time = models.DateTimeField(null=True, verbose_name=_("End time"))
    limit = models.PositiveIntegerField(null=True, verbose_name=_("Limit"))


class VoucherDiscount(DiscountBase):
    ''' Discounts that are enabled when a voucher code is in the current
    cart. '''

    voucher = models.OneToOneField(Voucher, on_delete=models.CASCADE,
        verbose_name=_("Voucher"))


class IncludedProductDiscount(DiscountBase):
    ''' Discounts that are enabled because another product has been purchased.
    e.g. A conference ticket includes a free t-shirt. '''

    class Meta:
        verbose_name = _("Product inclusion")

    enabling_products = models.ManyToManyField(Product,
        verbose_name=_("Including product"))


class RoleDiscount(object):
    ''' Discounts that are enabled because the active user has a specific
    role. This is for e.g. volunteers who can get a discount ticket. '''
    ## TODO: implement RoleDiscount
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
    products = models.ManyToManyField(Product)
    categories = models.ManyToManyField(Category)


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
        return "Enabled by voucher: %s" % voucher

    voucher = models.OneToOneField(Voucher)


#@python_2_unicode_compatible
class RoleEnablingCondition(object):
    ''' The condition is met because the active user has a particular Role.
    This is for e.g. enabling Team tickets. '''
    ## TODO: implement RoleEnablingCondition
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

    @classmethod
    def reserved_carts(cls):
        ''' Gets all carts that are 'reserved' '''
        return Cart.objects.filter(
            (Q(active=True) &
                Q(time_last_updated__gt=timezone.now()-F('reservation_duration')
            )) |
            Q(active=False)
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
