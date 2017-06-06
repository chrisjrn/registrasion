import datetime
import zipfile

from . import forms
from . import util
from .models import commerce
from .models import inventory
from .models import people
from .controllers.batch import BatchController
from .controllers.cart import CartController
from .controllers.category import CategoryController
from .controllers.credit_note import CreditNoteController
from .controllers.discount import DiscountController
from .controllers.invoice import InvoiceController
from .controllers.item import ItemController
from .controllers.product import ProductController
from .exceptions import CartValidationError

from collections import namedtuple

from django import forms as django_forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.core.exceptions import ValidationError
from django.core.mail import send_mass_mail
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.shortcuts import render
from django.template import Context, Template, loader


_GuidedRegistrationSection = namedtuple(
    "GuidedRegistrationSection",
    (
        "title",
        "discounts",
        "description",
        "form",
    )
)


@util.all_arguments_optional
class GuidedRegistrationSection(_GuidedRegistrationSection):
    ''' Represents a section of a guided registration page.

    Attributes:
       title (str): The title of the section.

       discounts ([registrasion.contollers.discount.DiscountAndQuantity, ...]):
            A list of discount objects that are available in the section. You
            can display ``.clause`` to show what the discount applies to, and
            ``.quantity`` to display the number of times that discount can be
            applied.

       description (str): A description of the section.

       form (forms.Form): A form to display.
    '''
    pass


@login_required
def guided_registration(request, page_number=None):
    ''' Goes through the registration process in order, making sure user sees
    all valid categories.

    The user must be logged in to see this view.

    Parameter:
        page_number:
            1) Profile form (and e-mail address?)
            2) Ticket type
            3) Remaining products
            4) Mark registration as complete

    Returns:
        render: Renders ``registrasion/guided_registration.html``,
            with the following data::

                {
                    "current_step": int(),  # The current step in the
                                            # registration
                    "sections": sections,   # A list of
                                            # GuidedRegistrationSections
                    "title": str(),         # The title of the page
                    "total_steps": int(),   # The total number of steps
                }

    '''

    PAGE_PROFILE = 1
    PAGE_TICKET = 2
    PAGE_PRODUCTS = 3
    PAGE_PRODUCTS_MAX = 4
    TOTAL_PAGES = 4

    ticket_category = inventory.Category.objects.get(
        id=settings.TICKET_PRODUCT_CATEGORY
    )
    cart = CartController.for_user(request.user)

    attendee = people.Attendee.get_instance(request.user)

    # This guided registration process is only for people who have
    # not completed registration (and has confusing behaviour if you go
    # back to it.)
    if attendee.completed_registration:
        return redirect(review)

    # Calculate the current maximum page number for this user.
    has_profile = hasattr(attendee, "attendeeprofilebase")
    if not has_profile:
        # If there's no profile, they have to go to the profile page.
        max_page = PAGE_PROFILE
        redirect_page = PAGE_PROFILE
    else:
        # We have a profile.
        # Do they have a ticket?
        products = inventory.Product.objects.filter(
            productitem__cart=cart.cart
        )
        products = products.filter(category=ticket_category)

        if products.count() == 0:
            # If no ticket, they can only see the profile or ticket page.
            max_page = PAGE_TICKET
            redirect_page = PAGE_TICKET
        else:
            # If there's a ticket, they should *see* the general products page#
            # but be able to go to the overflow page if needs be.
            max_page = PAGE_PRODUCTS_MAX
            redirect_page = PAGE_PRODUCTS

    if page_number is None or int(page_number) > max_page:
        return redirect("guided_registration", redirect_page)

    page_number = int(page_number)

    next_step = redirect("guided_registration", page_number + 1)

    with BatchController.batch(request.user):

        # This view doesn't work if the conference has sold out.
        available = ProductController.available_products(
            request.user, category=ticket_category
        )
        if not available:
            messages.error(request, "There are no more tickets available.")
            return redirect("dashboard")

        sections = []

        # Build up the list of sections
        if page_number == PAGE_PROFILE:
            # Profile bit
            title = "Attendee information"
            sections = _guided_registration_profile_and_voucher(request)
        elif page_number == PAGE_TICKET:
            # Select ticket
            title = "Select ticket type"
            sections = _guided_registration_products(
                request, GUIDED_MODE_TICKETS_ONLY
            )
        elif page_number == PAGE_PRODUCTS:
            # Select additional items
            title = "Additional items"
            sections = _guided_registration_products(
                request, GUIDED_MODE_ALL_ADDITIONAL
            )
        elif page_number == PAGE_PRODUCTS_MAX:
            # Items enabled by things on page 3 -- only shows things
            # that have not been marked as complete.
            title = "More additional items"
            sections = _guided_registration_products(
                request, GUIDED_MODE_EXCLUDE_COMPLETE
            )

        if not sections:
            # We've filled in every category
            attendee.completed_registration = True
            attendee.save()
            return redirect("review")

        if sections and request.method == "POST":
            for section in sections:
                if section.form.errors:
                    break
            else:
                # We've successfully processed everything
                return next_step

    data = {
        "current_step": page_number,
        "sections": sections,
        "title": title,
        "total_steps": 3,
    }
    return render(request, "registrasion/guided_registration.html", data)


GUIDED_MODE_TICKETS_ONLY = 2
GUIDED_MODE_ALL_ADDITIONAL = 3
GUIDED_MODE_EXCLUDE_COMPLETE = 4


@login_required
def _guided_registration_products(request, mode):
    sections = []

    SESSION_KEY = "guided_registration"
    MODE_KEY = "mode"
    CATS_KEY = "cats"

    attendee = people.Attendee.get_instance(request.user)

    # Get the next category
    cats = inventory.Category.objects.order_by("order")  # TODO: default order?

    # Fun story: If _any_ of the category forms result in an error, but other
    # new products get enabled with a flag, those new products will appear.
    # We need to make sure that we only display the products that were valid
    # in the first place. So we track them in a session, and refresh only if
    # the page number does not change. Cheap!

    if SESSION_KEY in request.session:
        session_struct = request.session[SESSION_KEY]
        old_mode = session_struct[MODE_KEY]
        old_cats = session_struct[CATS_KEY]
    else:
        old_mode = None
        old_cats = []

    if mode == old_mode:
        cats = cats.filter(id__in=old_cats)
    elif mode == GUIDED_MODE_TICKETS_ONLY:
        cats = cats.filter(id=settings.TICKET_PRODUCT_CATEGORY)
    elif mode == GUIDED_MODE_ALL_ADDITIONAL:
        cats = cats.exclude(id=settings.TICKET_PRODUCT_CATEGORY)
    elif mode == GUIDED_MODE_EXCLUDE_COMPLETE:
        cats = cats.exclude(id=settings.TICKET_PRODUCT_CATEGORY)
        cats = cats.exclude(id__in=old_cats)

    # We update the session key at the end of this method
    # once we've found all the categories that have available products

    all_products = inventory.Product.objects.filter(
        category__in=cats,
    ).select_related("category")

    seen_categories = []

    with BatchController.batch(request.user):
        available_products = set(ProductController.available_products(
            request.user,
            products=all_products,
        ))

        if len(available_products) == 0:
            return []

        has_errors = False

        for category in cats:
            products = [
                i for i in available_products
                if i.category == category
            ]

            prefix = "category_" + str(category.id)
            p = _handle_products(request, category, products, prefix)
            products_form, discounts, products_handled = p

            section = GuidedRegistrationSection(
                title=category.name,
                description=category.description,
                discounts=discounts,
                form=products_form,
            )

            if products:
                # This product category has items to show.
                sections.append(section)
                seen_categories.append(category)

    # Update the cache with the newly calculated values
    cat_ids = [cat.id for cat in seen_categories]
    request.session[SESSION_KEY] = {MODE_KEY: mode, CATS_KEY: cat_ids}

    return sections


@login_required
def _guided_registration_profile_and_voucher(request):
    voucher_form, voucher_handled = _handle_voucher(request, "voucher")
    profile_form, profile_handled = _handle_profile(request, "profile")

    voucher_section = GuidedRegistrationSection(
        title="Voucher Code",
        form=voucher_form,
    )

    profile_section = GuidedRegistrationSection(
        title="Profile and Personal Information",
        form=profile_form,
    )

    return [voucher_section, profile_section]


@login_required
def review(request):
    ''' View for the review page. '''

    return render(
        request,
        "registrasion/review.html",
        {},
    )


@login_required
def edit_profile(request):
    ''' View for editing an attendee's profile

    The user must be logged in to edit their profile.

    Returns:
        redirect or render:
            In the case of a ``POST`` request, it'll redirect to ``dashboard``,
            or otherwise, it will render ``registrasion/profile_form.html``
            with data::

                {
                    "form": form,  # Instance of ATTENDEE_PROFILE_FORM.
                }

    '''

    form, handled = _handle_profile(request, "profile")

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


# Define the attendee profile form, or get a default.
try:
    ProfileForm = util.get_object_from_name(settings.ATTENDEE_PROFILE_FORM)
except:
    class ProfileForm(django_forms.ModelForm):
        class Meta:
            model = util.get_object_from_name(settings.ATTENDEE_PROFILE_MODEL)
            exclude = ["attendee"]


def _handle_profile(request, prefix):
    ''' Returns a profile form instance, and a boolean which is true if the
    form was handled. '''
    attendee = people.Attendee.get_instance(request.user)

    try:
        profile = attendee.attendeeprofilebase
        profile = people.AttendeeProfileBase.objects.get_subclass(
            pk=profile.id,
        )
    except ObjectDoesNotExist:
        profile = None

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
    ''' Form for selecting products from an individual product category.

    Arguments:
        category_id (castable to int): The id of the category to display.

    Returns:
        redirect or render:
            If the form has been sucessfully submitted, redirect to
            ``dashboard``. Otherwise, render
            ``registrasion/product_category.html`` with data::

                {
                    "category": category,         # An inventory.Category for
                                                  # category_id
                    "discounts": discounts,       # A list of
                                                  # DiscountAndQuantity
                    "form": products_form,        # A form for selecting
                                                  # products
                    "voucher_form": voucher_form, # A form for entering a
                                                  # voucher code
                }

    '''

    PRODUCTS_FORM_PREFIX = "products"
    VOUCHERS_FORM_PREFIX = "vouchers"

    # Handle the voucher form *before* listing products.
    # Products can change as vouchers are entered.
    v = _handle_voucher(request, VOUCHERS_FORM_PREFIX)
    voucher_form, voucher_handled = v

    category_id = int(category_id)  # Routing is [0-9]+
    category = inventory.Category.objects.get(pk=category_id)

    with BatchController.batch(request.user):
        products = ProductController.available_products(
            request.user,
            category=category,
        )

        if not products:
            messages.warning(
                request,
                (
                    "There are no products available from category: " +
                    category.name
                ),
            )
            return redirect("dashboard")

        p = _handle_products(request, category, products, PRODUCTS_FORM_PREFIX)
        products_form, discounts, products_handled = p

    if request.POST and not voucher_handled and not products_form.errors:
        # Only return to the dashboard if we didn't add a voucher code
        # and if there's no errors in the products form
        if products_form.has_changed():
            messages.success(
                request,
                "Your reservations have been updated.",
            )
        return redirect(review)

    data = {
        "category": category,
        "discounts": discounts,
        "form": products_form,
        "voucher_form": voucher_form,
    }

    return render(request, "registrasion/product_category.html", data)


def voucher_code(request):
    ''' A view *just* for entering a voucher form. '''

    VOUCHERS_FORM_PREFIX = "vouchers"

    # Handle the voucher form *before* listing products.
    # Products can change as vouchers are entered.
    v = _handle_voucher(request, VOUCHERS_FORM_PREFIX)
    voucher_form, voucher_handled = v

    if voucher_handled:
        messages.success(request, "Your voucher code was accepted.")
        return redirect("dashboard")

    data = {
        "voucher_form": voucher_form,
    }

    return render(request, "registrasion/voucher_code.html", data)



def _handle_products(request, category, products, prefix):
    ''' Handles a products list form in the given request. Returns the
    form instance, the discounts applicable to this form, and whether the
    contents were handled. '''

    current_cart = CartController.for_user(request.user)

    ProductsForm = forms.ProductsForm(category, products)

    # Create initial data for each of products in category
    items = commerce.ProductItem.objects.filter(
        product__in=products,
        cart=current_cart.cart,
    ).select_related("product")
    quantities = []
    seen = set()

    for item in items:
        quantities.append((item.product, item.quantity))
        seen.add(item.product)

    zeros = set(products) - seen
    for product in zeros:
        quantities.append((product, 0))

    products_form = ProductsForm(
        request.POST or None,
        product_quantities=quantities,
        prefix=prefix,
    )

    if request.method == "POST" and products_form.is_valid():
        if products_form.has_changed():
            _set_quantities_from_products_form(products_form, current_cart)

        # If category is required, the user must have at least one
        # in an active+valid cart
        if category.required:
            carts = commerce.Cart.objects.filter(user=request.user)
            items = commerce.ProductItem.objects.filter(
                product__category=category,
                cart=carts,
            )
            if len(items) == 0:
                products_form.add_error(
                    None,
                    "You must have at least one item from this category",
                )
    handled = False if products_form.errors else True

    # Making this a function to lazily evaluate when it's displayed
    # in templates.

    discounts = util.lazy(
        DiscountController.available_discounts,
        request.user,
        [],
        products,
    )

    return products_form, discounts, handled


def _set_quantities_from_products_form(products_form, current_cart):

    # Makes id_to_quantity, a dictionary from product ID to its quantity
    quantities = list(products_form.product_quantities())
    id_to_quantity = dict(quantities)

    # Get the actual product objects
    pks = [i[0] for i in quantities]
    products = inventory.Product.objects.filter(
        id__in=pks,
    ).select_related("category").order_by("id")

    quantities.sort(key=lambda i: i[0])

    # Match the product objects to their quantities
    product_quantities = [
        (product, id_to_quantity[product.id]) for product in products
    ]

    try:
        current_cart.set_quantities(product_quantities)
    except CartValidationError as ve:
        for ve_field in ve.error_list:
            product, message = ve_field.message
            products_form.add_product_error(product, message)


def _handle_voucher(request, prefix):
    ''' Handles a voucher form in the given request. Returns the voucher
    form instance, and whether the voucher code was handled. '''

    voucher_form = forms.VoucherForm(request.POST or None, prefix=prefix)
    current_cart = CartController.for_user(request.user)

    if (voucher_form.is_valid() and
            voucher_form.cleaned_data["voucher"].strip()):

        voucher = voucher_form.cleaned_data["voucher"]
        voucher = inventory.Voucher.normalise_code(voucher)

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
def checkout(request, user_id=None):
    ''' Runs the checkout process for the current cart.

    If the query string contains ``fix_errors=true``, Registrasion will attempt
    to fix errors preventing the system from checking out, including by
    cancelling expired discounts and vouchers, and removing any unavailable
    products.

    Arguments:
        user_id (castable to int):
            If the requesting user is staff, then the user ID can be used to
            run checkout for another user.
    Returns:
        render or redirect:
            If the invoice is generated successfully, or there's already a
            valid invoice for the current cart, redirect to ``invoice``.
            If there are errors when generating the invoice, render
            ``registrasion/checkout_errors.html`` with the following data::

                {
                    "error_list", [str, ...]  # The errors to display.
                }

    '''

    if user_id is not None:
        if request.user.is_staff:
            user = User.objects.get(id=int(user_id))
        else:
            raise Http404()
    else:
        user = request.user

    current_cart = CartController.for_user(user)

    if "fix_errors" in request.GET and request.GET["fix_errors"] == "true":
        current_cart.fix_simple_errors()

    try:
        current_invoice = InvoiceController.for_cart(current_cart.cart)
    except ValidationError as ve:
        return _checkout_errors(request, ve)

    return redirect("invoice", current_invoice.invoice.id)


def _checkout_errors(request, errors):

    error_list = []
    for error in errors.error_list:
        if isinstance(error, tuple):
            error = error[1]
        error_list.append(error)

    data = {
        "error_list": error_list,
    }

    return render(request, "registrasion/checkout_errors.html", data)


def invoice_access(request, access_code):
    ''' Redirects to an invoice for the attendee that matches the given access
    code, if any.

    If the attendee has multiple invoices, we use the following tie-break:

    - If there's an unpaid invoice, show that, otherwise
    - If there's a paid invoice, show the most recent one, otherwise
    - Show the most recent invoid of all

    Arguments:

        access_code (castable to int): The access code for the user whose
            invoice you want to see.

    Returns:
        redirect:
            Redirect to the selected invoice for that user.

    Raises:
        Http404: If the user has no invoices.
    '''

    invoices = commerce.Invoice.objects.filter(
        user__attendee__access_code=access_code,
    ).order_by("-issue_time")

    if not invoices:
        raise Http404()

    unpaid = invoices.filter(status=commerce.Invoice.STATUS_UNPAID)
    paid = invoices.filter(status=commerce.Invoice.STATUS_PAID)

    if unpaid:
        invoice = unpaid[0]  # (should only be 1 unpaid invoice?)
    elif paid:
        invoice = paid[0]  # Most recent paid invoice
    else:
        invoice = invoices[0]  # Most recent of any invoices

    return redirect("invoice", invoice.id, access_code)


def invoice(request, invoice_id, access_code=None):
    ''' Displays an invoice.

    This view is not authenticated, but it will only allow access to either:
    the user the invoice belongs to; staff; or a request made with the correct
    access code.

    Arguments:

        invoice_id (castable to int): The invoice_id for the invoice you want
            to view.

        access_code (Optional[str]): The access code for the user who owns
            this invoice.

    Returns:
        render:
            Renders ``registrasion/invoice.html``, with the following
            data::

                {
                    "invoice": models.commerce.Invoice(),
                }

    Raises:
        Http404: if the current user cannot view this invoice and the correct
            access_code is not provided.

    '''

    current_invoice = InvoiceController.for_id_or_404(invoice_id)

    if not current_invoice.can_view(
            user=request.user,
            access_code=access_code,
            ):
        raise Http404()

    data = {
        "invoice": current_invoice.invoice,
    }

    return render(request, "registrasion/invoice.html", data)


def _staff_only(user):
    ''' Returns true if the user is staff. '''
    return user.is_staff


@user_passes_test(_staff_only)
def manual_payment(request, invoice_id):
    ''' Allows staff to make manual payments or refunds on an invoice.

    This form requires a login, and the logged in user needs to be staff.

    Arguments:
        invoice_id (castable to int): The invoice ID to be paid

    Returns:
        render:
            Renders ``registrasion/manual_payment.html`` with the following
            data::

                {
                    "invoice": models.commerce.Invoice(),
                    "form": form,   # A form that saves a ``ManualPayment``
                                    # object.
                }

    '''

    FORM_PREFIX = "manual_payment"

    current_invoice = InvoiceController.for_id_or_404(invoice_id)

    form = forms.ManualPaymentForm(
        request.POST or None,
        prefix=FORM_PREFIX,
    )

    if request.POST and form.is_valid():
        form.instance.invoice = current_invoice.invoice
        form.instance.entered_by = request.user
        form.save()
        current_invoice.update_status()
        form = forms.ManualPaymentForm(prefix=FORM_PREFIX)

    data = {
        "invoice": current_invoice.invoice,
        "form": form,
    }

    return render(request, "registrasion/manual_payment.html", data)


@user_passes_test(_staff_only)
def refund(request, invoice_id):
    ''' Marks an invoice as refunded and requests a credit note for the
    full amount paid against the invoice.

    This view requires a login, and the logged in user must be staff.

    Arguments:
        invoice_id (castable to int): The ID of the invoice to refund.

    Returns:
        redirect:
            Redirects to ``invoice``.

    '''

    current_invoice = InvoiceController.for_id_or_404(invoice_id)

    try:
        current_invoice.refund()
        messages.success(request, "This invoice has been refunded.")
    except ValidationError as ve:
        messages.error(request, ve)

    return redirect("invoice", invoice_id)


@user_passes_test(_staff_only)
def credit_note(request, note_id, access_code=None):
    ''' Displays a credit note.

    If ``request`` is a ``POST`` request, forms for applying or refunding
    a credit note will be processed.

    This view requires a login, and the logged in user must be staff.

    Arguments:
        note_id (castable to int): The ID of the credit note to view.

    Returns:
        render or redirect:
            If the "apply to invoice" form is correctly processed, redirect to
            that invoice, otherwise, render ``registration/credit_note.html``
            with the following data::

                {
                    "credit_note": models.commerce.CreditNote(),
                    "apply_form": form,  # A form for applying credit note
                                         # to an invoice.
                    "refund_form": form, # A form for applying a *manual*
                                         # refund of the credit note.
                    "cancellation_fee_form" : form, # A form for generating an
                                                    # invoice with a
                                                    # cancellation fee
                }

    '''

    note_id = int(note_id)
    current_note = CreditNoteController.for_id_or_404(note_id)

    apply_form = forms.ApplyCreditNoteForm(
        current_note.credit_note.invoice.user,
        request.POST or None,
        prefix="apply_note"
    )

    refund_form = forms.ManualCreditNoteRefundForm(
        request.POST or None,
        prefix="refund_note"
    )

    cancellation_fee_form = forms.CancellationFeeForm(
        request.POST or None,
        prefix="cancellation_fee"
    )

    if request.POST and apply_form.is_valid():
        inv_id = apply_form.cleaned_data["invoice"]
        invoice = commerce.Invoice.objects.get(pk=inv_id)
        current_note.apply_to_invoice(invoice)
        messages.success(
            request,
            "Applied credit note %d to invoice." % note_id,
        )
        return redirect("invoice", invoice.id)

    elif request.POST and refund_form.is_valid():
        refund_form.instance.entered_by = request.user
        refund_form.instance.parent = current_note.credit_note
        refund_form.save()
        messages.success(
            request,
            "Applied manual refund to credit note."
        )
        refund_form = forms.ManualCreditNoteRefundForm(
            prefix="refund_note",
        )

    elif request.POST and cancellation_fee_form.is_valid():
        percentage = cancellation_fee_form.cleaned_data["percentage"]
        invoice = current_note.cancellation_fee(percentage)
        messages.success(
            request,
            "Generated cancellation fee for credit note %d." % note_id,
        )
        return redirect("invoice", invoice.invoice.id)

    data = {
        "credit_note": current_note.credit_note,
        "apply_form": apply_form,
        "refund_form": refund_form,
        "cancellation_fee_form": cancellation_fee_form,
    }

    return render(request, "registrasion/credit_note.html", data)


@user_passes_test(_staff_only)
def amend_registration(request, user_id):
    ''' Allows staff to amend a user's current registration cart, and etc etc.
    '''

    user = User.objects.get(id=int(user_id))
    current_cart = CartController.for_user(user)

    items = commerce.ProductItem.objects.filter(
        cart=current_cart.cart,
    ).select_related("product")
    initial = [{"product": i.product, "quantity": i.quantity} for i in items]

    StaffProductsFormSet = forms.staff_products_formset_factory(user)
    formset = StaffProductsFormSet(
        request.POST or None,
        initial=initial,
        prefix="products",
    )

    for item, form in zip(items, formset):
        queryset = inventory.Product.objects.filter(id=item.product.id)
        form.fields["product"].queryset = queryset

    voucher_form = forms.VoucherForm(
        request.POST or None,
        prefix="voucher",
    )

    if request.POST and formset.is_valid():

        pq = [
            (f.cleaned_data["product"], f.cleaned_data["quantity"])
            for f in formset
            if "product" in f.cleaned_data and
            f.cleaned_data["product"] is not None
        ]

        try:
            current_cart.set_quantities(pq)
            return redirect(amend_registration, user_id)
        except ValidationError as ve:
            for ve_field in ve.error_list:
                product, message = ve_field.message
                for form in formset:
                    if "product" not in form.cleaned_data:
                        # This is the empty form.
                        continue
                    if form.cleaned_data["product"] == product:
                        form.add_error("quantity", message)

    if request.POST and voucher_form.has_changed() and voucher_form.is_valid():
        try:
            current_cart.apply_voucher(voucher_form.cleaned_data["voucher"])
            return redirect(amend_registration, user_id)
        except ValidationError as ve:
            voucher_form.add_error(None, ve)

    ic = ItemController(user)
    data = {
        "user": user,
        "paid": ic.items_purchased(),
        "cancelled": ic.items_released(),
        "form": formset,
        "voucher_form": voucher_form,
    }

    return render(request, "registrasion/amend_registration.html", data)


@user_passes_test(_staff_only)
def extend_reservation(request, user_id, days=7):
    ''' Allows staff to extend the reservation on a given user's cart.
    '''

    user = User.objects.get(id=int(user_id))
    cart = CartController.for_user(user)
    cart.extend_reservation(datetime.timedelta(days=days))

    return redirect(request.META["HTTP_REFERER"])


Email = namedtuple(
    "Email",
    ("subject", "body", "from_email", "recipient_list"),
)


@user_passes_test(_staff_only)
def invoice_mailout(request):
    ''' Allows staff to send emails to users based on their invoice status. '''

    category = request.GET.getlist("category", [])
    product = request.GET.getlist("product", [])
    status = request.GET.get("status")

    form = forms.InvoiceEmailForm(
        request.POST or None,
        category=category,
        product=product,
        status=status,
    )

    emails = []

    if form.is_valid():
        emails = []
        for invoice in form.cleaned_data["invoice"]:
            # datatuple = (subject, message, from_email, recipient_list)
            from_email = form.cleaned_data["from_email"]
            subject = form.cleaned_data["subject"]
            body = Template(form.cleaned_data["body"]).render(
                Context({
                    "invoice": invoice,
                    "user": invoice.user,
                })
            )
            recipient_list = [invoice.user.email]
            emails.append(Email(subject, body, from_email, recipient_list))

        if form.cleaned_data["action"] == forms.InvoiceEmailForm.ACTION_SEND:
            # Send e-mails *ONLY* if we're sending.
            send_mass_mail(emails)
            messages.info(request, "The e-mails have been sent.")

    data = {
        "form": form,
        "emails": emails,
    }

    return render(request, "registrasion/invoice_mailout.html", data)


@user_passes_test(_staff_only)
def badge(request, user_id):
    ''' Renders a single user's badge (SVG). '''

    user_id = int(user_id)
    user = User.objects.get(pk=user_id)

    rendered = render_badge(user)
    response = HttpResponse(rendered)

    response["Content-Type"] = "image/svg+xml"
    response["Content-Disposition"] = 'inline; filename="badge.svg"'
    return response


def badges(request):
    ''' Either displays a form containing a list of users with badges to
    render, or returns a .zip file containing their badges. '''

    category = request.GET.getlist("category", [])
    product = request.GET.getlist("product", [])
    status = request.GET.get("status")

    form = forms.InvoicesWithProductAndStatusForm(
        request.POST or None,
        category=category,
        product=product,
        status=status,
    )

    if form.is_valid():
        response = HttpResponse()
        response["Content-Type"] = "application.zip"
        response["Content-Disposition"] = 'attachment; filename="badges.zip"'

        z = zipfile.ZipFile(response, "w")

        for invoice in form.cleaned_data["invoice"]:
            user = invoice.user
            badge = render_badge(user)
            z.writestr("badge_%d.svg" % user.id, badge.encode("utf-8"))

        return response

    data = {
        "form": form,
    }

    return render(request, "registrasion/badges.html", data)


def render_badge(user):
    ''' Renders a single user's badge. '''

    data = {
        "user": user,
    }

    t = loader.get_template('registrasion/badge.svg')
    return t.render(data)
