import itertools

from . import inventory

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _
from model_utils.managers import InheritanceManager


# Product Modifiers

@python_2_unicode_compatible
class DiscountBase(models.Model):
    ''' Base class for discounts. Each subclass has controller code that
    determines whether or not the given discount is available to be added to
    the current cart. '''

    class Meta:
        app_label = "registrasion"

    objects = InheritanceManager()

    def __str__(self):
        return "Discount: " + self.description

    def effects(self):
        ''' Returns all of the effects of this discount. '''
        products = self.discountforproduct_set.all()
        categories = self.discountforcategory_set.all()
        return itertools.chain(products, categories)

    description = models.CharField(
        max_length=255,
        verbose_name=_("Description"),
        help_text=_("A description of this discount. This will be included on "
                    "invoices where this discount is applied."),
        )


@python_2_unicode_compatible
class DiscountForProduct(models.Model):
    ''' Represents a discount on an individual product. Each Discount can
    contain multiple products and categories. Discounts can either be a
    percentage or a fixed amount, but not both. '''

    class Meta:
        app_label = "registrasion"

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
    product = models.ForeignKey(inventory.Product, on_delete=models.CASCADE)
    percentage = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True)
    price = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True)
    quantity = models.PositiveIntegerField()


@python_2_unicode_compatible
class DiscountForCategory(models.Model):
    ''' Represents a discount for a category of products. Each discount can
    contain multiple products. Category discounts can only be a percentage. '''

    class Meta:
        app_label = "registrasion"

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
    category = models.ForeignKey(inventory.Category, on_delete=models.CASCADE)
    percentage = models.DecimalField(
        max_digits=4,
        decimal_places=1)
    quantity = models.PositiveIntegerField()


class TimeOrStockLimitDiscount(DiscountBase):
    ''' Discounts that are generally available, but are limited by timespan or
    usage count. This is for e.g. Early Bird discounts. '''

    class Meta:
        app_label = "registrasion"
        verbose_name = _("discount (time/stock limit)")
        verbose_name_plural = _("discounts (time/stock limit)")

    start_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Start time"),
        help_text=_("This discount will only be available after this time."),
    )
    end_time = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("End time"),
        help_text=_("This discount will only be available before this time."),
    )
    limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Limit"),
        help_text=_("This discount may only be applied this many times."),
    )


class VoucherDiscount(DiscountBase):
    ''' Discounts that are enabled when a voucher code is in the current
    cart. '''

    class Meta:
        app_label = "registrasion"
        verbose_name = _("discount (enabled by voucher)")
        verbose_name_plural = _("discounts (enabled by voucher)")

    voucher = models.OneToOneField(
        inventory.Voucher,
        on_delete=models.CASCADE,
        verbose_name=_("Voucher"),
        db_index=True,
    )


class IncludedProductDiscount(DiscountBase):
    ''' Discounts that are enabled because another product has been purchased.
    e.g. A conference ticket includes a free t-shirt. '''

    class Meta:
        app_label = "registrasion"
        verbose_name = _("discount (product inclusions)")
        verbose_name_plural = _("discounts (product inclusions)")

    enabling_products = models.ManyToManyField(
        inventory.Product,
        verbose_name=_("Including product"),
        help_text=_("If one of these products are purchased, the discounts "
                    "below will be enabled."),
    )


class RoleDiscount(object):
    ''' Discounts that are enabled because the active user has a specific
    role. This is for e.g. volunteers who can get a discount ticket. '''
    # TODO: implement RoleDiscount
    pass


@python_2_unicode_compatible
class FlagBase(models.Model):
    ''' This defines a condition which allows products or categories to
    be made visible, or be prevented from being visible.

    The various subclasses of this can define the conditions that enable
    or disable products, by the following rules:

    If there is at least one 'disable if false' flag defined on a product or
    category, all such flag conditions must be met. If there is at least one
    'enable if true' flag, at least one such condition must be met.

    If both types of conditions exist on a product, both of these rules apply.
    '''

    class Meta:
        # TODO: make concrete once https://code.djangoproject.com/ticket/26488
        # is solved.
        abstract = True

    DISABLE_IF_FALSE = 1
    ENABLE_IF_TRUE = 2

    def __str__(self):
        return self.description

    def effects(self):
        ''' Returns all of the items affected by this condition. '''
        return itertools.chain(self.products.all(), self.categories.all())

    @property
    def is_disable_if_false(self):
        return self.condition == FlagBase.DISABLE_IF_FALSE

    @property
    def is_enable_if_true(self):
        return self.condition == FlagBase.ENABLE_IF_TRUE

    description = models.CharField(max_length=255)
    condition = models.IntegerField(
        default=ENABLE_IF_TRUE,
        choices=(
            (DISABLE_IF_FALSE, _("Disable if false")),
            (ENABLE_IF_TRUE, _("Enable if true")),
        ),
        help_text=_("If there is at least one 'disable if false' flag "
                    "defined on a product or category, all such flag "
                    " conditions must be met. If there is at least one "
                    "'enable if true' flag, at least one such condition must "
                    "be met. If both types of conditions exist on a product, "
                    "both of these rules apply."
                    ),
    )
    products = models.ManyToManyField(
        inventory.Product,
        blank=True,
        help_text=_("Products affected by this flag's condition."),
        related_name="flagbase_set",
    )
    categories = models.ManyToManyField(
        inventory.Category,
        blank=True,
        help_text=_("Categories whose products are affected by this flag's "
                    "condition."
                    ),
        related_name="flagbase_set",
    )


class EnablingConditionBase(FlagBase):
    ''' Reifies the abstract FlagBase. This is necessary because django
    prevents renaming base classes in migrations. '''
    # TODO: remove this, and make subclasses subclass FlagBase once
    # https://code.djangoproject.com/ticket/26488 is solved.

    class Meta:
        app_label = "registrasion"

    objects = InheritanceManager()


class TimeOrStockLimitFlag(EnablingConditionBase):
    ''' Registration product ceilings '''

    class Meta:
        app_label = "registrasion"
        verbose_name = _("flag (time/stock limit)")
        verbose_name_plural = _("flags (time/stock limit)")

    start_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Products included in this condition will only be "
                    "available after this time."),
    )
    end_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Products included in this condition will only be "
                    "available before this time."),
    )
    limit = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("The number of items under this grouping that can be "
                    "purchased."),
    )


@python_2_unicode_compatible
class ProductFlag(EnablingConditionBase):
    ''' The condition is met because a specific product is purchased. '''

    class Meta:
        app_label = "registrasion"
        verbose_name = _("flag (dependency on product)")
        verbose_name_plural = _("flags (dependency on product)")

    def __str__(self):
        return "Enabled by products: " + str(self.enabling_products.all())

    enabling_products = models.ManyToManyField(
        inventory.Product,
        help_text=_("If one of these products are purchased, this condition "
                    "is met."),
    )


@python_2_unicode_compatible
class CategoryFlag(EnablingConditionBase):
    ''' The condition is met because a product in a particular product is
    purchased. '''

    class Meta:
        app_label = "registrasion"
        verbose_name = _("flag (dependency on product from category)")
        verbose_name_plural = _("flags (dependency on product from category)")

    def __str__(self):
        return "Enabled by product in category: " + str(self.enabling_category)

    enabling_category = models.ForeignKey(
        inventory.Category,
        help_text=_("If a product from this category is purchased, this "
                    "condition is met."),
    )


@python_2_unicode_compatible
class VoucherFlag(EnablingConditionBase):
    ''' The condition is met because a Voucher is present. This is for e.g.
    enabling sponsor tickets. '''

    class Meta:
        app_label = "registrasion"
        verbose_name = _("flag (dependency on voucher)")
        verbose_name_plural = _("flags (dependency on voucher)")

    def __str__(self):
        return "Enabled by voucher: %s" % self.voucher

    voucher = models.OneToOneField(inventory.Voucher)


# @python_2_unicode_compatible
class RoleFlag(object):
    ''' The condition is met because the active user has a particular Role.
    This is for e.g. enabling Team tickets. '''
    # TODO: implement RoleFlag
    pass
