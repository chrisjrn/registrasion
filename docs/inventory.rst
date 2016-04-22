
Inventory Management
====================

Registrasion uses an inventory model to keep track of tickets, and the other various products that attendees of your conference might want to have, such as t-shirts and dinner tickets.

The inventory model is split up into Categories and Products. Categories are used to group Products.

Registrasion uses conditionals to build up complex tickets, or enable/disable specific items to specific users:

Often, you will want to offer free items, such as t-shirts or dinner tickets to your attendees. Registrasion has a Discounts facility that lets you automatically offer free items to your attendees as part of their tickets. You can also automatically offer promotional discounts, such as Early Bird discounts.

Sometimes, you may want to restrict parts of the conference to specific attendees, for example, you might have a Speakers Dinner to only speakers. Or you might want to restrict certain Products to attendees who have purchased other items, for example, you might want to sell Comfy Chairs to people who've bought VIP tickets. You can control showing and hiding specific products using Flags.


.. automodule:: registrasion.models.inventory

Categories
----------

Categories are logical groups of Products. Generally, you should keep like products in the same category, and use as many categories as you need.

You will need at least one Category to be able to sell tickets to your attendees.

Each category has the following attributes:

.. autoclass :: Category


Products
--------

Products represent the different items that comprise a user's conference ticket.

Each product has the following attributes:

.. autoclass :: Product


Vouchers
--------

Vouchers are used to enable Discounts or Flags for people who enter a voucher
code.

.. autoclass :: Voucher

If an attendee enters a voucher code, they have at least an hour to finalise
their registration before the voucher becomes unreserved. Only as many people
as allowed by ``limit`` are allowed to have a voucher reserved.


.. automodule:: registrasion.models.conditions

Discounts
---------

Discounts serve multiple purposes: they can be used to build up complex tickets by automatically waiving the costs for sub-products; they can be used to offer freebie tickets to specific people, or people who hold voucher codes; or they can be used to enable short-term promotional discounts.

Registrasion has several types of discounts, which enable themselves under specific conditions. We'll explain how these work later on, but first:

Common features
~~~~~~~~~~~~~~~
Each discount type has the following common attributes:

.. autoclass :: DiscountBase

You can apply a discount to individual products, or to whole categories, or both. All of the products and categories affected by the discount are displayed on the discount's admin page.

If you choose to specify individual products, you have these options:

.. autoclass :: DiscountForProduct

If you choose to specify whole categories, you have these options:

.. autoclass :: DiscountForCategory

Note that you cannot have a discount apply to both a category, and a product within that category.

Product Inclusions
~~~~~~~~~~~~~~~~~~
Product inclusion discounts allow you to enable a discount when an attendee has selected a specific enabling Product.

For example, if you want to give everyone with a ticket a free t-shirt, you can use a product inclusion to offer a 100% discount on the t-shirt category, if the attendee has selected one of your ticket Products.

Once a discount has been enabled in one Invoice, it is available until the quantities are exhausted for that attendee.

.. autoclass :: IncludedProductDiscount

Time/stock limit discounts
~~~~~~~~~~~~~~~~~~~~~~~~~~
These discounts allow you to offer a limited promotion that is automatically offered to all attendees. You can specify a time range for when the discount should be enabled, you can also specify a stock limit.

.. autoclass :: TimeOrStockLimitDiscount

Voucher discounts
~~~~~~~~~~~~~~~~~
Vouchers can be used to enable discounts.

.. autoclass :: VoucherDiscount

How discounts get applied
~~~~~~~~~~~~~~~~~~~~~~~~~
It's possible for multiple discounts to be available on any given Product. This means there need to be rules for how discounts get applied. It works like so:

#. Take all of the Products that the user currently has selected, and sort them so that the most expensive comes first.
#. Apply the highest-value discount line for the first Product, until either all such products have a discount applied, or the discount's Quantity has been exhausted for that user for that Product.
#. Repeat until all products have been processed.

In summary, the system greedily applies the highest-value discounts for each product. This may not provide a global optimum, but it'll do.

As an example: say a user has a voucher available for a 100% discount of tickets, and there's a promotional discount for 15% off tickets. In this case, the 100% discount will apply, and the 15% discount will not be disturbed.


Flags
-----

Flags are conditions that can be used to enable or disable Products or Categories, depending on whether conditions are met. They can be used to restrict specific products to specific people, or to place time limits on availability for products.

Common Features
~~~~~~~~~~~~~~~

.. autoclass :: FlagBase


Dependencies on products from category
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Category Dependency flags have their condition met if a product from the enabling category has been selected by the attendee. For example, if there is an *Accommodation* Category, this flag could be used to enable an *Accommodation Breakfast* category, allowing only attendees with accommodation to purchase breakfast.

.. autoclass :: CategoryFlag


Dependencies on products
~~~~~~~~~~~~~~~~~~~~~~~~
Product dependency flags have their condition met if one of the enabling products have been selected by the attendee.

.. autoclass :: ProductFlag

Time/stock limit flags
~~~~~~~~~~~~~~~~~~~~~~
These flags allow the products that they cover to be made available for a limited time, or to set a global ceiling on the products covered.

These can be used to remove items from sale once a sales deadline has been met, or if a venue for a specific event has reached capacity.  If there are items that fall under multiple such groupings, it makes sense to set all of these flags to be ``DISABLE_IF_FALSE``.

.. autoclass :: TimeOrStockLimitFlag

If any of the attributes are omitted, then only the remaining attributes affect the availablility of the products covered. If there's no attributes set at all, then the grouping has no effect, but it can be used to group products for reporting purposes.

Voucher flags
~~~~~~~~~~~~~
Vouchers can be used to enable flags.

.. autoclass :: VoucherFlag
