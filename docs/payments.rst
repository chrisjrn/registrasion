.. automodule:: registrasion.models.commerce
.. _payments_and_refunds:

Payments and Refunds
====================

Registrasion aims to support whatever payment platform you have available to use. Therefore, Registrasion uses a bare minimum payments model to track money within the system. It's the role of you, as a deployer of Registrasion, to implement a payment application that communicates with your own payment platform.

Invoices may have multiple ``PaymentBase`` objects attached to them; each of these represent a payment against the invoice. Payments can be negative (and this represents a refund against the Invoice), however, this approach is not recommended for use by implementers.

Registrasion also keeps track of money that is not currently attached to invoices through `credit notes`_. Credit notes may be applied to unpaid invoices *in full*, if there is an amount left over from the credit note, a new credit note will be created from that amount. Credit notes may also be released, at which point they're the responsibility of the payment application to create a refund.

Finally, Registrasion provides a `manual payments`_ feature, which allows for staff members to manually report payments into the system. This is the only payment facility built into Registrasion, but it's not intended as a reference implementation.


Invoice and payment access control
----------------------------------

Conferences are interesting: usually you want attendees to fill in their own registration so that they get their catering options right, so that they can personally agree to codes of conduct, and so that you can make sure that you're communicating key information directly with them.

On the other hand, employees at companies often need for their employers to directly pay for their registration.

Registrasion solves this problem by having attendees complete their own registration, and then providing an access URL that allows anyone who holds that URL to view their invoice and make payment.

You can call ``InvoiceController.can_view`` to determine whether or not you're allowed to show the invoice. It returns true if the user is allowed to view the invoice::

    InvoiceController.can_view(self, user=request.user, access_code="CODE")

As a rule, you should call ``can_view`` before doing any operations that amend the status of an invoice. This includes taking payments or requesting refunds.

The access code is unique for each attendee -- this means that every invoice that an attendee generates can be viewed with the same access code. This is useful if the user amends their registration between giving the URL to their employer, and their employer making payment.




Making payments
---------------

Making payments is a three-step process:

#. Validate that the invoice is ready to be paid,
#. Create a payment object for the amount that you are paying towards an invoice,
#. Ask the invoice to calculate its status now that the payment has been made.

Pre-validation
~~~~~~~~~~~~~~
Registrasion's ``InvoiceController`` has a ``validate_allowed_to_pay`` method, which performs all of the pre-payment checks (is the invoice still unpaid and non-void? has the registration been amended?).

If the pre-payment check fails, ``InvoiceController`` will raise a Django ``ValidationError``.

Our the ``demopay`` view from the ``registrasion-demo`` project implements pre-validation like so::

    from registrasion.controllers.invoice import InvoiceController
    from django.core.exceptions import ValidationError

    invoice = InvoiceController.for_id_or_404(invoice.id)

    try:
        invoice.validate_allowed_to_pay()  # Verify that we're allowed to do this.
    except ValidationError as ve:
        messages.error(request, ve.message)
        return REDIRECT_TO_INVOICE  # And display the validation message.

In most cases, you don't engage your actual payment application until after pre-validation is finished, as this gives you an opportunity to bail out if the invoice isn't able to have funds applied to it.

Applying payments
~~~~~~~~~~~~~~~~~
Payments in Registrasion are represented as subclasses of the ``PaymentBase`` model. ``PaymentBase`` looks like this:

.. autoclass :: PaymentBase

When you implement your own payment application, you'll need to subclass ``PaymentBase``, as this will allow you to add metadata that lets you link the Registrasion payment object with your payment platform's object.

Generally, the ``reference`` field should be something that lets your end-users identify the payment on their credit card statement, and to provide to your team's tech support in case something goes wrong.

Once you've subclassed ``PaymentBase``, applying a payment is really quite simple. In the ``demopay`` view, we have a subclass called ``DemoPayment``::

    invoice = InvoiceController(some_invoice_model)

    # Create the payment object
    models.DemoPayment.objects.create(
        invoice=invoice.invoice,
        reference="Demo payment by user: " + request.user.username,
        amount=invoice.invoice.value,
    )

Note that multiple payments can be provided against an ``Invoice``, however, payments that exceed the total value of the invoice will have credit notes generated.

Updating an invoice's status
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
``InvoiceController`` has a method called ``update_status``. You should call ``update_status`` immediately after you create a ``PaymentBase`` object, as this keeps invoice and its payments synchronised::

    invoice = InvoiceController(some_invoice_model)
    invoice.update_status()

Calling ``update_status`` collects the ``PaymentBase`` objects that are attached to the ``Invoice``, and will update the status of the invoice:

* If an invoice is ``VOID``, it will remain void.
* If an invoice is ``UNPAID`` and it now has ``PaymentBase`` objects whose value meets or exceed's the invoice's value, the invoice becomes ``PAID``.
* If an invoice is ``UNPAID`` and it now has ``PaymentBase`` objects whose values sum to zero, the invoice becomes ``VOID``.
* If an invoice is ``PAID`` and it now has ``PaymentBase`` objects of less than the invoice's value, the invoice becomes ``REFUNDED``.

When your invoice becomes ``PAID`` for the first time, if there's a cart of inventory items attached to it, that cart becomes permanently reserved -- that is, all of the items within it are no longer available for other users to purchase. If an invoice becomes ``REFUNDED``, the items in the cart are released, which means that they are available for anyone to purchase again.

If you overpay an invoice, or pay into an invoice that should not have funds attached, a credit note for the residual payments will also be issued.

In general, although this means you *can* use negative payments to take an invoice into a *REFUNDED* state, it's still much more sensible to use the credit notes facility, as this makes sure that any leftover funds remain tracked in the system.


Credit Notes
------------

When you refund an invoice, often you're doing so in order to make a minor amendment to items that the attendee has purchased. In order to make it easy to transfer funds from a refunded invoice to a new invoice, Registrasion provides an automatic credit note facility.

Credit notes are created when you mark an invoice as refunded, but they're also created if you overpay an invoice, or if you direct money into an invoice that can no longer take payment.

Once created, Credit Notes act as a payment that can be put towards other invoices, or that can be cashed out, back to the original payment platform. Credits can only be applied or cashed out in full.

This means that it's easy to track funds that aren't accounted for by invoices -- it's just the sum of the credit notes that haven't been applied to new invoices, or haven't been cashed out.

We recommend using credit notes to track all of your refunds for consistency; it also allows you to invoice for cancellation fees and the like.

Creating credit notes
~~~~~~~~~~~~~~~~~~~~~
In Registrasion, credit notes originate against invoices, and are represented as negative payments to an invoice.

Credit notes are usually created automatically. In most cases, Credit Notes come about from asking to refund an invoice::

    InvoiceController(invoice).refund()

Calling ``refund()`` will generate a refund of all of the payments applied to that invoice.

Otherwise, credit notes come about when invoices are overpaid, in this case, a credit for the overpay amount will be generated.

Applying credits to new invoices
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Credits can be applied to invoices::

    CreditNoteController(credit_not).apply_to_invoice(invoice)

This will result in an instance of ``CreditNoteApplication`` being applied as a payment to ``invoice``. ``CreditNoteApplication`` will always be a payment of the full amount of its parent credit note. If this payment overpays the invoice it's being applied to, a credit note for the residual will be generated.

Refunding credit notes
~~~~~~~~~~~~~~~~~~~~~~
It is possible to release a credit note back to the original payment platform. To do so, you attach an instance of ``CreditNoteRefund`` to the original ``CreditNote``:

.. autoclass :: CreditNoteRefund

You'll usually want to make a subclass of ``CreditNoteRefund`` for your own purposes, usually so that you can tie Registrasion's internal representation of the refund to a concrete refund on the side of your payment platform.

Note that you can only release a credit back to the payment platform for the full amount of the credit.


Manual payments
---------------

Registrasion provides a *manual payments* feature, which allows for staff members to manually report payments into the system. This is the only payment facility built into Registrasion, but it's not intended as a reference implementation.

The main use case for manual payments is to record the receipt of funds from bank transfers or cheques sent on behalf of attendees.

It's not intended as a reference implementation is because it does not perform validation of the cart before the payment is applied to the invoice.

This means that it's possible for a staff member to apply a payment with a specific invoice reference into the invoice matching that reference. Registrasion will generate a credit note if the invoice is not able to receive payment (e.g. because it has since been voided), you can use that credit note to pay into a valid invoice if necessary.

It is possible for staff to enter a negative amount on a manual payment. This will be treated as a refund. Generally, it's preferred to issue a credit note to an invoice rather than enter a negative amount manually.
