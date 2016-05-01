import datetime
import pytz

from django.core.exceptions import ValidationError

from controller_helpers import TestingCartController
from test_cart import RegistrationCartTestCase

from registrasion.controllers.batch import BatchController
from registrasion.controllers.discount import DiscountController
from registrasion.controllers.product import ProductController
from registrasion.models import commerce
from registrasion.models import conditions

UTC = pytz.timezone('UTC')


class BatchTestCase(RegistrationCartTestCase):

    def test_no_caches_outside_of_batches(self):
        cache_1 = BatchController.get_cache(self.USER_1)
        cache_2 = BatchController.get_cache(self.USER_2)

        # Identity testing is important here
        self.assertIsNot(cache_1, cache_2)

    def test_cache_clears_at_batch_exit(self):
        with BatchController.batch(self.USER_1):
            cache_1 = BatchController.get_cache(self.USER_1)

        cache_2 = BatchController.get_cache(self.USER_1)

        self.assertIsNot(cache_1, cache_2)

    def test_caches_identical_within_nestings(self):
        with BatchController.batch(self.USER_1):
            cache_1 = BatchController.get_cache(self.USER_1)

            with BatchController.batch(self.USER_2):
                cache_2 = BatchController.get_cache(self.USER_1)

            cache_3 = BatchController.get_cache(self.USER_1)

        self.assertIs(cache_1, cache_2)
        self.assertIs(cache_2, cache_3)

    def test_caches_are_independent_for_different_users(self):
        with BatchController.batch(self.USER_1):
            cache_1 = BatchController.get_cache(self.USER_1)

            with BatchController.batch(self.USER_2):
                cache_2 = BatchController.get_cache(self.USER_2)

        self.assertIsNot(cache_1, cache_2)

    def test_cache_clears_are_independent_for_different_users(self):
        with BatchController.batch(self.USER_1):
            cache_1 = BatchController.get_cache(self.USER_1)

            with BatchController.batch(self.USER_2):
                cache_2 = BatchController.get_cache(self.USER_2)

            with BatchController.batch(self.USER_2):
                cache_3 = BatchController.get_cache(self.USER_2)

            cache_4 = BatchController.get_cache(self.USER_1)

        self.assertIs(cache_1, cache_4)
        self.assertIsNot(cache_1, cache_2)
        self.assertIsNot(cache_2, cache_3)

    def test_new_caches_for_new_batches(self):
        with BatchController.batch(self.USER_1):
            cache_1 = BatchController.get_cache(self.USER_1)

        with BatchController.batch(self.USER_1):
            cache_2 = BatchController.get_cache(self.USER_1)

            with BatchController.batch(self.USER_1):
                cache_3 = BatchController.get_cache(self.USER_1)

        self.assertIs(cache_2, cache_3)
        self.assertIsNot(cache_1, cache_2)
