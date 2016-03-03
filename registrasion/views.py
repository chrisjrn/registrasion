from registrasion import forms
from registrasion import models as rego
from registrasion.controllers.cart import CartController

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.forms import formset_factory
from django.shortcuts import render
from functools import partial, wraps


@login_required
def product_category(request, category_id):
    ''' Registration selections form for a specific category of items '''

    category_id = int(category_id)  # Routing is [0-9]+
    category = rego.Category.objects.get(pk=category_id)

    ProductItemFormForCategory = (
        wraps(forms.ProductItemForm)
        (partial(forms.ProductItemForm, category=category)))
    ProductItemFormSet = formset_factory(ProductItemFormForCategory, extra=0)

    if request.method == "POST":
        formset = ProductItemFormSet(request.POST, request.FILES)
        if formset.is_valid():
            current_cart = CartController.for_user(request.user)
            with transaction.atomic():
                for form in formset.forms:
                    data = form.cleaned_data
                    # TODO set form error instead of failing completely
                    current_cart.set_quantity(
                        data["product"], data["quantity"], batched=True)
                current_cart.end_batch()
    else:
        # Create initial data for each of products in category
        initial = []
        products = rego.Product.objects.filter(category=category)
        items = rego.ProductItem.objects.filter(product__category=category)
        products = products.order_by("order")
        for product in products:
            try:
                quantity = items.get(product=product).quantity
            except ObjectDoesNotExist:
                quantity = 0
            data = {"product": product, "quantity": quantity}
            initial.append(data)

        formset = ProductItemFormSet(initial=initial)

    data = {
        "category": category,
        "formset": formset,
    }

    return render(request, "product_category.html", data)
