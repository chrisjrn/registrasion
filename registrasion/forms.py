import models as rego

from django import forms


class ProductItemForm(forms.Form):
    product = forms.ModelChoiceField(queryset=None, empty_label=None)
    quantity = forms.IntegerField()

    def __init__(self, category, *a, **k):
        super(ProductItemForm, self).__init__(*a, **k)
        products = rego.Product.objects.filter(category=category)
        self.fields['product'].queryset = products
