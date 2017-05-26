import csv

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

    # Create & return view
    def _report(view):
        report_view = ReportView(view, title, form_type)
        report_view = user_passes_test(views._staff_only)(report_view)
        report_view = wraps(view)(report_view)

        # Add this report to the list of reports.
        _all_report_views.append(report_view)

        return report_view

    return _report


class ReportView(object):
    ''' View objects that can render report data into HTML or CSV. '''

    def __init__(self, inner_view, title, form_type):
        '''

        Arguments:
            inner_view: Callable that returns either a Report or a sequence of
                Report objects.

            title: The title that appears at the top of all of the reports.

            form_type: A Form class that can be used to query the report.

        '''

        # Consolidate form_type so it has content type and section
        self.inner_view = inner_view
        self.title = title
        self.form_type = form_type

    def __call__(self, request, *a, **k):
        data = ReportViewRequestData(self, request, *a, **k)
        return self.render(data)

    def get_form(self, request):

        ''' Creates an instance of self.form_type using request.GET '''

        # Create a form instance
        if self.form_type is not None:
            form = self.form_type(request.GET)

            # Pre-validate it
            form.is_valid()
        else:
            form = None

        return form

    @classmethod
    def wrap_reports(cls, reports, content_type):
        ''' Wraps the reports in a _ReportTemplateWrapper for the given
        content_type -- this allows data to be returned as HTML links, for
        instance. '''

        reports = [
            _ReportTemplateWrapper(content_type, report)
            for report in reports
        ]

        return reports

    def render(self, data):
        ''' Renders the reports based on data.content_type's value.

        Arguments:
            data (ReportViewRequestData): The report data. data.content_type
                is used to determine how the reports are rendered.

        Returns:
            HTTPResponse: The rendered version of the report.

        '''
        renderers = {
            "text/csv": self._render_as_csv,
            "text/html": self._render_as_html,
            None: self._render_as_html,
        }
        render = renderers[data.content_type]
        return render(data)

    def _render_as_html(self, data):
        ctx = {
            "title": self.title,
            "form": data.form,
            "reports": data.reports,
        }

        return render(data.request, "registrasion/report.html", ctx)

    def _render_as_csv(self, data):
        report = data.reports[data.section]

        # Create the HttpResponse object with the appropriate CSV header.
        response = HttpResponse(content_type='text/csv')

        writer = csv.writer(response)
        encode = lambda i: i.encode("utf8") if isinstance(i, unicode) else i  # NOQA
        writer.writerow(list(encode(i) for i in report.headings()))
        for row in report.rows():
            writer.writerow(list(encode(i) for i in row))

        return response


class ReportViewRequestData(object):
    '''

    Attributes:
        form (Form): form based on request
        reports ([Report, ...]): The reports rendered from the request

    Arguments:
        report_view (ReportView): The ReportView to call back to.
        request (HTTPRequest): A django HTTP request

    '''

    def __init__(self, report_view, request, *a, **k):

        self.report_view = report_view
        self.request = request

        # Calculate other data
        self.form = report_view.get_form(request)

        # Content type and section come from request.GET
        self.content_type = request.GET.get("content_type")
        self.section = request.GET.get("section")
        self.section = int(self.section) if self.section else None

        if self.content_type is None:
            self.content_type = "text/html"

        # Reports come from calling the inner view
        reports = report_view.inner_view(request, self.form, *a, **k)

        # Normalise to a list
        if isinstance(reports, Report):
            reports = [reports]

        # Wrap them in appropriate format
        reports = ReportView.wrap_reports(reports, self.content_type)

        self.reports = reports


def get_all_reports():
    ''' Returns all the views that have been registered with @report '''

    return list(_all_report_views)
