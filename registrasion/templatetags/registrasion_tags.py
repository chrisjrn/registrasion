from registrasion.models import commerce
from registrasion.controllers.category import CategoryController
from registrasion.controllers.item import ItemController

from django import template
from django.db.models import Sum

register = template.Library()


@register.assignment_tag(takes_context=True)
def available_categories(context):
    ''' Gets all of the currently available products.

    Returns:
        [models.inventory.Category, ...]: A list of all of the categories that
            have Products that the current user can reserve.

    '''
    return CategoryController.available_categories(context.request.user)


@register.assignment_tag(takes_context=True)
def missing_categories(context):
    ''' Adds the categories that the user does not currently have. '''
    user = context.request.user
    categories_available = set(CategoryController.available_categories(user))
    items = ItemController(user).items_pending_or_purchased()

    categories_held = set()

    for product, quantity in items:
        categories_held.add(product.category)

    return categories_available - categories_held


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
    ''' Gets all of the items that the user from this context has reserved.'''
    return ItemController(context.request.user).items_pending()


@register.assignment_tag(takes_context=True)
def items_purchased(context, category=None):
    ''' Returns the items purchased for this user. '''

    return ItemController(context.request.user).items_purchased(
        category=category
    )


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
