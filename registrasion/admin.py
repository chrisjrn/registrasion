from django.contrib import admin
from django.utils.translation import ugettext_lazy as _

import nested_admin

from registrasion import models as rego


# Inventory admin

class ProductInline(admin.TabularInline):
    model = rego.Product


@admin.register(rego.Category)
class CategoryAdmin(admin.ModelAdmin):
    model = rego.Category
    verbose_name_plural = _("Categories")
    inlines = [
        ProductInline,
    ]

admin.site.register(rego.Product)


# Discounts

class DiscountForProductInline(admin.TabularInline):
    model = rego.DiscountForProduct
    verbose_name = _("Product included in discount")
    verbose_name_plural = _("Products included in discount")


class DiscountForCategoryInline(admin.TabularInline):
    model = rego.DiscountForCategory
    verbose_name = _("Category included in discount")
    verbose_name_plural = _("Categories included in discount")


@admin.register(
    rego.TimeOrStockLimitDiscount,
    rego.IncludedProductDiscount,
)
class DiscountAdmin(admin.ModelAdmin):
    inlines = [
        DiscountForProductInline,
        DiscountForCategoryInline,
    ]


# Vouchers

class VoucherDiscountInline(nested_admin.NestedStackedInline):
    model = rego.VoucherDiscount
    verbose_name = _("Discount")

    # TODO work out why we're allowed to add more than one?
    max_num = 1
    extra = 1
    inlines = [
        DiscountForProductInline,
        DiscountForCategoryInline,
    ]


class VoucherEnablingConditionInline(nested_admin.NestedStackedInline):
    model = rego.VoucherEnablingCondition
    verbose_name = _("Product and category enabled by voucher")
    verbose_name_plural = _("Products and categories enabled by voucher")

    # TODO work out why we're allowed to add more than one?
    max_num = 1
    extra = 1


@admin.register(rego.Voucher)
class VoucherAdmin(nested_admin.NestedAdmin):
    model = rego.Voucher
    inlines = [
        VoucherDiscountInline,
        VoucherEnablingConditionInline,
    ]
