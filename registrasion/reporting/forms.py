from registrasion.models import conditions
from registrasion.models import inventory

from django import forms

# Reporting forms.


class DiscountForm(forms.Form):
    discount = forms.ModelMultipleChoiceField(
        queryset=conditions.DiscountBase.objects.all(),
        required=False,
    )


class ProductAndCategoryForm(forms.Form):
    product = forms.ModelMultipleChoiceField(
        queryset=inventory.Product.objects.all(),
        required=False,
    )
    category = forms.ModelMultipleChoiceField(
        queryset=inventory.Category.objects.all(),
        required=False,
    )


class UserIdForm(forms.Form):
    user = forms.IntegerField(
        label="User ID",
        required=False,
    )


def model_fields_form_factory(model):
    ''' Creates a form for specifying fields from a model to display. '''

    fields = model._meta.get_fields()

    choices = []
    for field in fields:
        if hasattr(field, "verbose_name"):
            choices.append((field.name, field.verbose_name))

    class ModelFieldsForm(forms.Form):
        fields = forms.MultipleChoiceField(
            choices=choices,
            required=False,
        )

    return ModelFieldsForm
