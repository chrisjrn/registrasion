import forms

import collections
import datetime

from django.contrib.auth.decorators import user_passes_test
from django.core.urlresolvers import reverse
from django.db import models
from django.db.models import F, Q
from django.db.models import Count, Max, Sum
from django.db.models import Case, When, Value
from django.shortcuts import render

from registrasion.controllers.item import ItemController
from registrasion.models import commerce
from registrasion.models import people
from registrasion import views

from reports import get_all_reports
from reports import Links
from reports import ListReport
from reports import QuerysetReport
from reports import report_view


def CURRENCY():
    return models.DecimalField(decimal_places=2)


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

    print line_items

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
            refunded_credit_notes - unclaimed_credit_notes,
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
        ["discount",],
        ["discount", "discount__description",],
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


@report_view("Paid invoices by date", form_type=forms.ProductAndCategoryForm)
def paid_invoices_by_date(request, form):
    ''' Shows the number of paid invoices containing given products or
    categories per day. '''

    products = form.cleaned_data["product"]
    categories = form.cleaned_data["category"]

    invoices = commerce.Invoice.objects.filter(
        Q(lineitem__product__in=products) | Q(lineitem__product__category__in=categories),
        status=commerce.Invoice.STATUS_PAID,
    )

    payments = commerce.PaymentBase.objects.all()
    payments = payments.filter(
        invoice__in=invoices,
    )
    payments = payments.order_by("invoice")
    invoice_max_time = payments.values("invoice").annotate(max_time=Max("time"))

    by_date = collections.defaultdict(int)

    for line in invoice_max_time:
        time = line["max_time"]
        date = datetime.datetime(
            year=time.year, month=time.month, day=time.day
        )
        by_date[date] += 1

    data = [(date, count) for date, count in sorted(by_date.items())]
    data = [(date.strftime("%Y-%m-%d"), count) for date, count in data]

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
        ["id", "invoice__user__attendee__attendeeprofilebase__invoice_recipient", "status", "value"],  # NOQA
        notes,
        headings=["id", "Owner", "Status", "Value"],
        link_view=views.credit_note,
    )


@report_view("Attendee", form_type=forms.UserIdForm)
def attendee(request, form, user_id=None):
    ''' Returns a list of all manifested attendees if no attendee is specified,
    else displays the attendee manifest. '''

    if user_id is None and not form.has_changed():
        return attendee_list(request)

    if form.cleaned_data["user"] is not None:
        user_id = form.cleaned_data["user"]

    attendee = people.Attendee.objects.get(user__id=user_id)
    name = attendee.attendeeprofilebase.attendee_name()

    reports = []

    links = []
    links.append((
        reverse(views.amend_registration, args=[user_id]),
        "Amend current cart",
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
    )
    reports.append(QuerysetReport(
        "Credit Notes",
        ["id", "status", "value"],
        credit_notes,
        link_view=views.credit_note,
    ))

    # All payments
    payments = commerce.PaymentBase.objects.filter(
        invoice__user=attendee.user,
    )
    reports.append(QuerysetReport(
        "Payments",
        ["invoice__id", "id", "reference", "amount"],
        payments,
        link_view=views.invoice,
    ))

    return reports


def attendee_list(request):
    ''' Returns a list of all attendees. '''

    attendees = people.Attendee.objects.all().select_related(
        "attendeeprofilebase",
        "user",
    )

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
            a.attendeeprofilebase.attendee_name(),
            a.user.email,
            a.has_registered > 0,
        ])

    # Sort by whether they've registered, then ID.
    data.sort(key=lambda a: (-a[3], a[0]))

    class Report(ListReport):

        def get_link(self, argument):
            return reverse(self._link_view) + "?user=%d" % int(argument)

    return Report("Attendees", headings, data, link_view=attendee)
