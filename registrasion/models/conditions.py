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
    ''' Base class for discounts. This class is subclassed with special
    attributes which are used to determine whether or not the given discount
    is available to be added to the current cart.

    Attributes:
        description (str): Display text that appears on the attendee's Invoice
            when the discount is applied to a Product on that invoice.
    '''

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
    percentage or a fixed amount, but not both.

    Attributes:
        product (inventory.Product): The product that this discount line will
            apply to.

        percentage (Decimal): The percentage discount that will be *taken off*
            this product if this discount applies.

        price (Decimal): The currency value that will be *taken off* this
            product if this discount applies.

        quantity (int): The number of times that each user may apply this
            discount line. This applies across every valid Invoice that
            the user has.

    '''

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
    contain multiple products. Category discounts can only be a percentage.

    Attributes:

        category (inventory.Category): The category whose products that this
            discount line will apply to.

        percentage (Decimal): The percentage discount that will be *taken off*
            a product if this discount applies.

        quantity (int): The number of times that each user may apply this
            discount line. This applies across every valid Invoice that the
            user has.

    '''

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
    usage count. This is for e.g. Early Bird discounts.

    Attributes:
        start_time (Optional[datetime]): When the discount should start being
            offered.

        end_time (Optional[datetime]): When the discount should stop being
            offered.

        limit (Optional[int]): How many times the discount is allowed to be
            applied -- to all users.

    '''

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
    cart. These are normally configured in the Admin page at the same time as
    creating a Voucher object.

    Attributes:
        voucher (inventory.Voucher): The voucher that enables this discount.

    '''

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
    e.g. A conference ticket includes a free t-shirt.

    Attributes:
        enabling_products ([inventory.Product, ...]): The products that enable
            the discount.

    '''

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

    Attributes:
        description (str): A human-readable description that is used to
            identify the flag to staff in the admin interface. It's not seen
            anywhere else in Registrasion.

        condition (int): This determines the effect of this flag's condition
            being met. There are two types of condition:

            ``ENABLE_IF_TRUE`` conditions switch on the products and
            categories included under this flag if *any* such condition is met.

            ``DISABLE_IF_FALSE`` conditions *switch off* the products and
            categories included under this flag is any such condition
            *is not* met.

            If you have both types of conditions attached to a Product, every
            ``DISABLE_IF_FALSE`` condition must be met, along with one
            ``ENABLE_IF_TRUE`` condition.

        products ([inventory.Product, ...]):
            The Products affected by this flag.

        categories ([inventory.Category, ...]):
            The Categories whose Products are affected by this flag.
    '''

    objects = InheritanceManager()

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


class TimeOrStockLimitFlag(FlagBase):
    ''' Product groupings that can be used to enable a product during a
    specific date range, or when fewer than a limit of products have been
    sold.

    Attributes:
        start_time (Optional[datetime]): This condition is only met after this
            time.

        end_time (Optional[datetime]): This condition is only met before this
            time.

        limit (Optional[int]): The number of products that *all users* can
            purchase under this limit, regardless of their per-user limits.

    '''

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
class ProductFlag(FlagBase):
    ''' The condition is met because a specific product is purchased.

    Attributes:
        enabling_products ([inventory.Product, ...]): The products that cause
            this condition to be met.
    '''

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
class CategoryFlag(FlagBase):
    ''' The condition is met because a product in a particular product is
    purchased.

    Attributes:
        enabling_category (inventory.Category): The category that causes this
            condition to be met.
     '''

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
class VoucherFlag(FlagBase):
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
