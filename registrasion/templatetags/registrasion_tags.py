from registrasion import models as rego

from django import template

register = template.Library()


@register.assignment_tag(takes_context=True)
def available_categories(context):
    ''' Returns all of the available product categories '''
    return rego.Category.objects.all()
