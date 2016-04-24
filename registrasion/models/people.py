from registrasion import util

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from model_utils.managers import InheritanceManager


# User models

@python_2_unicode_compatible
class Attendee(models.Model):
    ''' Miscellaneous user-related data. '''

    class Meta:
        app_label = "registrasion"

    def __str__(self):
        return "%s" % self.user

    @staticmethod
    def get_instance(user):
        ''' Returns the instance of attendee for the given user, or creates
        a new one. '''
        try:
            return Attendee.objects.get(user=user)
        except ObjectDoesNotExist:
            return Attendee.objects.create(user=user)

    def save(self, *a, **k):
        while not self.access_code:
            access_code = util.generate_access_code()
            if Attendee.objects.filter(access_code=access_code).count() == 0:
                self.access_code = access_code
        return super(Attendee, self).save(*a, **k)

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    # Badge/profile is linked
    access_code = models.CharField(
        max_length=6,
        unique=True,
        db_index=True,
    )
    completed_registration = models.BooleanField(default=False)
    guided_categories_complete = models.ManyToManyField("category")


class AttendeeProfileBase(models.Model):
    ''' Information for an attendee's badge and related preferences.
    Subclass this in your Django site to ask for attendee information in your
    registration progess.
     '''

    class Meta:
        app_label = "registrasion"

    objects = InheritanceManager()

    @classmethod
    def name_field(cls):
        '''
        Returns:
            The name of a field that stores the attendee's name. This is used
            to pre-fill the attendee's name from their Speaker profile, if they
            have one.
        '''
        return None

    def invoice_recipient(self):
        '''

        Returns:
            A representation of this attendee profile for the purpose
            of rendering to an invoice. This should include any information
            that you'd usually include on an invoice. Override in subclasses.
        '''

        # Manual dispatch to subclass. Fleh.
        slf = AttendeeProfileBase.objects.get_subclass(id=self.id)
        # Actually compare the functions.
        if type(slf).invoice_recipient != type(self).invoice_recipient:
            return type(slf).invoice_recipient(slf)

        # Return a default
        return slf.attendee.user.username

    attendee = models.OneToOneField(Attendee, on_delete=models.CASCADE)
