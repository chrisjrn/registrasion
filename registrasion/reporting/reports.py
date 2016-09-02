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

from registrasion import forms
from registrasion import views
from registrasion.models import commerce
from registrasion.models import inventory


''' A list of report views objects that can be used to load a list of
reports. '''
_all_report_views = []


class Report(object):

    def __init__(self, title, headings, data):
        self._headings = headings
        self._data = data

    @property
    def title(self):
        ''' Returns the title for this report. '''
        return self._title

    @property
    def headings(self):
        ''' Returns the headings for the table. '''
        return self._headings

    @property
    def data(self):
        ''' Returns the data rows for the table. '''
        return self._data


def report_view(title, form_type=None):
    ''' Decorator that converts a report view function into something that
    displays a Report.

    Arguments:
        title (str):
            The title of the report.
        form_type (Optional[forms.Form]):
            A form class that can make this report display things. If not
            supplied, no form will be displayed.

    '''

    def _report(view):

        @wraps(view)
        @user_passes_test(views._staff_only)
        def inner_view(request, *a, **k):

            if form_type is not None:
                form = form_type(request.GET)
                form.is_valid()
            else:
                form = None

            report = view(request, form, *a, **k)

            ctx = {
                "title": title,
                "form": form,
                "report": report,
            }

            return render(request, "registrasion/report.html", ctx)

        # Add this report to the list of reports.
        _all_report_views.append(inner_view)

        # Return the callable
        return inner_view
    return _report


def get_all_reports():
    ''' Returns all the views that have been registered with @report '''

    return list(_all_report_views)
