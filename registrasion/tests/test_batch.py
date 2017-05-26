import pytz

from registrasion.tests.test_cart import RegistrationCartTestCase

from registrasion.controllers.batch import BatchController

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

    def test_memoisation_happens_in_batch_context(self):
        with BatchController.batch(self.USER_1):
            output_1 = self._memoiseme(self.USER_1)

            with BatchController.batch(self.USER_1):
                output_2 = self._memoiseme(self.USER_1)

        self.assertIs(output_1, output_2)

    def test_memoisaion_does_not_happen_outside_batch_context(self):
        output_1 = self._memoiseme(self.USER_1)
        output_2 = self._memoiseme(self.USER_1)

        self.assertIsNot(output_1, output_2)

    def test_memoisation_is_user_independent(self):
        with BatchController.batch(self.USER_1):
            output_1 = self._memoiseme(self.USER_1)
            with BatchController.batch(self.USER_2):
                output_2 = self._memoiseme(self.USER_2)
                output_3 = self._memoiseme(self.USER_1)

        self.assertIsNot(output_1, output_2)
        self.assertIs(output_1, output_3)

    def test_memoisation_clears_outside_batches(self):
        with BatchController.batch(self.USER_1):
            output_1 = self._memoiseme(self.USER_1)

        with BatchController.batch(self.USER_1):
            output_2 = self._memoiseme(self.USER_1)

        self.assertIsNot(output_1, output_2)

    @classmethod
    @BatchController.memoise
    def _memoiseme(self, user):
        return object()

    def test_batch_end_functionality_is_called(self):
        class Ender(object):
            end_count = 0

            def end_batch(self):
                self.end_count += 1

        @BatchController.memoise
        def get_ender(user):
            return Ender()

        # end_batch should get called once on exiting the batch
        with BatchController.batch(self.USER_1):
            ender = get_ender(self.USER_1)
        self.assertEquals(1, ender.end_count)

        # end_batch should get called once on exiting the batch
        # no matter how deep the object gets cached
        with BatchController.batch(self.USER_1):
            with BatchController.batch(self.USER_1):
                ender = get_ender(self.USER_1)
        self.assertEquals(1, ender.end_count)
