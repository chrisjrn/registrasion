from registrasion.models import commerce
from registrasion.controllers.category import CategoryController
from registrasion.controllers.item import ItemController

from django import template
from django.conf import settings
from django.db.models import Sum
from urllib import urlencode  # TODO: s/urllib/six.moves.urllib/

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


@register.assignment_tag(takes_context=True)
def sold_out_and_unregistered(context):
    ''' If the current user is unregistered, returns True if there are no
    products in the TICKET_PRODUCT_CATEGORY that are available to that user.

    If there *are* products available, the return False.

    If the current user *is* registered, then return None (it's not a
    pertinent question for people who already have a ticket).

    '''

    user = user_for_context(context)
    if hasattr(user, "attendee") and user.attendee.completed_registration:
        # This user has completed registration, and so we don't need to answer
        # whether they have sold out yet.

        # TODO: what if a user has got to the review phase?
        # currently that user will hit the review page, click "Check out and
        # pay", and that will fail. Probably good enough for now.

        return None

    ticket_category = settings.TICKET_PRODUCT_CATEGORY
    categories = available_categories(context)

    return ticket_category not in [cat.id for cat in categories]


class IncludeNode(template.Node):
    ''' https://djangosnippets.org/snippets/2058/ '''


    def __init__(self, template_name):
        # template_name as passed in includes quotmarks?
        # strip them from the start and end
        self.template_name = template_name[1:-1]

    def render(self, context):
        try:
            # Loading the template and rendering it
            return template.loader.render_to_string(
                self.template_name, context=context,
            )
        except template.TemplateDoesNotExist:
            return ""


@register.simple_tag
def template_exists(template_name):
    try:
        template.loader.get_template(template_name)
        return True
    except template.TemplateDoesNotExist:
        return False


@register.tag
def include_if_exists(parser, token):
    """Usage: {% include_if_exists "head.html" %}

    This will fail silently if the template doesn't exist. If it does, it will
    be rendered with the current context.

    From: https://djangosnippets.org/snippets/2058/
    """
    try:
        tag_name, template_name = token.split_contents()
    except ValueError:
        raise template.TemplateSyntaxError, \
            "%r tag requires a single argument" % token.contents.split()[0]

    return IncludeNode(template_name)


@register.filter
def addstr(arg1, arg2):
    """concatenate arg1 & arg2"""
    return str(arg1) + str(arg2)
