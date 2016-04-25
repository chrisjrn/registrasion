Integrating Registrasion
========================

Registrasion is a Django app. It does not provide any templates -- you'll need to develop these yourself. You can use the `registrasion-demo <https://github.com/chrisjrn/registrasion-demo>`_ project as a starting point.

To use Registrasion for your own conference, you'll need to do a small amount of development work, usually in your own Django App.

The first is to define a model and form for your attendee profile, and the second is to implement a payment app.


Attendee profile
----------------

.. automodule:: registrasion.models.people

Attendee profiles are where you ask for information such as what your attendee wants on their badge, and what the attendee's dietary and accessibility requirements are.

Because every conference is different, Registrasion lets you define your own attendee profile model, and your own form for requesting this information. The only requirement is that you derive your model from ``AttendeeProfileBase``.

.. autoclass :: AttendeeProfileBase
    :members: name_field, invoice_recipient

Once you've subclassed ``AttendeeProfileBase``, you'll need to implement a form that lets attendees fill out their profile.

You specify how to find that form in your Django ``settings.py`` file::

    ATTENDEE_PROFILE_FORM = "democon.forms.AttendeeProfileForm"

The only contract is that this form creates an instance of ``AttendeeProfileBase`` when saved, and that it can take an instance of your subclass on creation (so that your attendees can edit their profile).


Payments
--------

Registrasion does not implement its own credit card processing. You'll need to do that yourself. Registrasion *does* provide a mechanism for recording cheques and direct deposits, if you do end up taking registrations that way.

See :ref:`payments_and_refunds` for a guide on how to correctly implement payments.
