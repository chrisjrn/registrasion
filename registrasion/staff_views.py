import forms
import views

from collections import namedtuple

from django.contrib.auth.decorators import user_passes_test
from django.core.urlresolvers import reverse
from django.db import models
from django.db.models import F, Q
from django.db.models import Sum
from django.db.models import Case, When, Value
from django.http import Http404
from django.shortcuts import render
from functools import wraps

from models import commerce
from models import inventory

from reporting.reports import Report
from reporting.reports import report_view


@user_passes_test(views._staff_only)
def reports_list(request):
    ''' Lists all of the reports currently available. '''

    reports = []

    for report in _all_report_views:
        reports.append({
            "name" : report.__name__,
            "url" : reverse(report),
            "description" : report.__doc__,
        })

    reports.sort(key=lambda report: report["name"])

    ctx = {
        "reports" : reports,
    }

    return render(request, "registrasion/reports_list.html", ctx)


# Report functions


@report_view("Paid items", forms.ProductAndCategoryForm)
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


@report_view("Inventory", forms.ProductAndCategoryForm)
def inventory(request, form):
    ''' Summarises the inventory status of the given items, grouping by
    invoice status. '''

    products = form.cleaned_data["product"]
    categories = form.cleaned_data["category"]

    items = commerce.ProductItem.objects.filter(
        Q(product__in=products) | Q(product__category__in=categories),
    ).select_related("cart", "product")

    items = items.annotate(
        is_reserved=Case(
            When(cart__in=commerce.Cart.reserved_carts(), then=Value(1)),
            default=Value(0),
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
