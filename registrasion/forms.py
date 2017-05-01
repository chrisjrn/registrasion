from registrasion.controllers.product import ProductController
from registrasion.models import commerce
from registrasion.models import inventory

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q


class ApplyCreditNoteForm(forms.Form):

    def __init__(self, user, *a, **k):
        ''' User: The user whose invoices should be made available as
        choices. '''
        self.user = user
        super(ApplyCreditNoteForm, self).__init__(*a, **k)

        self.fields["invoice"].choices = self._unpaid_invoices

    def _unpaid_invoices(self):
        invoices = commerce.Invoice.objects.filter(
            status=commerce.Invoice.STATUS_UNPAID,
        ).select_related("user")

        invoices_annotated = [invoice.__dict__ for invoice in invoices]
        users = dict((inv.user.id, inv.user) for inv in invoices)
        for invoice in invoices_annotated:
            invoice.update({
                "user_id": users[invoice["user_id"]].id,
                "user_email": users[invoice["user_id"]].email,
            })


        key = lambda inv: (0 - (inv["user_id"] == self.user.id), inv["id"])
        invoices_annotated.sort(key=key)

        template = "Invoice %(id)d - user: %(user_email)s (%(user_id)d) -  $%(value)d"
        return [
            (invoice["id"], template % invoice)
            for invoice in invoices_annotated
        ]

    invoice = forms.ChoiceField(
        required=True,
    )
    verify = forms.BooleanField(
        required=True,
        help_text="Have you verified that this is the correct invoice?",
    )


class CancellationFeeForm(forms.Form):

    percentage = forms.DecimalField(
        required=True,
        min_value=0,
        max_value=100,
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
# and the fields added as needs be. ProductsForm (the function) is responsible
# for the subclassing.

def ProductsForm(category, products):
    ''' Produces an appropriate _ProductsForm subclass for the given render
    type. '''

    # Each Category.RENDER_TYPE value has a subclass here.
    cat = inventory.Category
    RENDER_TYPES = {
        cat.RENDER_TYPE_QUANTITY: _QuantityBoxProductsForm,
        cat.RENDER_TYPE_RADIO: _RadioButtonProductsForm,
        cat.RENDER_TYPE_ITEM_QUANTITY: _ItemQuantityProductsForm,
        cat.RENDER_TYPE_CHECKBOX: _CheckboxProductsForm,
    }

    # Produce a subclass of _ProductsForm which we can alter the base_fields on
    class ProductsForm(RENDER_TYPES[category.render_type]):
        pass

    ProductsForm.set_fields(category, products)

    if category.render_type == inventory.Category.RENDER_TYPE_ITEM_QUANTITY:
        ProductsForm = forms.formset_factory(
            ProductsForm,
            formset=_ItemQuantityProductsFormSet,
        )

    return ProductsForm


class _HasProductsFields(object):

    PRODUCT_PREFIX = "product_"

    ''' Base class for product entry forms. '''
    def __init__(self, *a, **k):
        if "product_quantities" in k:
            initial = self.initial_data(k["product_quantities"])
            k["initial"] = initial
            del k["product_quantities"]
        super(_HasProductsFields, self).__init__(*a, **k)

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

    def add_product_error(self, product, error):
        ''' Adds an error to the given product's field '''

        ''' if product in field_names:
            field = field_names[product]
        elif isinstance(product, inventory.Product):
            return
        else:
            field = None '''

        self.add_error(self.field_name(product), error)


class _ProductsForm(_HasProductsFields, forms.Form):
    pass


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
                yield (product_id, value)


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
            )

    def add_product_error(self, product, error):
        self.add_error(self.FIELD, error)


class _CheckboxProductsForm(_ProductsForm):
    ''' Products entry form that allows users to say yes or no
    to desired products. Basically, it's a quantity form, but the quantity
    is either zero or one.'''

    @classmethod
    def set_fields(cls, category, products):
        for product in products:
            field = forms.BooleanField(
                label='%s -- %s' % (product.name, product.price),
                required=False,
            )
            cls.base_fields[cls.field_name(product)] = field

    @classmethod
    def initial_data(cls, product_quantities):
        initial = {}
        for product, quantity in product_quantities:
            initial[cls.field_name(product)] = bool(quantity)

        return initial

    def product_quantities(self):
        for name, value in self.cleaned_data.items():
            if name.startswith(self.PRODUCT_PREFIX):
                product_id = int(name[len(self.PRODUCT_PREFIX):])
                yield (product_id, int(value))


class _ItemQuantityProductsForm(_ProductsForm):
    ''' Products entry form that allows users to select a product type, and
     enter a quantity of that product. This version _only_ allows a single
     product type to be purchased. This form is usually used in concert with
     the _ItemQuantityProductsFormSet to allow selection of multiple
     products.'''

    CHOICE_FIELD = "choice"
    QUANTITY_FIELD = "quantity"

    @classmethod
    def set_fields(cls, category, products):
        choices = []

        if not category.required:
            choices.append((0, "---"))

        for product in products:
            choice_text = "%s -- $%d each" % (product.name, product.price)
            choices.append((product.id, choice_text))

        cls.base_fields[cls.CHOICE_FIELD] = forms.TypedChoiceField(
            label=category.name,
            widget=forms.Select,
            choices=choices,
            initial=0,
            empty_value=0,
            coerce=int,
        )

        cls.base_fields[cls.QUANTITY_FIELD] = forms.IntegerField(
            label="Quantity",  # TODO: internationalise
            min_value=0,
            max_value=500,  # Issue #19. We should figure out real limit.
        )

    @classmethod
    def initial_data(cls, product_quantities):
        initial = {}

        for product, quantity in product_quantities:
            if quantity > 0:
                initial[cls.CHOICE_FIELD] = product.id
                initial[cls.QUANTITY_FIELD] = quantity
                break

        return initial

    def product_quantities(self):
        our_choice = self.cleaned_data[self.CHOICE_FIELD]
        our_quantity = self.cleaned_data[self.QUANTITY_FIELD]
        choices = self.fields[self.CHOICE_FIELD].choices
        for choice_value, choice_display in choices:
            if choice_value == 0:
                continue
            yield (
                choice_value,
                our_quantity if our_choice == choice_value else 0,
            )

    def add_product_error(self, product, error):
        if self.CHOICE_FIELD not in self.cleaned_data:
            return

        if product.id == self.cleaned_data[self.CHOICE_FIELD]:
            self.add_error(self.CHOICE_FIELD, error)
            self.add_error(self.QUANTITY_FIELD, error)


class _ItemQuantityProductsFormSet(_HasProductsFields, forms.BaseFormSet):

    @classmethod
    def set_fields(cls, category, products):
        raise ValueError("set_fields must be called on the underlying Form")

    @classmethod
    def initial_data(cls, product_quantities):
        ''' Prepares initial data for an instance of this form.
        product_quantities is a sequence of (product,quantity) tuples '''

        f = [
            {
                _ItemQuantityProductsForm.CHOICE_FIELD: product.id,
                _ItemQuantityProductsForm.QUANTITY_FIELD: quantity,
            }
            for product, quantity in product_quantities
            if quantity > 0
        ]
        return f

    def product_quantities(self):
        ''' Yields a sequence of (product, quantity) tuples from the
        cleaned form data. '''

        products = set()
        # Track everything so that we can yield some zeroes
        all_products = set()

        for form in self:
            if form.empty_permitted and not form.cleaned_data:
                # This is the magical empty form at the end of the list.
                continue

            for product, quantity in form.product_quantities():
                all_products.add(product)
                if quantity == 0:
                    continue
                if product in products:
                    form.add_error(
                        _ItemQuantityProductsForm.CHOICE_FIELD,
                        "You may only choose each product type once.",
                    )
                    form.add_error(
                        _ItemQuantityProductsForm.QUANTITY_FIELD,
                        "You may only choose each product type once.",
                    )
                products.add(product)
                yield product, quantity

        for product in (all_products - products):
            yield product, 0

    def add_product_error(self, product, error):
        for form in self.forms:
            form.add_product_error(product, error)

    @property
    def errors(self):
        _errors = super(_ItemQuantityProductsFormSet, self).errors
        if False not in [not form.errors for form in self.forms]:
            return []
        else:
            return _errors


class VoucherForm(forms.Form):
    voucher = forms.CharField(
        label="Voucher code",
        help_text="If you have a voucher code, enter it here",
        required=False,
    )


def staff_products_form_factory(user):
    ''' Creates a StaffProductsForm that restricts the available products to
    those that are available to a user. '''

    products = inventory.Product.objects.all()
    products = ProductController.available_products(user, products=products)

    product_ids = [product.id for product in products]
    product_set = inventory.Product.objects.filter(id__in=product_ids)

    class StaffProductsForm(forms.Form):
        ''' Form for allowing staff to add an item to a user's cart. '''

        product = forms.ModelChoiceField(
            widget=forms.Select,
            queryset=product_set,
        )

        quantity = forms.IntegerField(
            min_value=0,
        )

    return StaffProductsForm

def staff_products_formset_factory(user):
    ''' Creates a formset of StaffProductsForm for the given user. '''
    form_type = staff_products_form_factory(user)
    return forms.formset_factory(form_type)


class InvoicesWithProductAndStatusForm(forms.Form):
    invoice = forms.ModelMultipleChoiceField(
        widget=forms.CheckboxSelectMultiple,
        queryset=commerce.Invoice.objects.all(),
    )

    def __init__(self, *a, **k):
        category = k.pop('category', None) or []
        product = k.pop('product', None) or []
        status = int(k.pop('status', None) or 0)

        category = [int(i) for i in category]
        product = [int(i) for i in product]

        super(InvoicesWithProductAndStatusForm, self).__init__(*a, **k)
        print status

        qs = commerce.Invoice.objects.filter(
            status=status or commerce.Invoice.STATUS_UNPAID,
        ).filter(
            Q(lineitem__product__category__in=category) |
            Q(lineitem__product__in=product)
        )

        # Uniqify
        qs = commerce.Invoice.objects.filter(
            id__in=qs,
        )

        qs = qs.select_related("user__attendee__attendeeprofilebase")
        qs = qs.order_by("id")

        self.fields['invoice'].queryset = qs
        #self.fields['invoice'].initial = [i.id for i in qs] # UNDO THIS LATER


class InvoiceEmailForm(InvoicesWithProductAndStatusForm):

    ACTION_PREVIEW = 1
    ACTION_SEND = 2

    ACTION_CHOICES = (
        (ACTION_PREVIEW, "Preview"),
        (ACTION_SEND, "Send emails"),
    )

    from_email = forms.CharField()
    subject = forms.CharField()
    body = forms.CharField(
        widget=forms.Textarea,
    )
    action = forms.TypedChoiceField(
        widget=forms.RadioSelect,
        coerce=int,
        choices=ACTION_CHOICES,
        initial=ACTION_PREVIEW,
    )
