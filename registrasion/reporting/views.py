import forms

from django.contrib.auth.decorators import user_passes_test
from django.core.urlresolvers import reverse
from django.db import models
from django.db.models import F, Q
from django.db.models import Count, Sum
from django.db.models import Case, When, Value
from django.shortcuts import render

from registrasion.controllers.item import ItemController
from registrasion.models import commerce
from registrasion.models import people
from registrasion import views

from reports import get_all_reports
from reports import Report
from reports import report_view


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


@report_view("Paid items", form_type=forms.ProductAndCategoryForm)
def items_sold(request, form):
    ''' Summarises the items sold and discounts granted for a given set of
    products, or products from categories. '''

    data = None
    headings = None

    products = form.cleaned_data["product"]
    categories = form.cleaned_data["category"]

    line_items = commerce.LineItem.objects.filter(
        Q(product__in=products) | Q(product__category__in=categories),
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

    return Report("Paid items", headings, data)


@report_view("Reconcilitation")
def reconciliation(request, form):
    ''' Reconciles all sales in the system with the payments in the
    system. '''

    headings = ["Thing", "Total"]
    data = []

    sales = commerce.LineItem.objects.filter(
        invoice__status=commerce.Invoice.STATUS_PAID,
    ).values(
        "price", "quantity"
    ).aggregate(total=Sum(F("price") * F("quantity")))

    data.append(["Paid items", sales["total"]])

    payments = commerce.PaymentBase.objects.values(
        "amount",
    ).aggregate(total=Sum("amount"))

    data.append(["Payments", payments["total"]])

    ucn = commerce.CreditNote.unclaimed().values(
        "amount"
    ).aggregate(total=Sum("amount"))

    data.append(["Unclaimed credit notes", 0 - ucn["total"]])

    data.append([
        "(Money not on invoices)",
        sales["total"] - payments["total"] - ucn["total"],
    ])

    return Report("Sales and Payments", headings, data)


@report_view("Product status", form_type=forms.ProductAndCategoryForm)
def product_status(request, form):
    ''' Summarises the inventory status of the given items, grouping by
    invoice status. '''

    products = form.cleaned_data["product"]
    categories = form.cleaned_data["category"]

    items = commerce.ProductItem.objects.filter(
        Q(product__in=products) | Q(product__category__in=categories),
    ).select_related("cart", "product")

    items = items.annotate(
        is_reserved=Case(
            When(cart__in=commerce.Cart.reserved_carts(), then=Value(True)),
            default=Value(False),
            output_field=models.BooleanField(),
        ),
    )

    items = items.order_by(
        "product__category__order",
        "product__order",
    ).values(
        "product",
        "product__category__name",
        "product__name",
    ).annotate(
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

    return Report("Inventory", headings, data)


@report_view("Credit notes")
def credit_notes(request, form):
    ''' Shows all of the credit notes in the system. '''

    notes = commerce.CreditNote.objects.all().select_related(
        "creditnoterefund",
        "creditnoteapplication",
        "invoice",
        "invoice__user__attendee__attendeeprofilebase",
    )

    headings = [
        "id", "Owner", "Status", "Value",
    ]

    data = []
    for note in notes:
        data.append([
            note.id,
            note.invoice.user.attendee.attendeeprofilebase.invoice_recipient(),
            note.status,
            note.value,
        ])

    return Report("Credit Notes", headings, data, link_view="credit_note")


@report_view("Attendee", form_type=forms.UserIdForm)
def attendee(request, form, user_id=None):
    ''' Returns a list of all manifested attendees if no attendee is specified,
    else displays the attendee manifest. '''

    if user_id is None and not form.has_changed():
        return attendee_list(request)

    if form.cleaned_data["user"] is not None:
        user_id = form.cleaned_data["user"]

    attendee = people.Attendee.objects.get(user__id=user_id)

    reports = []

    # TODO: METADATA.

    ic = ItemController(attendee.user)
    # Paid products
    headings = ["Product", "Quantity"]
    data = []

    for pq in ic.items_purchased():
        data.append([
            pq.product,
            pq.quantity,
        ])

    reports.append(Report("Paid Products", headings, data))

    # Unpaid products
    headings = ["Product", "Quantity"]
    data = []

    for pq in ic.items_pending():
        data.append([
            pq.product,
            pq.quantity,
        ])

    reports.append( Report("Unpaid Products", headings, data))

    # Invoices
    headings = ["Invoice ID", "Status", "Value"]
    data = []

    invoices = commerce.Invoice.objects.filter(
        user=attendee.user,
    )
    for invoice in invoices:
        data.append([
            invoice.id, invoice.get_status_display(), invoice.value,
        ])

    reports.append(Report("Invoices", headings, data, link_view="invoice"))

    # Credit Notes
    headings = ["Note ID", "Status", "Value"]
    data = []

    credit_notes = commerce.CreditNote.objects.filter(
        invoice__user=attendee.user,
    )
    for credit_note in credit_notes:
        data.append([
            credit_note.id, credit_note.status, credit_note.value,
        ])

    reports.append(
        Report("Credit Notes", headings, data, link_view="credit_note")
    )

    # All payments
    headings = ["To Invoice", "Payment ID", "Reference", "Amount"]
    data = []

    payments = commerce.PaymentBase.objects.filter(
        invoice__user=attendee.user,
    )
    for payment in payments:
        data.append([
            payment.invoice.id, payment.id, payment.reference, payment.amount,
        ])

    reports.append(
        Report("Payments", headings, data, link_view="invoice")
    )


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

    for attendee in attendees:
        data.append([
            attendee.user.id,
            attendee.attendeeprofilebase.attendee_name(),
            attendee.user.email,
            attendee.has_registered > 0,
        ])

    # Sort by whether they've registered, then ID.
    data.sort(key=lambda attendee: (-attendee[3], attendee[0]))

    return Report("Attendees", headings, data, link_view="attendee")
