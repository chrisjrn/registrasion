from django.utils import timezone


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
