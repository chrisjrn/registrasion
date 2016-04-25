from registrasion.models import commerce
from registrasion.models import inventory

from django import forms


class ApplyCreditNoteForm(forms.Form):

    def __init__(self, user, *a, **k):
        ''' User: The user whose invoices should be made available as
        choices. '''
        self.user = user
        super(ApplyCreditNoteForm, self).__init__(*a, **k)

        self.fields["invoice"].choices = self._unpaid_invoices_for_user

    def _unpaid_invoices_for_user(self):
        invoices = commerce.Invoice.objects.filter(
            status=commerce.Invoice.STATUS_UNPAID,
            user=self.user,
        )

        return [
            (invoice.id, "Invoice %(id)d - $%(value)d" % invoice.__dict__)
            for invoice in invoices
        ]

    invoice = forms.ChoiceField(
        required=True,
    )


class ManualCreditNoteRefundForm(forms.ModelForm):

    class Meta:
        model = commerce.ManualCreditNoteRefund
        fields = ["reference"]


class ManualPaymentForm(forms.ModelForm):

    class Meta:
        model = commerce.ManualPayment
        fields = ["reference", "amount"]


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
    def set_fields(cls, category, products):
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
    def set_fields(cls, category, products):
        for product in products:
            if product.description:
                help_text = "$%d each -- %s" % (
                    product.price,
                    product.description,
                )
            else:
                help_text = "$%d each" % product.price

            field = forms.IntegerField(
                label=product.name,
                help_text=help_text,
                min_value=0,
                max_value=500,  # Issue #19. We should figure out real limit.
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


class _RadioButtonProductsForm(_ProductsForm):
    ''' Products entry form that allows users to enter quantities
    of desired products. '''

    FIELD = "chosen_product"

    @classmethod
    def set_fields(cls, category, products):
        choices = []
        for product in products:

            choice_text = "%s -- $%d" % (product.name, product.price)
            choices.append((product.id, choice_text))

        if not category.required:
            choices.append((0, "No selection"))

        cls.base_fields[cls.FIELD] = forms.TypedChoiceField(
            label=category.name,
            widget=forms.RadioSelect,
            choices=choices,
            empty_value=0,
            coerce=int,
        )

    @classmethod
    def initial_data(cls, product_quantities):
        initial = {}

        for product, quantity in product_quantities:
            if quantity > 0:
                initial[cls.FIELD] = product.id
                break

        return initial

    def product_quantities(self):
        ours = self.cleaned_data[self.FIELD]
        choices = self.fields[self.FIELD].choices
        for choice_value, choice_display in choices:
            if choice_value == 0:
                continue
            yield (
                choice_value,
                1 if ours == choice_value else 0,
                self.FIELD,
            )


def ProductsForm(category, products):
    ''' Produces an appropriate _ProductsForm subclass for the given render
    type. '''

    # Each Category.RENDER_TYPE value has a subclass here.
    RENDER_TYPES = {
        inventory.Category.RENDER_TYPE_QUANTITY: _QuantityBoxProductsForm,
        inventory.Category.RENDER_TYPE_RADIO: _RadioButtonProductsForm,
    }

    # Produce a subclass of _ProductsForm which we can alter the base_fields on
    class ProductsForm(RENDER_TYPES[category.render_type]):
        pass

    ProductsForm.set_fields(category, products)
    return ProductsForm


class VoucherForm(forms.Form):
    voucher = forms.CharField(
        label="Voucher code",
        help_text="If you have a voucher code, enter it here",
        required=False,
    )
