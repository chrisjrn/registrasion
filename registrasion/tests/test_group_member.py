import pytz

from django.contrib.auth.models import Group

from registrasion.models import conditions
from registrasion.controllers.product import ProductController

from registrasion.tests.test_cart import RegistrationCartTestCase

UTC = pytz.timezone('UTC')


class GroupMemberTestCase(RegistrationCartTestCase):

    @classmethod
    def _create_group_and_flag(cls):
        ''' Creates cls.GROUP_1, and restricts cls.PROD_1 only to users who are
        members of the group. Likewise GROUP_2 and PROD_2 '''

        groups = []
        products = [cls.PROD_1, cls.PROD_2]
        for i, product in enumerate(products):
            group = Group.objects.create(name="TEST GROUP" + str(i))
            flag = conditions.GroupMemberFlag.objects.create(
                description="Group member flag " + str(i),
                condition=conditions.FlagBase.ENABLE_IF_TRUE,
            )
            flag.group.add(group)
            flag.products.add(product)

            groups.append(group)

        cls.GROUP_1 = groups[0]
        cls.GROUP_2 = groups[1]

    def test_product_not_enabled_until_user_joins_group(self):
        ''' Tests that GroupMemberFlag disables a product for a user until
        they are a member of a specific group. '''

        self._create_group_and_flag()

        groups = [self.GROUP_1, self.GROUP_2]
        products = [self.PROD_1, self.PROD_2]

        for group, product in zip(groups, products):

            # USER_1 cannot see PROD_1 until they're in GROUP.
            available = ProductController.available_products(
                self.USER_1,
                products=[product],
            )
            self.assertNotIn(product, available)

            self.USER_1.groups.add(group)

            # USER_1 cannot see PROD_1 until they're in GROUP.
            available = ProductController.available_products(
                self.USER_1,
                products=[product],
            )
            self.assertIn(product, available)

            # USER_2 is still locked out
            available = ProductController.available_products(
                self.USER_2,
                products=[product],
            )
            self.assertNotIn(product, available)
