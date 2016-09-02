from django.utils import timezone

from registrasion.contrib import mail


class SetTimeMixin(object):
    ''' Patches timezone.now() for the duration of a test case. Allows us to
    test time-based conditions (ceilings etc) relatively easily. '''

    def setUp(self):
        super(SetTimeMixin, self).setUp()
        self._old_timezone_now = timezone.now
        self.now = timezone.now()
        timezone.now = self.new_timezone_now

    def tearDown(self):
        timezone.now = self._old_timezone_now
        super(SetTimeMixin, self).tearDown()

    def set_time(self, time):
        self.now = time

    def add_timedelta(self, delta):
        self.now += delta

    def new_timezone_now(self):
        return self.now


class SendEmailMixin(object):

    def setUp(self):
        super(SendEmailMixin, self).setUp()

        self._old_sender = mail.__send_email__
        mail.__send_email__ = self._send_email
        self.emails = []

    def _send_email(self, template_prefix, to, kind, **kwargs):
        args = {"to": to, "kind": kind}
        args.update(kwargs)
        self.emails.append(args)

    def tearDown(self):
        mail.__send_email__ = self._old_sender
        super(SendEmailMixin, self).tearDown()


class MixInPatches(SetTimeMixin, SendEmailMixin):
    pass
