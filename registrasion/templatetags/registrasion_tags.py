from registrasion import models as rego

from collections import namedtuple
from django import template
from django.db.models import Sum

register = template.Library()

ProductAndQuantity = namedtuple("ProductAndQuantity", ["product", "quantity"])


@register.assignment_tag(takes_context=True)
def available_categories(context):
    ''' Returns all of the available product categories '''
    return rego.Category.objects.all()


@register.assignment_tag(takes_context=True)
def invoices(context):
    ''' Returns all of the invoices that this user has. '''
    return rego.Invoice.objects.filter(cart__user=context.request.user)


@register.assignment_tag(takes_context=True)
def items_pending(context):
    ''' Returns all of the items that this user has in their current cart,
    and is awaiting payment. '''

    all_items = rego.ProductItem.objects.filter(
        cart__user=context.request.user,
        cart__active=True,
    )
    return all_items


@register.assignment_tag(takes_context=True)
def items_purchased(context):
    ''' Returns all of the items that this user has purchased '''

    all_items = rego.ProductItem.objects.filter(
        cart__user=context.request.user,
        cart__active=False,
    )

    products = set(item.product for item in all_items)
    out = []
    for product in products:
        pp = all_items.filter(product=product)
        quantity = pp.aggregate(Sum("quantity"))["quantity__sum"]
        out.append(ProductAndQuantity(product, quantity))
    return out
