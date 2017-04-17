from registrasion.models import commerce
from registrasion.controllers.category import CategoryController
from registrasion.controllers.item import ItemController

from django import template
from django.db.models import Sum
from urllib.parse import urlencode

register = template.Library()


def user_for_context(context):
    ''' Returns either context.user or context.request.user if the former is
    not defined. '''
    try:
        return context["user"]
    except KeyError:
        return context.request.user


@register.assignment_tag(takes_context=True)
def available_categories(context):
    ''' Gets all of the currently available products.

    Returns:
        [models.inventory.Category, ...]: A list of all of the categories that
            have Products that the current user can reserve.

    '''
    return CategoryController.available_categories(user_for_context(context))


@register.assignment_tag(takes_context=True)
def missing_categories(context):
    ''' Adds the categories that the user does not currently have. '''
    user = user_for_context(context)
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
        invoice__user=user_for_context(context),
    )
    ret = notes.values("amount").aggregate(Sum("amount"))["amount__sum"] or 0
    return 0 - ret


@register.assignment_tag(takes_context=True)
def invoices(context):
    '''

    Returns:
        [models.commerce.Invoice, ...]: All of the current user's invoices. '''
    return commerce.Invoice.objects.filter(user=user_for_context(context))


@register.assignment_tag(takes_context=True)
def items_pending(context):
    ''' Gets all of the items that the user from this context has reserved.

    The user will be either `context.user`, and `context.request.user` if
    the former is not defined.
    '''

    return ItemController(user_for_context(context)).items_pending()


@register.assignment_tag(takes_context=True)
def items_purchased(context, category=None):
    ''' Returns the items purchased for this user.

    The user will be either `context.user`, and `context.request.user` if
    the former is not defined.
    '''

    return ItemController(user_for_context(context)).items_purchased(
        category=category
    )


@register.assignment_tag(takes_context=True)
def total_items_purchased(context, category=None):
    ''' Returns the number of items purchased for this user (sum of quantities).

    The user will be either `context.user`, and `context.request.user` if
    the former is not defined.
    '''

    return sum(i.quantity for i in items_purchased(context, category))


@register.assignment_tag(takes_context=True)
def report_as_csv(context, section):

    old_query = context.request.META["QUERY_STRING"]
    query = dict([("section", section), ("content_type", "text/csv")])
    querystring = urlencode(query)

    if old_query:
        querystring = old_query + "&" + querystring

    return context.request.path + "?" + querystring
