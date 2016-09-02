from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render
from functools import wraps

from registrasion import views


''' A list of report views objects that can be used to load a list of
reports. '''
_all_report_views = []


class Report(object):

    def __init__(self, title, headings, data, link_view=None):
        self._title = title
        self._headings = headings
        self._data = data
        self._link_view = link_view

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

    @property
    def link_view(self):
        ''' Returns the URL name or the view callable that can be used to
        view the row's detail. The left-most value is passed into `reverse`
        as an argument. '''

        return self._link_view


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

            reports = view(request, form, *a, **k)

            if isinstance(reports, Report):
                reports = [reports]

            ctx = {
                "title": title,
                "form": form,
                "reports": reports,
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
