User-facing views
=================


View functions
--------------

Here's all of the views that Registrasion exposes to the public.

.. automodule:: registrasion.views
    :members:

Data types
~~~~~~~~~~

.. automodule:: registrasion.controllers.discount

.. autoclass:: DiscountAndQuantity


Template tags
-------------

Registrasion makes template tags available:

.. automodule:: registrasion.templatetags.registrasion_tags
    :members:


Rendering invoices
------------------

You'll need to render the following Django models in order to view invoices.

.. automodule:: registrasion.models.commerce

.. autoclass:: Invoice

.. autoclass:: LineItem

.. autoclass:: PaymentBase
