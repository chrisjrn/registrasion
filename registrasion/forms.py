import models as rego

from django import forms


def ProductsForm(products):

    PREFIX = "product_"

    def field_name(product):
        return PREFIX + ("%d" % product.id)

    class _ProductsForm(forms.Form):

        def __init__(self, *a, **k):
            if "product_quantities" in k:
                initial = _ProductsForm.initial_data(k["product_quantities"])
                k["initial"] = initial
                del k["product_quantities"]
            super(_ProductsForm, self).__init__(*a, **k)

        @classmethod
        def initial_data(cls, product_quantities):
            ''' Prepares initial data for an instance of this form.
            product_quantities is a sequence of (product,quantity) tuples '''
            initial = {}
            for product, quantity in product_quantities:
                initial[field_name(product)] = quantity

            return initial

        def product_quantities(self):
            ''' Yields a sequence of (product, quantity) tuples from the
            cleaned form data. '''
            for name, value in self.cleaned_data.items():
                if name.startswith(PREFIX):
                    product_id = int(name[len(PREFIX):])
                    yield (product_id, value, name)

    for product in products:

        help_text = "$%d -- %s" % (product.price, product.description)

        field = forms.IntegerField(
            label=product.name,
            help_text=help_text,
        )
        _ProductsForm.base_fields[field_name(product)] = field

    return _ProductsForm


class ProfileForm(forms.ModelForm):
    ''' A form for requesting badge and profile information. '''

    class Meta:
        model = rego.BadgeAndProfile
        exclude = ['attendee']


class VoucherForm(forms.Form):
    voucher = forms.CharField(
        label="Voucher code",
        help_text="If you have a voucher code, enter it here",
        required=False,
    )
