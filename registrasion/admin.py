from django.contrib import admin
from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import ugettext_lazy as _

import nested_admin

from registrasion import models as rego


class EffectsDisplayMixin(object):
    def effects(self, obj):
        return list(obj.effects())

# Inventory admin


class ProductInline(admin.TabularInline):
    model = rego.Product
    ordering = ("order", )


@admin.register(rego.Category)
class CategoryAdmin(admin.ModelAdmin):
    model = rego.Category
    fields = ("name", "description", "required", "render_type",
              "limit_per_user", "order",)
    list_display = ("name", "description")
    ordering = ("order", )
    inlines = [
        ProductInline,
    ]


@admin.register(rego.Product)
class ProductAdmin(admin.ModelAdmin):
    model = rego.Product
    list_display = ("name", "category", "description")
    list_filter = ("category", )
    ordering = ("category__order", "order", )


# Discounts

class DiscountForProductInline(admin.TabularInline):
    model = rego.DiscountForProduct
    verbose_name = _("Product included in discount")
    verbose_name_plural = _("Products included in discount")


class DiscountForCategoryInline(admin.TabularInline):
    model = rego.DiscountForCategory
    verbose_name = _("Category included in discount")
    verbose_name_plural = _("Categories included in discount")


@admin.register(rego.TimeOrStockLimitDiscount)
class TimeOrStockLimitDiscountAdmin(admin.ModelAdmin, EffectsDisplayMixin):
    list_display = (
        "description",
        "start_time",
        "end_time",
        "limit",
        "effects",
    )
    ordering = ("start_time", "end_time", "limit")

    inlines = [
        DiscountForProductInline,
        DiscountForCategoryInline,
    ]


@admin.register(rego.IncludedProductDiscount)
class IncludedProductDiscountAdmin(admin.ModelAdmin):

    def enablers(self, obj):
        return list(obj.enabling_products.all())

    def effects(self, obj):
        return list(obj.effects())

    list_display = ("description", "enablers", "effects")

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


class VoucherFlagInline(nested_admin.NestedStackedInline):
    model = rego.VoucherFlag
    verbose_name = _("Product and category enabled by voucher")
    verbose_name_plural = _("Products and categories enabled by voucher")

    # TODO work out why we're allowed to add more than one?
    max_num = 1
    extra = 1


@admin.register(rego.Voucher)
class VoucherAdmin(nested_admin.NestedAdmin):

    def effects(self, obj):
        ''' List the effects of the voucher in the admin. '''
        out = []

        try:
            discount_effects = obj.voucherdiscount.effects()
        except ObjectDoesNotExist:
            discount_effects = None

        try:
            enabling_effects = obj.voucherflag.effects()
        except ObjectDoesNotExist:
            enabling_effects = None

        if discount_effects:
            out.append("Discounts: " + str(list(discount_effects)))
        if enabling_effects:
            out.append("Enables: " + str(list(enabling_effects)))

        return "\n".join(out)

    model = rego.Voucher
    list_display = ("recipient", "code", "effects")
    inlines = [
        VoucherDiscountInline,
        VoucherFlagInline,
    ]


# Enabling conditions
@admin.register(rego.ProductFlag)
class ProductFlagAdmin(
        nested_admin.NestedAdmin,
        EffectsDisplayMixin):

    def enablers(self, obj):
        return list(obj.enabling_products.all())

    model = rego.ProductFlag
    fields = ("description", "enabling_products", "mandatory", "products",
              "categories"),

    list_display = ("description", "enablers", "effects")


# Enabling conditions
@admin.register(rego.CategoryFlag)
class CategoryFlagAdmin(
        nested_admin.NestedAdmin,
        EffectsDisplayMixin):

    model = rego.CategoryFlag
    fields = ("description", "enabling_category", "mandatory", "products",
              "categories"),

    list_display = ("description", "enabling_category", "effects")
    ordering = ("enabling_category",)


# Enabling conditions
@admin.register(rego.TimeOrStockLimitFlag)
class TimeOrStockLimitFlagAdmin(
        nested_admin.NestedAdmin,
        EffectsDisplayMixin):
    model = rego.TimeOrStockLimitFlag

    list_display = (
        "description",
        "start_time",
        "end_time",
        "limit",
        "effects",
    )
    ordering = ("start_time", "end_time", "limit")
