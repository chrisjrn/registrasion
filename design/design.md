# Logic

## Definitions
- User has one 'active Cart' at a time. The Cart remains active until a paid Invoice is attached to it.
- A 'paid Cart' is a Cart with a paid Invoice attached to it, where the Invoice has not been voided.
- An unpaid Cart is 'reserved' if
 - CURRENT_TIME - "Time last updated" <= max(reservation duration of Products in Cart),
 - A Voucher was added and CURRENT_TIME - "Time last updated" < VOUCHER_RESERVATION_TIME (15 minutes?)
- An Item is 'reserved' if:
  - it belongs to a reserved Cart
  - it belongs to a paid Cart
- A Cart can have any number of Items added to it, subject to limits.


## Entering Vouchers
- Vouchers are attached to Carts
- A user can enter codes for as many different Vouchers as they like.
- A Voucher is added to the Cart if the number of paid or reserved Carts containing the Voucher is less than the "total available" for the voucher.
- A cart is invalid if it contains a voucher that has been overused


## Are products available?

- Availability is determined by the number of items we want to add to the cart: items_to_add

- If items_to_add + count(Product in their active and paid Carts) > "Limit per user" for the Product, the Product is "unavailable".
- If the Product belongs to an exhausted Ceiling, the Product is "unavailable".
- Otherwise, the product is available


## Displaying Products:

- If there is at least one mandatory EnablingCondition attached to the Product, display it only if all EnablingConditions are met
- If there is at least one EnablingCondition attached to the Product, display it only if at least one EnablingCondition is met
- If there are zero EnablingConditions attached to the Product, display it
- If the product is not available for items_to_add=0, mark it as "unavailable"

- If the Product is displayed and available, its price is the price for the Product, minus the greatest Discount available to this Cart and Product

- The product is displayed per the rendering characteristics of the Category it belongs to


## Displaying Categories

- If the Category contains only "unavailable" Products, mark it as "unavailable"
- If the Category contains no displayed Products, do not display the Category
- If the Category contains at least one EnablingCondition, display it only if at least one EnablingCondition is met
- If the Category contains no EnablingConditions, display it


## Exhausting Ceilings

- Exhaustion is determined by the number of items we want to add to the cart: items_to_add

- A ceiling is exhausted if:
 - Its start date has not yet been reached
 - Its end date has been exceeded
 - items_to_add + sum(paid and reserved Items for each Product in the ceiling) > Total available


## Applying Discounts

- Discounts only apply to the current cart
- Discounts can be applied to multiple carts until the user has exhausted the quantity for each product attached to the discount.
- Only one discount discount can be applied to each single item. Discounts are applied as follows:
 - All non-exhausted discounts for the product or its category are ordered by value
 - The highest discount is applied for the lower of the quantity of the product in the cart, or the remaining quantity from this discount
 - If the quantity remaining is non-zero, apply the next available discount

- Individual discount objects should not contain more than one DiscountForProduct for the same product
- Individual discount objects should not contain more than one DiscountForCategory for the same category
- Individual discount objects should not contain a discount for both a product and its category


## Adding Items to the Cart

- Products that are not displayed may not be added to a Cart
- The requested number of items must be available for those items to be added to a Cart
- If a different price applies to a Product when it is added to a cart, add at the new price, and display an alert to the user
- If a discount is used when adding a Product to the cart, add the discount as well
- Adding an item resets the "Time last updated" for the cart
- Each time carts have items added or removed, the revision number is updated


## Generating an invoice

- User can ask to 'check out' the active Cart. Doing so generates an Invoice. The invoice corresponds to a revision number of the cart.
- Checking out the active Cart resets the "Time last updated" for the cart.
- The invoice represents the current state of the cart.
- If the revision number for the cart is different to the cart's revision number for the invoice, the invoice is void.
- The invoice is void if


## Paying an invoice

- A payment can only be attached to an invoice if all of the items in it are available at the time payment is processed

### One-Shot
- Update the "Time last updated" for the cart based on the expected time it takes for a payment to complete
- Verify that all items are available, and if so:
- Proceed to make payment
- Apply payment record from amount received


### Authorization-based approach:
- Capture an authorization on the card
- Verify that all items are available, and if so:
- Apply payment record
- Take payment


# Registration workflow:

## User has not taken a guided registration yet:

User is shown two options:

1. Undertake guided registration ("for current user")
1. Purchase vouchers


## User has not purchased a ticket, and wishes to:

This gives the user a guided registration process.

1. Take list of categories, sorted by display order, and display the next lowest enabled & available category
1. Take user to category page
1. User can click "back" to go to previous screen, or "next" to go the next lowest enabled & available category

Once all categories have been seen:
1. Ask for badge information -- badge information is *not* the same as the invoicee.
1. User is taken to the "user has purchased a ticket" workflow


## User is buying vouchers
TODO: Consider separate workflow for purchasing ticket vouchers.


## User has completed a guided registration or purchased vouchers

1. Show list of products that are pending purchase.
1. Show list of categories + badge information, as well as 'checkout' button if the user has items in their current cart


## Category page

- User can enter a voucher at any time
- User is shown the list of products that have been paid for
- User has the option to add/remove products that are in the current cart


## Checkout

1. Ask for invoicing details (pre-fill from previous invoice?)
1. Ask for payment


# User Models

- Profile:
 - User
 - Has done guided registration?
 - Badge
 -

## Transaction Models

- Cart:
 - User
 - {Items}
 - {Voucher}
 - {DiscountItems}
 - Time last updated
 - Revision Number
 - Active?

- Item
 - Product
 - Quantity

- DiscountItem
 - Product
 - Discount
 - Quantity

- Invoice:
 - Invoice number
 - User
 - Cart
 - Cart Revision
 - {Line Items}
 - (Invoice Details)
 - {Payments}
 - Voided?

- LineItem
 - Description
 - Quantity
 - Price

- Payment
 - Time
 - Amount
 - Reference


## Inventory Model

- Product:
 - Name
 - Description
 - Category
 - Price
 - Limit per user
 - Reservation duration
 - Display order
 - {Ceilings}


- Voucher
 - Description
 - Code
 - Total available


- Category?
 - Name
 - Description
 - Display Order
 - Rendering Style


## Product Modifiers

- Discount:
 - Description
 - {DiscountForProduct}
 - {DiscountForCategory}

 - Discount Types:
    - TimeOrStockLimitDiscount:
     * A discount that is available for a limited amount of time, e.g. Early Bird sales *
     - Start date
     - End date
     - Total available

    - VoucherDiscount:
     * A discount that is available to a specific voucher *
     - Voucher

    - RoleDiscount
     * A discount that is available to a specific role *
     - Role

    - IncludedProductDiscount:
     * A discount that is available because another product has been purchased *
     - {Parent Product}

- DiscountForProduct
 - Product
 - Amount
 - Percentage
 - Quantity

- DiscountForCategory
 - Category
 - Percentage
 - Quantity


- EnablingCondition:
 - Description
 - Mandatory?
 - {Products}
 - {Categories}

 - EnablingCondition Types:
   - ProductEnablingCondition:
    * Enabling because the user has purchased a specific product *
    - {Products that enable}

   - CategoryEnablingCondition:
    * Enabling because the user has purchased a product in a specific category *
    - {Categories that enable}

   - VoucherEnablingCondition:
    * Enabling because the user has entered a voucher code *
     - Voucher

   - RoleEnablingCondition:
     * Enabling because the user has a specific role *
     - Role

   - TimeOrStockLimitEnablingCondition:
    * Enabling because a time condition has been met, or a number of items underneath it have not been sold *
    - Start date
    - End date
    - Total available
