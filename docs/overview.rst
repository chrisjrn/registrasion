Overview
========

Registrasion's approach to handling conference registrations is to use a cart and inventory model, where the various things sold by the conference to attendees are handled as Products, which can be added to a Cart. Carts can be used to generate Invoices, and Invoices can then be paid.


Guided registration
-------------------

Unlike a generic e-commerce platform, Registrasion is designed for building up conference tickets.

When they first attempt registration, attendees start off in a process called *guided mode*. Guided mode is multi-step form that takes users through a complete registration process:

#. The attendee fills out their profile
#. The attendee selects a ticket type
#. The attendee selects additional products such as t-shirts and dinner tickets, which may be sold at a cost, or have waivers applied.
#. The attendee is offered the opportunity to check out their cart, generating an invoice; or to enter amendments mode.

For specifics on how guided mode works, see *code guide to be written*.


Amendments mode
---------------

Once attendees have reached the end of guided registration, they are permanently added to *amendments mode*. Amendments mode allows attendees to change their product selections in a given category, with one rule: once an invoice has been paid, product selections cannot be changed without voiding that invoice (and optionally releasing a Credit Note).

Users can check out their current selections at any time, and generate an Invoice for their selections. That invoice can then be paid, and the attendee will then be making selections on a new cart.


Invoices
--------

When an attendee checks out their Cart, an Invoice is generated for their cart.

An invoice is valid for as long as the items in the cart do not change, and remain generally available. If a user amends their cart after generating an invoice, the user will need to check out their cart again, and generate a new invoice.

Once an invoice is paid, it is no longer possible for an invoice to be void, instead, it needs to have a refund generated.


User-Attendee Model
-------------------

Registrasion uses a User-Attendee model. This means that Registrasion expects each user account on the system to represent a single attendee at the conference. It also expects that the attendee themselves fill out the registration form.

This means that each attendee has a confirmed e-mail address for conference-related communications. It's usually a good idea for the conference to make sure that their account sign-up page points this out, so that administrative assistants at companies don't end up being the ones getting communicated at.

How do people get their employers to pay for their tickets?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Registrasion provides a semi-private URL that allows anyone in possession of this URL to view that attendee's most recent invoice, and make payments against that invoice.

A future release will add the ability to bulk-pay multiple invoices at once.
