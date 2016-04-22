import datetime

from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _


# Inventory Models

@python_2_unicode_compatible
class Category(models.Model):
    ''' Registration product categories, used as logical groupings for Products
    in registration forms.

    Attributes:
        name (str): The display name for the category.

        description (str): Some explanatory text for the category. This is
            displayed alongside the forms where your attendees choose their
            items.

        required (bool): Requires a user to select an item from this category
            during initial registration. You can use this, e.g., for making
            sure that the user has a ticket before they select whether they
            want a t-shirt.

        render_type (int): This is used to determine what sort of form the
            attendee will be presented with when choosing Products from this
            category. These may be either of the following:

            ``RENDER_TYPE_RADIO`` presents the Products in the Category as a
            list of radio buttons. At most one item can be chosen at a time.
            This works well when setting limit_per_user to 1.

            ``RENDER_TYPE_QUANTITY`` shows each Product next to an input field,
            where the user can specify a quantity of each Product type. This is
            useful for additional extras, like Dinner Tickets.

        limit_per_user (Optional[int]): This restricts the number of items
            from this Category that each attendee may claim. This extends
            across multiple Invoices.

        display_order (int): An ascending order for displaying the Categories
            available. By convention, your Category for ticket types should
            have the lowest display order.
    '''

    class Meta:
        app_label = "registrasion"
        verbose_name = _("inventory - category")
        verbose_name_plural = _("inventory - categories")
        ordering = ("order", )

    def __str__(self):
        return self.name

    RENDER_TYPE_RADIO = 1
    RENDER_TYPE_QUANTITY = 2

    CATEGORY_RENDER_TYPES = [
        (RENDER_TYPE_RADIO, _("Radio button")),
        (RENDER_TYPE_QUANTITY, _("Quantity boxes")),
    ]

    name = models.CharField(
        max_length=65,
        verbose_name=_("Name"),
    )
    description = models.CharField(
        max_length=255,
        verbose_name=_("Description"),
    )
    limit_per_user = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Limit per user"),
        help_text=_("The total number of items from this category one "
                    "attendee may purchase."),
    )
    required = models.BooleanField(
        blank=True,
        help_text=_("If enabled, a user must select an "
                    "item from this category."),
    )
    order = models.PositiveIntegerField(
        verbose_name=("Display order"),
        db_index=True,
    )
    render_type = models.IntegerField(
        choices=CATEGORY_RENDER_TYPES,
        verbose_name=_("Render type"),
        help_text=_("The registration form will render this category in this "
                    "style."),
    )


@python_2_unicode_compatible
class Product(models.Model):
    ''' Products make up the conference inventory.

    Attributes:
        name (str): The display name for the product.

        description (str): Some descriptive text that will help the user to
            understand the product when they're at the registration form.

        category (Category): The Category that this product will be grouped
            under.

        price (Decimal): The price that 1 unit of this product will sell for.
            Note that this should be the full price, before any discounts are
            applied.

        limit_per_user (Optional[int]): This restricts the number of this
            Product that each attendee may claim. This extends across multiple
            Invoices.

        reservation_duration (datetime): When a Product is added to the user's
            tentative registration, it is marked as unavailable for a period of
            time. This allows the user to build up their registration and then
            pay for it. This reservation duration determines how long an item
            should be allowed to be reserved whilst being unpaid.

        display_order (int): An ascending order for displaying the Products
            within each Category.

    '''

    class Meta:
        app_label = "registrasion"
        verbose_name = _("inventory - product")
        ordering = ("category__order", "order")

    def __str__(self):
        return "%s - %s" % (self.category.name, self.name)

    name = models.CharField(
        max_length=65,
        verbose_name=_("Name"),
    )
    description = models.CharField(
        max_length=255,
        verbose_name=_("Description"),
        null=True,
        blank=True,
    )
    category = models.ForeignKey(
        Category,
        verbose_name=_("Product category")
    )
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        verbose_name=_("Price"),
    )
    limit_per_user = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Limit per user"),
    )
    reservation_duration = models.DurationField(
        default=datetime.timedelta(hours=1),
        verbose_name=_("Reservation duration"),
        help_text=_("The length of time this product will be reserved before "
                    "it is released for someone else to purchase."),
    )
    order = models.PositiveIntegerField(
        verbose_name=("Display order"),
        db_index=True,
    )


@python_2_unicode_compatible
class Voucher(models.Model):
    ''' Vouchers are used to enable Discounts or Flags for the people who hold
    the voucher code.

    Attributes:
        recipient (str): A display string used to identify the holder of the
            voucher on the admin page.

        code (str): The string that is used to prove that the attendee holds
            this voucher.

        limit (int): The number of attendees who are permitted to hold this
            voucher.

     '''

    class Meta:
        app_label = "registrasion"

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
