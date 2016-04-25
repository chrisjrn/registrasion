from registrasion.models import commerce
from registrasion.models import inventory
from registrasion.controllers.category import CategoryController

from collections import namedtuple
from django import template
from django.db.models import Sum

register = template.Library()

_ProductAndQuantity = namedtuple("ProductAndQuantity", ["product", "quantity"])


class ProductAndQuantity(_ProductAndQuantity):
    ''' Class that holds a product and a quantity.

    Attributes:
        product (models.inventory.Product)

        quantity (int)

    '''
    pass


@register.assignment_tag(takes_context=True)
def available_categories(context):
    ''' Gets all of the currently available products.

    Returns:
        [models.inventory.Category, ...]: A list of all of the categories that
            have Products that the current user can reserve.

    '''
    return CategoryController.available_categories(context.request.user)


@register.assignment_tag(takes_context=True)
def available_credit(context):
    ''' Calculates the sum of unclaimed credit from this user's credit notes.

    Returns:
        Decimal: the sum of the values of unclaimed credit notes for the
            current user.

    '''

    notes = commerce.CreditNote.unclaimed().filter(
        invoice__user=context.request.user,
    )
    ret = notes.values("amount").aggregate(Sum("amount"))["amount__sum"] or 0
    return 0 - ret


@register.assignment_tag(takes_context=True)
def invoices(context):
    '''

    Returns:
        [models.commerce.Invoice, ...]: All of the current user's invoices. '''
    return commerce.Invoice.objects.filter(user=context.request.user)


@register.assignment_tag(takes_context=True)
def items_pending(context):
    ''' Gets all of the items that the user has reserved, but has not yet
    paid for.

    Returns:
        [ProductAndQuantity, ...]: A list of product-quantity pairs for the
            items that the user has not yet paid for.

    '''

    all_items = commerce.ProductItem.objects.filter(
        cart__user=context.request.user,
        cart__status=commerce.Cart.STATUS_ACTIVE,
    ).select_related(
        "product",
        "product__category",
    ).order_by(
        "product__category__order",
        "product__order",
    )
    return all_items


@register.assignment_tag(takes_context=True)
def items_purchased(context, category=None):
    ''' Aggregates the items that this user has purchased.

    Arguments:
        category (Optional[models.inventory.Category]): the category of items
            to restrict to.

    Returns:
        [ProductAndQuantity, ...]: A list of product-quantity pairs,
            aggregating like products from across multiple invoices.

    '''

    all_items = commerce.ProductItem.objects.filter(
        cart__user=context.request.user,
        cart__status=commerce.Cart.STATUS_PAID,
    ).select_related("product", "product__category")

    if category:
        all_items = all_items.filter(product__category=category)

    pq = all_items.values("product").annotate(quantity=Sum("quantity")).all()
    products = inventory.Product.objects.all()
    out = []
    for item in pq:
        prod = products.get(pk=item["product"])
        out.append(ProductAndQuantity(prod, item["quantity"]))
    return out


@register.filter
def multiply(value, arg):
    ''' Multiplies value by arg.

    This is useful when displaying invoices, as it lets you multiply the
    quantity by the unit value.

    Arguments:

        value (number)

        arg (number)

    Returns:
        number: value * arg

    '''

    return value * arg
