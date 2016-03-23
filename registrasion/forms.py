import models as rego

from django import forms


def CategoryForm(category):

    PREFIX = "product_"

    def field_name(product):
        return PREFIX + ("%d" % product.id)

    class _CategoryForm(forms.Form):

        @staticmethod
        def initial_data(product_quantities):
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

        def disable_product(self, product):
            ''' Removes a given product from this form. '''
            del self.fields[field_name(product)]

    products = rego.Product.objects.filter(category=category).order_by("order")
    for product in products:

        help_text = "$%d -- %s" % (product.price, product.description)

        field = forms.IntegerField(
            label=product.name,
            help_text=help_text,
        )
        _CategoryForm.base_fields[field_name(product)] = field

    return _CategoryForm

class VoucherForm(forms.Form):
    voucher = forms.CharField(
        label="Voucher code",
        help_text="If you have a voucher code, enter it here",
        required=True,
    )
