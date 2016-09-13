from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render
from django.core.urlresolvers import reverse
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


class OldReport(Report):

    def __init__(self, title, headings, data, link_view=None):
        super(OldReport, self).__init__()
        self._title = title
        self._headings = headings
        self._data = data
        self._link_view = link_view

    def title(self):
        ''' Returns the title for this report. '''
        return self._title

    def headings(self):
        ''' Returns the headings for the table. '''
        return self._headings

    def rows(self, content_type):
        ''' Returns the data rows for the table. '''

        def cell_text(index, text):
            if index > 0 or not self._link_view:
                return text
            else:
                address = self.get_link(text)
                return self._linked_text(content_type, address, text)

        for row in self._data:
            yield [cell_text(i, cell) for i, cell in enumerate(row)]

    def get_link(self, argument):
        return reverse(self._link_view, args=[argument])


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

            reports = [
                _ReportTemplateWrapper("text/html", report)
                for report in reports
            ]

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
