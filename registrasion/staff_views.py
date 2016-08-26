import forms

from django.db.models import Q
from django.db.models import Sum
from django.shortcuts import render
from functools import wraps

from models import commerce


'''

All reports must be viewable by staff only (permissions?)

Reports can have:

A form
 * Reports are all *gettable* - you can save a URL and get back to the same
 report
 * Fetching a report *cannot* break the underlying data.
A table
 * Headings
 * Data lines
 * Formats are pluggable

'''


class Report(object):

    def __init__(self, title, form, headings, data):
        self._title = title
        self._form = form
        self._headings = headings
        self._data = data

    @property
    def title(self):
        ''' Returns the form. '''
        return self._title

    @property
    def form(self):
        ''' Returns the form. '''
        return self._form

    @property
    def headings(self):
        ''' Returns the headings for the table. '''
        return self._headings

    @property
    def data(self):
        ''' Returns the data rows for the table. '''
        return self._data


def report(view):
    ''' Decorator that converts a report view function into something that
    displays a Report.

    '''

    @wraps(view)
    def inner_view(request, *a, **k):
        report = view(request, *a, **k)

        ctx = {
            "title": report.title,
            "form": report.form,
            "report": report,
        }

        return render(request, "registrasion/report.html", ctx)

    return inner_view


@report
def items_sold(request):
    ''' Summarises the items sold and discounts granted for a given set of
    products, or products from categories. '''

    title = "Paid items"

    form = forms.ProductAndCategoryForm(request.GET)

    data = None
    headings = None

    if form.is_valid() and form.has_changed():
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

        headings = ["description", "quantity", "price", "total"]

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

    return Report(title, form, headings, data)
