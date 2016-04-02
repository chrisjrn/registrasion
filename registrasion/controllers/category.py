from .product import ProductController

from registrasion import models as rego

class AllProducts(object):
    pass

class CategoryController(object):

    @classmethod
    def available_categories(cls, user, products=AllProducts):
        ''' Returns the categories available to the user. Specify `products` if
        you want to restrict to just the categories that hold the specified
        products, otherwise it'll do all. '''

        if products is AllProducts:
            products = rego.Product.objects.all()

        available = ProductController.available_products(
            user,
            products=products,
        )

        return set(i.category for i in available)
