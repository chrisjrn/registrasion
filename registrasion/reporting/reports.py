import csv
import forms

from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render
from django.core.urlresolvers import reverse
from django.http import HttpResponse
from functools import wraps

from registrasion import views


''' A list of report views objects that can be used to load a list of
reports. '''
_all_report_views = []


class Report(object):

    def __init__(self):
        pass

    def title():
        raise NotImplementedError

    def headings():
        ''' Returns the headings for the report. '''
        raise NotImplementedError

    def rows(content_type):
        '''

        Arguments:
            content_type (str): The content-type for the output format of this
            report.

        Returns:
            An iterator, which yields each row of the data. Each row should
            be an iterable containing the cells, rendered appropriately for
            content_type.
        '''
        raise NotImplementedError

    def _linked_text(self, content_type, address, text):
        '''

        Returns:
            an HTML linked version of text, if the content_type for this report
            is HTMLish, otherwise, the text.
        '''

        if content_type == "text/html":
            return Report._html_link(address, text)
        else:
            return text

    @staticmethod
    def _html_link(address, text):
        return '<a href="%s">%s</a>' % (address, text)


class _ReportTemplateWrapper(object):
    ''' Used internally to pass `Report` objects to templates. They effectively
    are used to specify the content_type for a report. '''

    def __init__(self, content_type, report):
        self.content_type = content_type
        self.report = report

    def title(self):
        return self.report.title()

    def headings(self):
        return self.report.headings()

    def rows(self):
        return self.report.rows(self.content_type)


class BasicReport(Report):

    def __init__(self, title, headings, link_view=None):
        super(BasicReport, self).__init__()
        self._title = title
        self._headings = headings
        self._link_view = link_view

    def title(self):
        ''' Returns the title for this report. '''
        return self._title

    def headings(self):
        ''' Returns the headings for the table. '''
        return self._headings

    def cell_text(self, content_type, index, text):
        if index > 0 or not self._link_view:
            return text
        else:
            address = self.get_link(text)
            return self._linked_text(content_type, address, text)

    def get_link(self, argument):
        return reverse(self._link_view, args=[argument])


class ListReport(BasicReport):

    def __init__(self, title, headings, data, link_view=None):
        super(ListReport, self).__init__(title, headings, link_view=link_view)
        self._data = data

    def rows(self, content_type):
        ''' Returns the data rows for the table. '''

        for row in self._data:
            yield [
                self.cell_text(content_type, i, cell)
                for i, cell in enumerate(row)
            ]


class QuerysetReport(BasicReport):

    def __init__(self, title, attributes, queryset, headings=None,
                 link_view=None):
        super(QuerysetReport, self).__init__(
            title, headings, link_view=link_view
        )
        self._attributes = attributes
        self._queryset = queryset

    def headings(self):
        if self._headings is not None:
            return self._headings

        return [
            " ".join(i.split("_")).capitalize() for i in self._attributes
        ]

    def rows(self, content_type):

        def rgetattr(item, attr):
            for i in attr.split("__"):
                item = getattr(item, i)

            if callable(item):
                try:
                    return item()
                except TypeError:
                    pass

            return item

        for row in self._queryset:
            yield [
                self.cell_text(content_type, i, rgetattr(row, attribute))
                for i, attribute in enumerate(self._attributes)
            ]


class Links(Report):

    def __init__(self, title, links):
        '''
        Arguments:
            links ([tuple, ...]): a list of 2-tuples:
                (url, link_text)

        '''
        self._title = title
        self._links = links

    def title(self):
        return self._title

    def headings(self):
        return []

    def rows(self, content_type):
        print self._links
        for url, link_text in self._links:
            yield [
                self._linked_text(content_type, url, link_text)
            ]


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

    # Consolidate form_type so it has format and section
    bases = [forms.SectionContentTypeForm, form_type]
    bases = [base for base in bases if base is not None]
    form_type = forms.mix_form(*bases)

    # Create & return view

    def _report(view):

        @wraps(view)
        @user_passes_test(views._staff_only)
        def inner_view(request, *a, **k):
            return ReportView(request, view, title, form_type).view(*a, **k)

        # Add this report to the list of reports.
        _all_report_views.append(inner_view)

        # Return the callable
        return inner_view
    return _report

class ReportView(object):

    def __init__(self, request, inner_view, title, form_type):
        self.request = request
        self.inner_view = inner_view
        self.title = title
        self.form_type = form_type
        self._prepare()

    def view(self, *a, **k):
        self._prepare_reports(*a, **k)

        return self._render()

    def _prepare(self):

        # Create a form instance
        if self.form_type is not None:
            form = self.form_type(self.request.GET)

            # Pre-validate it
            form.is_valid()
        else:
            form = None

        self.form = form
        self.content_type = form.cleaned_data["content_type"]
        self.section = form.cleaned_data["section"]

        renderers = {
            "text/csv": self._render_as_csv,
            "text/html": self._render_as_html,
            "": self._render_as_html,
        }
        self._render = renderers[self.content_type]

    def _prepare_reports(self, *a, **k):
        reports = self.inner_view(self.request, self.form, *a, **k)

        if isinstance(reports, Report):
            reports = [reports]

        self.reports = self._wrap_reports(reports)

    def _render(self):
        ''' Replace with a specialist _render function '''

    def _wrap_reports(self, reports):
        reports = [
            _ReportTemplateWrapper(self.content_type, report)
            for report in reports
        ]

        return reports

    def _render_as_html(self):

        ctx = {
            "title": self.title,
            "form": self.form,
            "reports": self.reports,
        }

        return render(self.request, "registrasion/report.html", ctx)

    def _render_as_csv(self):
        report = self.reports[self.section]

        # Create the HttpResponse object with the appropriate CSV header.
        response = HttpResponse(content_type='text/csv')
        #response['Content-Disposition'] = 'attachment; filename="somefilename.csv"'

        writer = csv.writer(response)
        writer.writerow(list(report.headings()))
        for row in report.rows():
            writer.writerow(list(row))

        return response



def get_all_reports():
    ''' Returns all the views that have been registered with @report '''

    return list(_all_report_views)
