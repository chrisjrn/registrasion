from registrasion.models import inventory

from django import forms

# Staff-facing forms.

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
