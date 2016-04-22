from registrasion.models import commerce
from registrasion.models import inventory
from registrasion.controllers.category import CategoryController

from collections import namedtuple
from django import template
from django.db.models import Sum

register = template.Library()

ProductAndQuantity = namedtuple("ProductAndQuantity", ["product", "quantity"])


@register.assignment_tag(takes_context=True)
def available_categories(context):
    ''' Returns all of the available product categories '''
    return CategoryController.available_categories(context.request.user)


@register.assignment_tag(takes_context=True)
def available_credit(context):
    ''' Returns the amount of unclaimed credit available for this user. '''
    notes = commerce.CreditNote.unclaimed().filter(
        invoice__user=context.request.user,
    )
    ret = notes.values("amount").aggregate(Sum("amount"))["amount__sum"] or 0
    return 0 - ret


@register.assignment_tag(takes_context=True)
def invoices(context):
    ''' Returns all of the invoices that this user has. '''
    return commerce.Invoice.objects.filter(cart__user=context.request.user)


@register.assignment_tag(takes_context=True)
def items_pending(context):
    ''' Returns all of the items that this user has in their current cart,
    and is awaiting payment. '''

    all_items = commerce.ProductItem.objects.filter(
        cart__user=context.request.user,
        cart__active=True,
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
    ''' Returns all of the items that this user has purchased, optionally
    from the given category. '''

    all_items = commerce.ProductItem.objects.filter(
        cart__user=context.request.user,
        cart__active=False,
        cart__released=False,
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
    ''' Multiplies value by arg '''
    return value * arg
