import sys

from registrasion import forms
from registrasion import models as rego
from registrasion.controllers import discount
from registrasion.controllers.cart import CartController
from registrasion.controllers.invoice import InvoiceController
from registrasion.controllers.product import ProductController
from registrasion.exceptions import CartValidationError

from collections import namedtuple

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect
from django.shortcuts import render


GuidedRegistrationSection = namedtuple(
    "GuidedRegistrationSection",
    (
        "title",
        "discounts",
        "description",
        "form",
    )
)
GuidedRegistrationSection.__new__.__defaults__ = (
    (None,) * len(GuidedRegistrationSection._fields)
)


def get_form(name):
    dot = name.rindex(".")
    mod_name, form_name = name[:dot], name[dot + 1:]
    __import__(mod_name)
    return getattr(sys.modules[mod_name], form_name)


@login_required
def guided_registration(request, page_id=0):
    ''' Goes through the registration process in order,
    making sure user sees all valid categories.

    WORK IN PROGRESS: the finalised version of this view will allow
    grouping of categories into a specific page. Currently, it just goes
    through each category one by one
    '''

    next_step = redirect("guided_registration")

    sections = []

    attendee = rego.Attendee.get_instance(request.user)

    if attendee.completed_registration:
        return render(
            request,
            "registrasion/guided_registration_complete.html",
            {},
        )

    # Step 1: Fill in a badge and collect a voucher code
    try:
        profile = attendee.attendeeprofilebase
    except ObjectDoesNotExist:
        profile = None

    if not profile:
        # TODO: if voucherform is invalid, make sure
        # that profileform does not save
        voucher_form, voucher_handled = handle_voucher(request, "voucher")
        profile_form, profile_handled = handle_profile(request, "profile")

        voucher_section = GuidedRegistrationSection(
            title="Voucher Code",
            form=voucher_form,
        )

        profile_section = GuidedRegistrationSection(
            title="Profile and Personal Information",
            form=profile_form,
        )

        title = "Attendee information"
        current_step = 1
        sections.append(voucher_section)
        sections.append(profile_section)
    else:
        # We're selling products

        last_category = attendee.highest_complete_category

        # Get the next category
        cats = rego.Category.objects
        cats = cats.filter(id__gt=last_category).order_by("order")

        if cats.count() == 0:
            # We've filled in every category
            attendee.completed_registration = True
            attendee.save()
            return next_step

        if last_category == 0:
            # Only display the first Category
            title = "Select ticket type"
            current_step = 2
            cats = [cats[0]]
        else:
            # Set title appropriately for remaining categories
            current_step = 3
            title = "Additional items"

        for category in cats:
            products = ProductController.available_products(
                request.user,
                category=category,
            )

            prefix = "category_" + str(category.id)
            p = handle_products(request, category, products, prefix)
            products_form, discounts, products_handled = p

            section = GuidedRegistrationSection(
                title=category.name,
                description=category.description,
                discounts=discounts,
                form=products_form,
            )
            if products:
                # This product category does not exist for this user
                sections.append(section)

            if request.method == "POST" and not products_form.errors:
                if category.id > attendee.highest_complete_category:
                    # This is only saved if we pass each form with no errors.
                    attendee.highest_complete_category = category.id

    if sections and request.method == "POST":
        for section in sections:
            if section.form.errors:
                break
        else:
            attendee.save()
            # We've successfully processed everything
            return next_step

    data = {
        "current_step": current_step,
        "sections": sections,
        "title": title,
        "total_steps": 3,
    }
    return render(request, "registrasion/guided_registration.html", data)


@login_required
def edit_profile(request):
    form, handled = handle_profile(request, "profile")

    if handled and not form.errors:
        messages.success(
            request,
            "Your attendee profile was updated.",
        )
        return redirect("dashboard")

    data = {
        "form": form,
    }
    return render(request, "registrasion/profile_form.html", data)


def handle_profile(request, prefix):
    ''' Returns a profile form instance, and a boolean which is true if the
    form was handled. '''
    attendee = rego.Attendee.get_instance(request.user)

    try:
        profile = attendee.attendeeprofilebase
        profile = rego.AttendeeProfileBase.objects.get_subclass(pk=profile.id)
    except ObjectDoesNotExist:
        profile = None

    ProfileForm = get_form(settings.ATTENDEE_PROFILE_FORM)

    # Load a pre-entered name from the speaker's profile,
    # if they have one.
    try:
        speaker_profile = request.user.speaker_profile
        speaker_name = speaker_profile.name
    except ObjectDoesNotExist:
        speaker_name = None

    name_field = ProfileForm.Meta.model.name_field()
    initial = {}
    if profile is None and name_field is not None:
        initial[name_field] = speaker_name

    form = ProfileForm(
        request.POST or None,
        initial=initial,
        instance=profile,
        prefix=prefix
    )

    handled = True if request.POST else False

    if request.POST and form.is_valid():
        form.instance.attendee = attendee
        form.save()

    return form, handled


@login_required
def product_category(request, category_id):
    ''' Registration selections form for a specific category of items.
    '''

    PRODUCTS_FORM_PREFIX = "products"
    VOUCHERS_FORM_PREFIX = "vouchers"

    # Handle the voucher form *before* listing products.
    # Products can change as vouchers are entered.
    v = handle_voucher(request, VOUCHERS_FORM_PREFIX)
    voucher_form, voucher_handled = v

    category_id = int(category_id)  # Routing is [0-9]+
    category = rego.Category.objects.get(pk=category_id)

    products = ProductController.available_products(
        request.user,
        category=category,
    )

    if not products:
        messages.warning(
            request,
            "There are no products available from category: " + category.name,
        )
        return redirect("dashboard")

    p = handle_products(request, category, products, PRODUCTS_FORM_PREFIX)
    products_form, discounts, products_handled = p

    if request.POST and not voucher_handled and not products_form.errors:
        # Only return to the dashboard if we didn't add a voucher code
        # and if there's no errors in the products form
        messages.success(
            request,
            "Your reservations have been updated.",
        )
        return redirect("dashboard")

    data = {
        "category": category,
        "discounts": discounts,
        "form": products_form,
        "voucher_form": voucher_form,
    }

    return render(request, "registrasion/product_category.html", data)


def handle_products(request, category, products, prefix):
    ''' Handles a products list form in the given request. Returns the
    form instance, the discounts applicable to this form, and whether the
    contents were handled. '''

    current_cart = CartController.for_user(request.user)

    ProductsForm = forms.ProductsForm(category, products)

    # Create initial data for each of products in category
    items = rego.ProductItem.objects.filter(
        product__in=products,
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

    products_form = ProductsForm(
        request.POST or None,
        product_quantities=quantities,
        prefix=prefix,
    )

    if request.method == "POST" and products_form.is_valid():
        if products_form.has_changed():
            set_quantities_from_products_form(products_form, current_cart)

        # If category is required, the user must have at least one
        # in an active+valid cart
        if category.required:
            carts = rego.Cart.objects.filter(user=request.user)
            items = rego.ProductItem.objects.filter(
                product__category=category,
                cart=carts,
            )
            if len(items) == 0:
                products_form.add_error(
                    None,
                    "You must have at least one item from this category",
                )
    handled = False if products_form.errors else True

    discounts = discount.available_discounts(request.user, [], products)

    return products_form, discounts, handled


def set_quantities_from_products_form(products_form, current_cart):

    quantities = list(products_form.product_quantities())
    product_quantities = [
        (rego.Product.objects.get(pk=i[0]), i[1]) for i in quantities
    ]
    field_names = dict(
        (i[0][0], i[1][2]) for i in zip(product_quantities, quantities)
    )

    try:
        current_cart.set_quantities(product_quantities)
    except CartValidationError as ve:
        for ve_field in ve.error_list:
            product, message = ve_field.message
            if product in field_names:
                field = field_names[product]
            else:
                field = None
            products_form.add_error(field, message)


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

    if request.user != inv.cart.user and not request.user.is_staff:
        raise Http404()

    current_invoice = InvoiceController(inv)

    data = {
        "invoice": current_invoice.invoice,
    }

    return render(request, "registrasion/invoice.html", data)


@login_required
def pay_invoice(request, invoice_id):
    ''' Marks the invoice with the given invoice id as paid.
    WORK IN PROGRESS FUNCTION. Must be replaced with real payment workflow.

    '''
    invoice_id = int(invoice_id)
    inv = rego.Invoice.objects.get(pk=invoice_id)
    current_invoice = InvoiceController(inv)
    if not current_invoice.invoice.paid and not current_invoice.invoice.void:
        current_invoice.pay("Demo invoice payment", inv.value)

    return redirect("invoice", current_invoice.invoice.id)
