import pytz

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError

from registrasion.models import commerce
from registrasion.models import conditions
from registrasion.controllers.category import CategoryController
from controller_helpers import TestingCartController
from controller_helpers import TestingInvoiceController
from registrasion.controllers.product import ProductController

from test_cart import RegistrationCartTestCase

UTC = pytz.timezone('UTC')


class GroupMemberTestCase(RegistrationCartTestCase):

    @classmethod
    def _create_group_and_flag(cls):
        ''' Creates cls.GROUP, and restricts cls.PROD_1 only to users who are
        members of the group. '''

        group = Group.objects.create(
            name="TEST GROUP",
        )

        flag = conditions.GroupMemberFlag.objects.create(
            description="Group member flag",
            condition=conditions.FlagBase.ENABLE_IF_TRUE,
        )
        flag.group.add(group)
        flag.products.add(cls.PROD_1)

        cls.GROUP = group

    def test_product_not_enabled_until_user_joins_group(self):
        ''' Tests that GroupMemberFlag disables a product for a user until
        they are a member of a specific group. '''

        self._create_group_and_flag()

        # USER_1 cannot see PROD_1 until they're in GROUP.
        available = ProductController.available_products(
            self.USER_1,
            products=[self.PROD_1],
        )
        self.assertNotIn(self.PROD_1, available)

        self.USER_1.groups.add(self.GROUP)

        # USER_1 cannot see PROD_1 until they're in GROUP.
        available = ProductController.available_products(
            self.USER_1,
            products=[self.PROD_1],
        )
        self.assertIn(self.PROD_1, available)

        # USER_2 is still locked out
        available = ProductController.available_products(
            self.USER_2,
            products=[self.PROD_1],
        )
        self.assertNotIn(self.PROD_1, available)
