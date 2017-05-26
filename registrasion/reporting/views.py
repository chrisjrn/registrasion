from . import forms

import collections
import datetime
import itertools

from django.conf import settings
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.db import models
from django.db.models import F, Q
from django.db.models import Count, Max, Sum
from django.db.models import Case, When, Value
from django.db.models.fields.related import RelatedField
from django.shortcuts import render

from registrasion.controllers.cart import CartController
from registrasion.controllers.item import ItemController
from registrasion.models import commerce
from registrasion.models import people
from registrasion import util
from registrasion import views

from symposion.schedule import models as schedule_models

from .reports import get_all_reports
from .reports import Links
from .reports import ListReport
from .reports import QuerysetReport
from .reports import report_view


def CURRENCY():
    return models.DecimalField(decimal_places=2)


AttendeeProfile = util.get_object_from_name(settings.ATTENDEE_PROFILE_MODEL)


@user_passes_test(views._staff_only)
def reports_list(request):
    ''' Lists all of the reports currently available. '''

    reports = []

    for report in get_all_reports():
        reports.append({
            "name": report.__name__,
            "url": reverse(report),
            "description": report.__doc__,
        })

    reports.sort(key=lambda report: report["name"])

    ctx = {
        "reports": reports,
    }

    return render(request, "registrasion/reports_list.html", ctx)


# Report functions

@report_view("Reconcilitation")
def reconciliation(request, form):
    ''' Shows the summary of sales, and the full history of payments and
    refunds into the system. '''

    return [
        sales_payment_summary(),
        items_sold(),
        payments(),
        credit_note_refunds(),
    ]


def items_sold():
    ''' Summarises the items sold and discounts granted for a given set of
    products, or products from categories. '''

    data = None
    headings = None

    line_items = commerce.LineItem.objects.filter(
        invoice__status=commerce.Invoice.STATUS_PAID,
    ).select_related("invoice")

    line_items = line_items.order_by(
        # sqlite requires an order_by for .values() to work
        "-price", "description",
    ).values(
        "price", "description",
    ).annotate(
        total_quantity=Sum("quantity"),
    )

    headings = ["Description", "Quantity", "Price", "Total"]

    data = []
    total_income = 0
    for line in line_items:
        cost = line["total_quantity"] * line["price"]
        data.append([
            line["description"], line["total_quantity"],
            line["price"], cost,
        ])
        total_income += cost

    data.append([
        "(TOTAL)", "--", "--", total_income,
    ])

    return ListReport("Items sold", headings, data)


def sales_payment_summary():
    ''' Summarises paid items and payments. '''

    def value_or_zero(aggregate, key):
        return aggregate[key] or 0

    def sum_amount(payment_set):
        a = payment_set.values("amount").aggregate(total=Sum("amount"))
        return value_or_zero(a, "total")

    headings = ["Category", "Total"]
    data = []

    # Summarise all sales made (= income.)
    sales = commerce.LineItem.objects.filter(
        invoice__status=commerce.Invoice.STATUS_PAID,
    ).values(
        "price", "quantity"
    ).aggregate(
        total=Sum(F("price") * F("quantity"), output_field=CURRENCY()),
    )
    sales = value_or_zero(sales, "total")

    all_payments = sum_amount(commerce.PaymentBase.objects.all())

    # Manual payments
    # Credit notes generated (total)
    # Payments made by credit note
    # Claimed credit notes

    all_credit_notes = 0 - sum_amount(commerce.CreditNote.objects.all())
    unclaimed_credit_notes = 0 - sum_amount(commerce.CreditNote.unclaimed())
    claimed_credit_notes = sum_amount(
        commerce.CreditNoteApplication.objects.all()
    )
    refunded_credit_notes = 0 - sum_amount(commerce.CreditNote.refunded())

    data.append(["Items on paid invoices", sales])
    data.append(["All payments", all_payments])
    data.append(["Sales - Payments ", sales - all_payments])
    data.append(["All credit notes", all_credit_notes])
    data.append(["Credit notes paid on invoices", claimed_credit_notes])
    data.append(["Credit notes refunded", refunded_credit_notes])
    data.append(["Unclaimed credit notes", unclaimed_credit_notes])
    data.append([
        "Credit notes - (claimed credit notes + unclaimed credit notes)",
        all_credit_notes - claimed_credit_notes -
        refunded_credit_notes - unclaimed_credit_notes
        ])

    return ListReport("Sales and Payments Summary", headings, data)


def payments():
    ''' Shows the history of payments into the system '''

    payments = commerce.PaymentBase.objects.all()
    return QuerysetReport(
        "Payments",
        ["invoice__id", "id", "reference", "amount"],
        payments,
        link_view=views.invoice,
    )


def credit_note_refunds():
    ''' Shows all of the credit notes that have been generated. '''
    notes_refunded = commerce.CreditNote.refunded()
    return QuerysetReport(
        "Credit note refunds",
        ["id", "creditnoterefund__reference", "amount"],
        notes_refunded,
        link_view=views.credit_note,
    )


def group_by_cart_status(queryset, order, values):
    queryset = queryset.annotate(
        is_reserved=Case(
            When(cart__in=commerce.Cart.reserved_carts(), then=Value(True)),
            default=Value(False),
            output_field=models.BooleanField(),
        ),
    )

    values = queryset.order_by(*order).values(*values)
    values = values.annotate(
        total_paid=Sum(Case(
            When(
                cart__status=commerce.Cart.STATUS_PAID,
                then=F("quantity"),
            ),
            default=Value(0),
        )),
        total_refunded=Sum(Case(
            When(
                cart__status=commerce.Cart.STATUS_RELEASED,
                then=F("quantity"),
            ),
            default=Value(0),
        )),
        total_unreserved=Sum(Case(
            When(
                (
                    Q(cart__status=commerce.Cart.STATUS_ACTIVE) &
                    Q(is_reserved=False)
                ),
                then=F("quantity"),
            ),
            default=Value(0),
        )),
        total_reserved=Sum(Case(
            When(
                (
                    Q(cart__status=commerce.Cart.STATUS_ACTIVE) &
                    Q(is_reserved=True)
                ),
                then=F("quantity"),
            ),
            default=Value(0),
        )),
    )

    return values


@report_view("Product status", form_type=forms.ProductAndCategoryForm)
def product_status(request, form):
    ''' Summarises the inventory status of the given items, grouping by
    invoice status. '''

    products = form.cleaned_data["product"]
    categories = form.cleaned_data["category"]

    items = commerce.ProductItem.objects.filter(
        Q(product__in=products) | Q(product__category__in=categories),
    ).select_related("cart", "product")

    items = group_by_cart_status(
        items,
        ["product__category__order", "product__order"],
        ["product", "product__category__name", "product__name"],
    )

    headings = [
        "Product", "Paid", "Reserved", "Unreserved", "Refunded",
    ]
    data = []

    for item in items:
        data.append([
            "%s - %s" % (
                item["product__category__name"], item["product__name"]
            ),
            item["total_paid"],
            item["total_reserved"],
            item["total_unreserved"],
            item["total_refunded"],
        ])

    return ListReport("Inventory", headings, data)


@report_view("Product status", form_type=forms.DiscountForm)
def discount_status(request, form):
    ''' Summarises the usage of a given discount. '''

    discounts = form.cleaned_data["discount"]

    items = commerce.DiscountItem.objects.filter(
        Q(discount__in=discounts),
    ).select_related("cart", "product", "product__category")

    items = group_by_cart_status(
        items,
        ["discount"],
        ["discount", "discount__description"],
    )

    headings = [
        "Discount", "Paid", "Reserved", "Unreserved", "Refunded",
    ]
    data = []

    for item in items:
        data.append([
            item["discount__description"],
            item["total_paid"],
            item["total_reserved"],
            item["total_unreserved"],
            item["total_refunded"],
        ])

    return ListReport("Usage by item", headings, data)


@report_view("Product Line Items By Date & Customer", form_type=forms.ProductAndCategoryForm)
def product_line_items(request, form):
    ''' Shows each product line item from invoices, including their date and
    purchashing customer. '''

    products = form.cleaned_data["product"]
    categories = form.cleaned_data["category"]

    invoices = commerce.Invoice.objects.filter(
        (
            Q(lineitem__product__in=products) |
            Q(lineitem__product__category__in=categories)
        ),
        status=commerce.Invoice.STATUS_PAID,
    ).select_related(
        "cart",
        "user",
        "user__attendee",
        "user__attendee__attendeeprofilebase"
    ).order_by("issue_time")

    headings = [
        'Invoice', 'Invoice Date', 'Attendee', 'Qty', 'Product', 'Status'
    ]

    data = []
    for invoice in invoices:
        for item in invoice.cart.productitem_set.all():
            if item.product in products or item.product.category in categories:
                output = []
                output.append(invoice.id)
                output.append(invoice.issue_time.strftime('%Y-%m-%d %H:%M:%S'))
                output.append(
                    invoice.user.attendee.attendeeprofilebase.attendee_name()
                )
                output.append(item.quantity)
                output.append(item.product)
                cart = invoice.cart
                if cart.status == commerce.Cart.STATUS_PAID:
                    output.append('PAID')
                elif cart.status == commerce.Cart.STATUS_ACTIVE:
                    output.append('UNPAID')
                elif cart.status == commerce.Cart.STATUS_RELEASED:
                    output.append('REFUNDED')
                data.append(output)

    return ListReport("Line Items", headings, data)


@report_view("Paid invoices by date", form_type=forms.ProductAndCategoryForm)
def paid_invoices_by_date(request, form):
    ''' Shows the number of paid invoices containing given products or
    categories per day. '''

    products = form.cleaned_data["product"]
    categories = form.cleaned_data["category"]

    invoices = commerce.Invoice.objects.filter(
        (
            Q(lineitem__product__in=products) |
            Q(lineitem__product__category__in=categories)
        ),
        status=commerce.Invoice.STATUS_PAID,
    )

    # Invoices with payments will be paid at the time of their latest payment
    payments = commerce.PaymentBase.objects.all()
    payments = payments.filter(
        invoice__in=invoices,
    )
    payments = payments.order_by("invoice")
    invoice_max_time = payments.values("invoice").annotate(
        max_time=Max("time")
    )

    # Zero-value invoices will have no payments, so they're paid at issue time
    zero_value_invoices = invoices.filter(value=0)

    times = itertools.chain(
        (line["max_time"] for line in invoice_max_time),
        (invoice.issue_time for invoice in zero_value_invoices),
    )

    by_date = collections.defaultdict(int)
    for time in times:
        date = datetime.datetime(
            year=time.year, month=time.month, day=time.day
        )
        by_date[date] += 1

    data = [(date_, count) for date_, count in sorted(by_date.items())]
    data = [(date_.strftime("%Y-%m-%d"), count) for date_, count in data]

    return ListReport(
        "Paid Invoices By Date",
        ["date", "count"],
        data,
    )


@report_view("Credit notes")
def credit_notes(request, form):
    ''' Shows all of the credit notes in the system. '''

    notes = commerce.CreditNote.objects.all().select_related(
        "creditnoterefund",
        "creditnoteapplication",
        "invoice",
        "invoice__user__attendee__attendeeprofilebase",
    )

    return QuerysetReport(
        "Credit Notes",
        ["id",
         "invoice__user__attendee__attendeeprofilebase__invoice_recipient",
         "status", "value"],
        notes,
        headings=["id", "Owner", "Status", "Value"],
        link_view=views.credit_note,
    )


@report_view("Invoices")
def invoices(request, form):
    ''' Shows all of the invoices in the system. '''

    invoices = commerce.Invoice.objects.all().order_by("status", "id")

    return QuerysetReport(
        "Invoices",
        ["id", "recipient", "value", "get_status_display"],
        invoices,
        headings=["id", "Recipient", "Value", "Status"],
        link_view=views.invoice,
    )


class AttendeeListReport(ListReport):

    def get_link(self, argument):
        return reverse(self._link_view) + "?user=%d" % int(argument)


@report_view("Attendee", form_type=forms.UserIdForm)
def attendee(request, form, user_id=None):
    ''' Returns a list of all manifested attendees if no attendee is specified,
    else displays the attendee manifest. '''

    if user_id is None and form.cleaned_data["user"] is not None:
        user_id = form.cleaned_data["user"]

    if user_id is None:
        return attendee_list(request)

    attendee = people.Attendee.objects.get(user__id=user_id)
    name = attendee.attendeeprofilebase.attendee_name()

    reports = []

    profile_data = []
    try:
        profile = people.AttendeeProfileBase.objects.get_subclass(
            attendee=attendee
        )
        fields = profile._meta.get_fields()
    except people.AttendeeProfileBase.DoesNotExist:
        fields = []

    exclude = set(["attendeeprofilebase_ptr", "id"])
    for field in fields:
        if field.name in exclude:
            # Not actually important
            continue
        if not hasattr(field, "verbose_name"):
            continue  # Not a publicly visible field
        value = getattr(profile, field.name)

        if isinstance(field, models.ManyToManyField):
            value = ", ".join(str(i) for i in value.all())

        profile_data.append((field.verbose_name, value))

    cart = CartController.for_user(attendee.user)
    reservation = cart.cart.reservation_duration + cart.cart.time_last_updated
    profile_data.append(("Current cart reserved until", reservation))

    reports.append(ListReport("Profile", ["", ""], profile_data))

    links = []
    links.append((
        reverse(views.badge, args=[user_id]),
        "View badge",
    ))
    links.append((
        reverse(views.amend_registration, args=[user_id]),
        "Amend current cart",
    ))
    links.append((
        reverse(views.extend_reservation, args=[user_id]),
        "Extend reservation",
    ))

    reports.append(Links("Actions for " + name, links))

    # Paid and pending  products
    ic = ItemController(attendee.user)
    reports.append(ListReport(
        "Paid Products",
        ["Product", "Quantity"],
        [(pq.product, pq.quantity) for pq in ic.items_purchased()],
    ))
    reports.append(ListReport(
        "Unpaid Products",
        ["Product", "Quantity"],
        [(pq.product, pq.quantity) for pq in ic.items_pending()],
    ))

    # Invoices
    invoices = commerce.Invoice.objects.filter(
        user=attendee.user,
    )
    reports.append(QuerysetReport(
        "Invoices",
        ["id", "get_status_display", "value"],
        invoices,
        headings=["Invoice ID", "Status", "Value"],
        link_view=views.invoice,
    ))

    # Credit Notes
    credit_notes = commerce.CreditNote.objects.filter(
        invoice__user=attendee.user,
    ).select_related("invoice", "creditnoteapplication", "creditnoterefund")

    reports.append(QuerysetReport(
        "Credit Notes",
        ["id", "status", "value"],
        credit_notes,
        link_view=views.credit_note,
    ))

    # All payments
    payments = commerce.PaymentBase.objects.filter(
        invoice__user=attendee.user,
    ).select_related("invoice")

    reports.append(QuerysetReport(
        "Payments",
        ["invoice__id", "id", "reference", "amount"],
        payments,
        link_view=views.invoice,
    ))

    return reports


def attendee_list(request):
    ''' Returns a list of all attendees. '''

    attendees = people.Attendee.objects.select_related(
        "attendeeprofilebase",
        "user",
    )

    profiles = AttendeeProfile.objects.filter(
        attendee__in=attendees
    ).select_related(
        "attendee", "attendee__user",
    )
    profiles_by_attendee = dict((i.attendee, i) for i in profiles)

    attendees = attendees.annotate(
        has_registered=Count(
            Q(user__invoice__status=commerce.Invoice.STATUS_PAID)
        ),
    )

    headings = [
        "User ID", "Name", "Email", "Has registered",
    ]

    data = []

    for a in attendees:
        data.append([
            a.user.id,
            (profiles_by_attendee[a].attendee_name()
                if a in profiles_by_attendee else ""),
            a.user.email,
            a.has_registered > 0,
        ])

    # Sort by whether they've registered, then ID.
    data.sort(key=lambda a: (-a[3], a[0]))

    return AttendeeListReport("Attendees", headings, data, link_view=attendee)


ProfileForm = forms.model_fields_form_factory(AttendeeProfile)


@report_view(
    "Attendees By Product/Category",
    form_type=forms.mix_form(
        forms.ProductAndCategoryForm, ProfileForm, forms.GroupByForm
    ),
)
def attendee_data(request, form, user_id=None):
    ''' Lists attendees for a given product/category selection along with
    profile data.'''

    status_display = {
        commerce.Cart.STATUS_ACTIVE: "Unpaid",
        commerce.Cart.STATUS_PAID: "Paid",
        commerce.Cart.STATUS_RELEASED: "Refunded",
    }

    output = []

    by_category = (
        form.cleaned_data["group_by"] == forms.GroupByForm.GROUP_BY_CATEGORY)

    products = form.cleaned_data["product"]
    categories = form.cleaned_data["category"]
    fields = form.cleaned_data["fields"]
    name_field = AttendeeProfile.name_field()

    items = commerce.ProductItem.objects.filter(
        Q(product__in=products) | Q(product__category__in=categories),
    ).exclude(
        cart__status=commerce.Cart.STATUS_RELEASED
    ).select_related(
        "cart", "cart__user", "product", "product__category",
    ).order_by("cart__status")

    # Add invoice nag link
    links = []
    invoice_mailout = reverse(views.invoice_mailout, args=[])
    invoice_mailout += "?" + request.META["QUERY_STRING"]
    links += [
        (invoice_mailout + "&status=1", "Send invoice reminders",),
        (invoice_mailout + "&status=2", "Send mail for paid invoices",),
    ]

    if items.count() > 0:
        output.append(Links("Actions", links))

    # Make sure we select all of the related fields
    related_fields = set(
        field for field in fields
        if isinstance(AttendeeProfile._meta.get_field(field), RelatedField)
    )

    # Get all of the relevant attendee profiles in one hit.
    profiles = AttendeeProfile.objects.filter(
        attendee__user__cart__productitem__in=items
    ).select_related("attendee__user").prefetch_related(*related_fields)
    by_user = {}
    for profile in profiles:
        by_user[profile.attendee.user] = profile

    cart = "attendee__user__cart"
    cart_status = cart + "__status"  # noqa
    product = cart + "__productitem__product"
    product_name = product + "__name"
    category = product + "__category"
    category_name = category + "__name"

    if by_category:
        grouping_fields = (category, category_name)
        order_by = (category, )
        first_column = "Category"
        group_name = lambda i: "%s" % (i[category_name], )  # noqa
    else:
        grouping_fields = (product, product_name, category_name)
        order_by = (category, )
        first_column = "Product"
        group_name = lambda i: "%s - %s" % (i[category_name], i[product_name])  # noqa

    # Group the responses per-field.
    for field in fields:
        concrete_field = AttendeeProfile._meta.get_field(field)
        field_verbose = concrete_field.verbose_name

        # Render the correct values for related fields
        if field in related_fields:
            # Get all of the IDs that will appear
            all_ids = profiles.order_by(field).values(field)
            all_ids = [i[field] for i in all_ids if i[field] is not None]
            # Get all of the concrete objects for those IDs
            model = concrete_field.related_model
            all_objects = model.objects.filter(id__in=all_ids)
            all_objects_by_id = dict((i.id, i) for i in all_objects)

            # Define a function to render those IDs.
            def display_field(value):
                if value in all_objects_by_id:
                    return all_objects_by_id[value]
                else:
                    return None
        else:
            def display_field(value):
                return value

        status_count = lambda status: Case(When(  # noqa
                attendee__user__cart__status=status,
                then=Value(1),
            ),
            default=Value(0),
            output_field=models.fields.IntegerField(),
        )
        paid_count = status_count(commerce.Cart.STATUS_PAID)
        unpaid_count = status_count(commerce.Cart.STATUS_ACTIVE)

        groups = profiles.order_by(
            *(order_by + (field, ))
        ).values(
            *(grouping_fields + (field, ))
        ).annotate(
            paid_count=Sum(paid_count),
            unpaid_count=Sum(unpaid_count),
        )
        output.append(ListReport(
            "Grouped by %s" % field_verbose,
            [first_column, field_verbose, "paid", "unpaid"],
            [
                (
                    group_name(group),
                    display_field(group[field]),
                    group["paid_count"] or 0,
                    group["unpaid_count"] or 0,
                )
                for group in groups
            ],
        ))

    # DO the report for individual attendees

    field_names = [
        AttendeeProfile._meta.get_field(field).verbose_name for field in fields
    ]

    def display_field(profile, field):
        field_type = AttendeeProfile._meta.get_field(field)
        attr = getattr(profile, field)

        if isinstance(field_type, models.ManyToManyField):
            return [str(i) for i in attr.all()] or ""
        else:
            return attr

    headings = ["User ID", "Name", "Email", "Product", "Item Status"]
    headings.extend(field_names)
    data = []
    for item in items:
        profile = by_user[item.cart.user]
        line = [
            item.cart.user.id,
            getattr(profile, name_field),
            profile.attendee.user.email,
            item.product,
            status_display[item.cart.status],
        ] + [
            display_field(profile, field) for field in fields
        ]
        data.append(line)

    output.append(AttendeeListReport(
        "Attendees by item with profile data", headings, data,
        link_view=attendee
    ))
    return output


@report_view(
    "Speaker Registration Status",
    form_type=forms.ProposalKindForm,
)
def speaker_registrations(request, form):
    ''' Shows registration status for speakers with a given proposal kind. '''

    kinds = form.cleaned_data["kind"]

    presentations = schedule_models.Presentation.objects.filter(
        proposal_base__kind__in=kinds,
    ).exclude(
        cancelled=True,
    )

    users = User.objects.filter(
        Q(speaker_profile__presentations__in=presentations) |
        Q(speaker_profile__copresentations__in=presentations)
    )

    paid_carts = commerce.Cart.objects.filter(status=commerce.Cart.STATUS_PAID)

    paid_carts = Case(
        When(cart__in=paid_carts, then=Value(1)),
        default=Value(0),
        output_field=models.IntegerField(),
    )
    users = users.annotate(paid_carts=Sum(paid_carts))
    users = users.order_by("paid_carts")

    return QuerysetReport(
        "Speaker Registration Status",
        ["id", "speaker_profile__name", "email", "paid_carts"],
        users,
        link_view=attendee,
    )

    return []


@report_view(
    "Manifest",
    forms.ProductAndCategoryForm,
)
def manifest(request, form):
    '''
    Produces the registration manifest for people with the given product
    type.
    '''

    products = form.cleaned_data["product"]
    categories = form.cleaned_data["category"]

    line_items = (
        Q(lineitem__product__in=products) |
        Q(lineitem__product__category__in=categories)
    )

    invoices = commerce.Invoice.objects.filter(
        line_items,
        status=commerce.Invoice.STATUS_PAID,
    ).select_related(
        "cart",
        "user",
        "user__attendee",
        "user__attendee__attendeeprofilebase"
    )

    users = set(i.user for i in invoices)

    carts = commerce.Cart.objects.filter(
        user__in=users
    )

    items = commerce.ProductItem.objects.filter(
        cart__in=carts
    ).select_related(
        "product",
        "product__category",
        "cart",
        "cart__user",
        "cart__user__attendee",
        "cart__user__attendee__attendeeprofilebase"
    ).order_by("product__category__order", "product__order")

    users = {}

    for item in items:
        cart = item.cart
        if cart.user not in users:
            users[cart.user] = {"unpaid": [], "paid": [], "refunded": []}
        items = users[cart.user]
        if cart.status == commerce.Cart.STATUS_ACTIVE:
            items["unpaid"].append(item)
        elif cart.status == commerce.Cart.STATUS_PAID:
            items["paid"].append(item)
        elif cart.status == commerce.Cart.STATUS_RELEASED:
            items["refunded"].append(item)

    users_by_name = list(users.keys())
    users_by_name.sort(key=(
        lambda i: i.attendee.attendeeprofilebase.attendee_name().lower()
    ))

    headings = ["User ID", "Name", "Paid", "Unpaid", "Refunded"]

    def format_items(item_list):
        strings = [
            '%d x %s' % (item.quantity, str(item.product))
            for item in item_list
        ]
        return ", \n".join(strings)

    output = []
    for user in users_by_name:
        items = users[user]
        output.append([
            user.id,
            user.attendee.attendeeprofilebase.attendee_name(),
            format_items(items["paid"]),
            format_items(items["unpaid"]),
            format_items(items["refunded"]),
        ])

    return ListReport("Manifest", headings, output)

    # attendeeprofilebase.attendee_name()
