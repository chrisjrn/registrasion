from registrasion import forms
from registrasion import models as rego
from registrasion.controllers import discount
from registrasion.controllers.cart import CartController
from registrasion.controllers.invoice import InvoiceController
from registrasion.controllers.product import ProductController

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect
from django.shortcuts import render


@login_required
def guided_registration(request, page_id=0):
    ''' Goes through the registration process in order,
    making sure user sees all valid categories.

    WORK IN PROGRESS: the finalised version of this view will allow
    grouping of categories into a specific page. Currently, it just goes
    through each category one by one
    '''

    dashboard = redirect("dashboard")
    next_step = redirect("guided_registration")

    attendee = rego.Attendee.get_instance(request.user)
    if attendee.completed_registration:
        return dashboard

    # Step 1: Fill in a badge
    profile = rego.BadgeAndProfile.get_instance(attendee)

    if profile is None:
        ret = edit_profile(request)
        profile_new = rego.BadgeAndProfile.get_instance(attendee)
        if profile_new is None:
            # No new profile was created
            return ret
        else:
            return next_step

    # Step 2: Go through each of the categories in order
    category = attendee.highest_complete_category

    # Get the next category
    cats = rego.Category.objects
    cats = cats.filter(id__gt=category).order_by("order")

    if len(cats) == 0:
        # We've filled in every category
        attendee.completed_registration = True
        attendee.save()
        return dashboard

    ret = product_category(request, cats[0].id)
    attendee_new = rego.Attendee.get_instance(request.user)
    if attendee_new.highest_complete_category == category:
        # We've not yet completed this category
        return ret
    else:
        return next_step


@login_required
def edit_profile(request):
    attendee = rego.Attendee.get_instance(request.user)

    try:
        profile = rego.BadgeAndProfile.objects.get(attendee=attendee)
    except ObjectDoesNotExist:
        profile = None

    form = forms.ProfileForm(request.POST or None, instance=profile)

    if request.POST and form.is_valid():
        form.instance.attendee = attendee
        form.save()

    data = {
        "form": form,
    }
    return render(request, "profile_form.html", data)


@login_required
def product_category(request, category_id):
    ''' Registration selections form for a specific category of items.
    '''

    PRODUCTS_FORM_PREFIX = "products"
    VOUCHERS_FORM_PREFIX = "vouchers"

    category_id = int(category_id)  # Routing is [0-9]+
    category = rego.Category.objects.get(pk=category_id)
    current_cart = CartController.for_user(request.user)

    attendee = rego.Attendee.get_instance(request.user)

    # Handle the voucher form *before* listing products.
    v = handle_voucher(request, VOUCHERS_FORM_PREFIX)
    voucher_form, voucher_handled = v
    if voucher_handled:
        # Do not handle product form
        pass

    products = rego.Product.objects.filter(category=category)
    products = products.order_by("order")
    products = ProductController.available_products(
        request.user,
        products=products,
    )

    ProductsForm = forms.ProductsForm(products)

    if request.method == "POST":
        cat_form = ProductsForm(
            request.POST,
            request.FILES,
            prefix=PRODUCTS_FORM_PREFIX)

        if voucher_handled:
            # The voucher form was handled here.
            pass
        elif cat_form.is_valid():
            try:
                handle_valid_cat_form(cat_form, current_cart)
            except ValidationError:
                pass

            # If category is required, the user must have at least one
            # in an active+valid cart

            if category.required:
                carts = rego.Cart.reserved_carts()
                carts = carts.filter(user=request.user)
                items = rego.ProductItem.objects.filter(
                    product__category=category,
                    cart=carts,
                )
                if len(items) == 0:
                    cat_form.add_error(
                        None,
                        "You must have at least one item from this category",
                    )

            if not cat_form.errors:
                if category_id > attendee.highest_complete_category:
                    attendee.highest_complete_category = category_id
                    attendee.save()
                return redirect("dashboard")

    else:
        # Create initial data for each of products in category
        items = rego.ProductItem.objects.filter(
            product__category=category,
            cart=current_cart.cart,
        )
        quantities = []
        for product in products:
            # Only add items that are enabled.
            try:
                quantity = items.get(product=product).quantity
            except ObjectDoesNotExist:
                quantity = 0
            quantities.append((product, quantity))

        cat_form = ProductsForm(
            prefix=PRODUCTS_FORM_PREFIX,
            product_quantities=quantities,
        )

    discounts = discount.available_discounts(request.user, [], products)
    data = {
        "category": category,
        "discounts": discounts,
        "form": cat_form,
        "voucher_form": voucher_form,
    }

    return render(request, "product_category.html", data)


@transaction.atomic
def handle_valid_cat_form(cat_form, current_cart):
    for product_id, quantity, field_name in cat_form.product_quantities():
        product = rego.Product.objects.get(pk=product_id)
        try:
            current_cart.set_quantity(product, quantity, batched=True)
        except ValidationError as ve:
            cat_form.add_error(field_name, ve)
    if cat_form.errors:
        raise ValidationError("Cannot add that stuff")
    current_cart.end_batch()

def handle_voucher(request, prefix):
    ''' Handles a voucher form in the given request. Returns the voucher
    form instance, and whether the voucher code was handled. '''

    voucher_form = forms.VoucherForm(request.POST or None, prefix=prefix)
    current_cart = CartController.for_user(request.user)

    if (voucher_form.is_valid() and
            voucher_form.cleaned_data["voucher"].strip()):

        voucher = voucher_form.cleaned_data["voucher"]
        voucher = rego.Voucher.normalise_code(voucher)

        if len(current_cart.cart.vouchers.filter(code=voucher)) > 0:
            # This voucher has already been applied to this cart.
            # Do not apply code
            handled = False
        else:
            try:
                current_cart.apply_voucher(voucher)
            except Exception as e:
                voucher_form.add_error("voucher", e)
            handled = True
    else:
        handled = False

    return (voucher_form, handled)

@login_required
def checkout(request):
    ''' Runs checkout for the current cart of items, ideally generating an
    invoice. '''

    current_cart = CartController.for_user(request.user)
    current_invoice = InvoiceController.for_cart(current_cart.cart)

    return redirect("invoice", current_invoice.invoice.id)


@login_required
def invoice(request, invoice_id):
    ''' Displays an invoice for a given invoice id. '''

    invoice_id = int(invoice_id)
    inv = rego.Invoice.objects.get(pk=invoice_id)
    current_invoice = InvoiceController(inv)

    data = {
        "invoice": current_invoice.invoice,
    }

    return render(request, "invoice.html", data)


@login_required
def pay_invoice(request, invoice_id):
    ''' Marks the invoice with the given invoice id as paid.
    WORK IN PROGRESS FUNCTION. Must be replaced with real payment workflow.

    '''

    invoice_id = int(invoice_id)
    inv = rego.Invoice.objects.get(pk=invoice_id)
    current_invoice = InvoiceController(inv)
    if not inv.paid and current_invoice.is_valid():
        current_invoice.pay("Demo invoice payment", inv.value)

    return redirect("invoice", current_invoice.invoice.id)
