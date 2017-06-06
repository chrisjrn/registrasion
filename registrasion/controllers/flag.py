import itertools

from collections import defaultdict
from collections import namedtuple
from django.db.models import Count
from django.db.models import Q

from .batch import BatchController
from .conditions import ConditionController

from registrasion.models import conditions
from registrasion.models import inventory


class FlagController(object):

    @classmethod
    def test_flags(
            cls, user, products=None, product_quantities=None):
        ''' Evaluates all of the flag conditions on the given products.

        If `product_quantities` is supplied, the condition is only met if it
        will permit the sum of the product quantities for all of the products
        it covers. Otherwise, it will be met if at least one item can be
        accepted.

        If all flag conditions pass, an empty list is returned, otherwise
        a list is returned containing all of the products that are *not
        enabled*. '''

        if products is not None and product_quantities is not None:
            raise ValueError("Please specify only products or "
                             "product_quantities")
        elif products is None:
            products = set(i[0] for i in product_quantities)
            quantities = dict((product, quantity)
                              for product, quantity in product_quantities)
        elif product_quantities is None:
            products = set(products)
            quantities = {}

        if products:
            # Simplify the query.
            all_conditions = cls._filtered_flags(user)
        else:
            all_conditions = []

        all_conditions = conditions.FlagBase.objects.filter(
            id__in=(i.id for i in all_conditions)
        ).select_subclasses()

        # Prefetch all of the products and categories (Saves a LOT of queries)
        all_conditions = all_conditions.prefetch_related(
            "products", "categories"
        )

        # Now pre-select all of the products attached to those categories
        all_categories = set(
            cat for condition in all_conditions
                for cat in condition.categories.all()
        )
        all_category_ids = (i.id for i in all_categories)
        all_category_products = inventory.Product.objects.filter(
            category__in=all_category_ids
        ).select_related("category")

        products_by_category_ = itertools.groupby(all_category_products, lambda prod: prod.category)
        products_by_category = dict((k.id, list(v)) for (k, v) in products_by_category_)

        # All disable-if-false conditions on a product need to be met
        do_not_disable = defaultdict(lambda: True)
        # At least one enable-if-true condition on a product must be met
        do_enable = defaultdict(lambda: False)
        # (if either sort of condition is present)

        # Count the number of conditions for a product
        dif_count = defaultdict(int)
        eit_count = defaultdict(int)

        messages = {}

        for condition in all_conditions:
            cond = ConditionController.for_condition(condition)
            remainder = cond.user_quantity_remaining(user, filtered=True)

            # Get all products covered by this condition, and the products
            # from the categories covered by this condition

            condition_products = condition.products.all()
            category_products = (
                product for cat in condition.categories.all() for product in products_by_category[cat.id]
            )

            all_products = itertools.chain(
                condition_products, category_products
            )
            all_products = set(all_products)

            # Filter out the products from this condition that
            # are not part of this query.
            all_products = set(i for i in all_products if i in products)

            if quantities:
                consumed = sum(quantities[i] for i in all_products)
            else:
                consumed = 1
            met = consumed <= remainder

            if not met:
                message = cls._error_message(all_products, remainder)

            for product in all_products:
                if condition.is_disable_if_false:
                    do_not_disable[product] &= met
                    dif_count[product] += 1
                else:
                    do_enable[product] |= met
                    eit_count[product] += 1

                if not met and product not in messages:
                    messages[product] = message

        total_flags = FlagCounter.count(user)

        valid = {}

        # the problem is that now, not every condition falls into
        # do_not_disable or do_enable '''
        # You should look into this, chris :)

        for product in products:
            if quantities:
                if quantities[product] == 0:
                    continue

            f = total_flags.get(product)
            if f.dif > 0 and f.dif != dif_count[product]:
                do_not_disable[product] = False
                if product not in messages:
                    messages[product] = cls._error_message([product], 0)
            if f.eit > 0 and product not in do_enable:
                do_enable[product] = False
                if product not in messages:
                    messages[product] = cls._error_message([product], 0)

        for product in itertools.chain(do_not_disable, do_enable):
            f = total_flags.get(product)
            if product in do_enable:
                # If there's an enable-if-true, we need need of those met too.
                # (do_not_disable will default to true otherwise)
                valid[product] = do_not_disable[product] and do_enable[product]
            elif product in do_not_disable:
                # If there's a disable-if-false condition, all must be met
                valid[product] = do_not_disable[product]

        error_fields = [
            (product, messages[product])
            for product in valid if not valid[product]
        ]

        return error_fields

    SINGLE = True
    PLURAL = False
    NONE = True
    SOME = False
    MESSAGE = {
        NONE: {
            SINGLE:
                "%(items)s is no longer available to you",
            PLURAL:
                "%(items)s are no longer available to you",
        },
        SOME: {
            SINGLE:
                "Only %(remainder)d of the following item remains: %(items)s",
            PLURAL:
                "Only %(remainder)d of the following items remain: %(items)s"
        },
    }

    @classmethod
    def _error_message(cls, affected, remainder):
        product_strings = (str(product) for product in affected)
        items = ", ".join(product_strings)
        base = cls.MESSAGE[remainder == 0][len(affected) == 1]
        message = base % {"items": items, "remainder": remainder}
        return message

    @classmethod
    @BatchController.memoise
    def _filtered_flags(cls, user):
        '''

        Returns:
            Sequence[flagbase]: All flags that passed the filter function.

        '''

        types = list(ConditionController._controllers())
        flagtypes = [i for i in types if issubclass(i, conditions.FlagBase)]

        all_subsets = []

        for flagtype in flagtypes:
            flags = flagtype.objects.all()
            ctrl = ConditionController.for_type(flagtype)
            flags = ctrl.pre_filter(flags, user)
            all_subsets.append(flags)

        return list(itertools.chain(*all_subsets))


ConditionAndRemainder = namedtuple(
    "ConditionAndRemainder",
    (
        "condition",
        "remainder",
    ),
)


_FlagCounter = namedtuple(
    "_FlagCounter",
    (
        "products",
        "categories",
    ),
)


_ConditionsCount = namedtuple(
    "ConditionsCount",
    (
        "dif",
        "eit",
    ),
)


class FlagCounter(_FlagCounter):

    @classmethod
    @BatchController.memoise
    def count(cls, user):
        # Get the count of how many conditions should exist per product
        flagbases = conditions.FlagBase.objects

        types = (
            conditions.FlagBase.ENABLE_IF_TRUE,
            conditions.FlagBase.DISABLE_IF_FALSE,
        )
        keys = ("eit", "dif")
        flags = [
            flagbases.filter(
                condition=condition_type
            ).values(
                'products', 'categories'
            ).annotate(
                count=Count('id')
            )
            for condition_type in types
        ]

        cats = defaultdict(lambda: defaultdict(int))
        prod = defaultdict(lambda: defaultdict(int))

        for key, flagcounts in zip(keys, flags):
            for row in flagcounts:
                if row["products"] is not None:
                    prod[row["products"]][key] = row["count"]
                if row["categories"] is not None:
                    cats[row["categories"]][key] = row["count"]

        return cls(products=prod, categories=cats)

    def get(self, product):
        p = self.products[product.id]
        c = self.categories[product.category.id]
        eit = p["eit"] + c["eit"]
        dif = p["dif"] + c["dif"]
        return _ConditionsCount(dif=dif, eit=eit)
