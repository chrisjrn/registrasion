import models as rego

from django import forms


# Products forms -- none of these have any fields: they are to be subclassed
# and the fields added as needs be.

class _ProductsForm(forms.Form):

    PRODUCT_PREFIX = "product_"

    ''' Base class for product entry forms. '''
    def __init__(self, *a, **k):
        if "product_quantities" in k:
            initial = self.initial_data(k["product_quantities"])
            k["initial"] = initial
            del k["product_quantities"]
        super(_ProductsForm, self).__init__(*a, **k)

    @classmethod
    def field_name(cls, product):
        return cls.PRODUCT_PREFIX + ("%d" % product.id)

    @classmethod
    def set_fields(cls, products):
        ''' Sets the base_fields on this _ProductsForm to allow selecting
        from the provided products. '''
        pass

    @classmethod
    def initial_data(cls, product_quantites):
        ''' Prepares initial data for an instance of this form.
        product_quantities is a sequence of (product,quantity) tuples '''
        return {}

    def product_quantities(self):
        ''' Yields a sequence of (product, quantity) tuples from the
        cleaned form data. '''
        return iter([])


class _QuantityBoxProductsForm(_ProductsForm):
    ''' Products entry form that allows users to enter quantities
    of desired products. '''

    @classmethod
    def set_fields(cls, products):
        for product in products:
            help_text = "$%d -- %s" % (product.price, product.description)

            field = forms.IntegerField(
                label=product.name,
                help_text=help_text,
            )
            cls.base_fields[cls.field_name(product)] = field

    @classmethod
    def initial_data(cls, product_quantities):
        initial = {}
        for product, quantity in product_quantities:
            initial[cls.field_name(product)] = quantity

        return initial

    def product_quantities(self):
        for name, value in self.cleaned_data.items():
            if name.startswith(self.PRODUCT_PREFIX):
                product_id = int(name[len(self.PRODUCT_PREFIX):])
                yield (product_id, value, name)


def ProductsForm(products):
    ''' Produces an appropriate _ProductsForm subclass for the given render
    type. '''

    if True:
        class ProductsForm(_QuantityBoxProductsForm):
            pass

    ProductsForm.set_fields(products)
    return ProductsForm


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
