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
