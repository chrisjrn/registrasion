import contextlib
import functools


class BatchController(object):
    ''' Batches are sets of operations where certain queries for users may be
    repeated, but are also unlikely change within the boundaries of the batch.

    Batches are keyed per-user. You can mark the edge of the batch with the
    ``batch`` context manager. If you nest calls to ``batch``, only the
    outermost call will have the effect of ending the batch.

    Batches store results for functions wrapped with ``memoise``. These results
    for the user are flushed at the end of the batch.

    If a return for a memoised function has a callable attribute called
    ``end_batch``, that attribute will be called at the end of the batch.

    '''

    _user_caches = {}

    @classmethod
    @contextlib.contextmanager
    def batch(cls, user):
        ''' Marks the entry point for a batch for the given user. '''
        pass
        # TODO: store nesting count *inside* the cache object. You know it
        # makes sense.

    @classmethod
    def memoise(cls, func):
        ''' Decorator that stores the result of the stored function in the
        user's results cache until the batch completes.

        Arguments:
            func (callable(user, *a, **k)): The function whose results we want
                to store. ``user`` must be the first argument; this is used as
                the cache key.

        Returns:
            callable(user, *a, **k): The memosing version of ``func``.

        '''

        @functools.wraps(func)
        def f(user, *a, **k):

            cache = cls.get_cache(user)
            if func not in cache:
                cache[func] = func(user, *a, **k)

            return cache[func]

        return f

    @classmethod
    def get_cache(cls, user):
        if user not in cls._user_caches:
            return {}  # Return blank cache here, we'll just discard :)

        return cls._user_caches[user]


'''
TODO: memoise CartController.for_user
TODO: memoise user_remainders (Product, Category)
TODO: memoise _filtered_flags
TODO: memoise FlagCounter.count() (doesn't take user, but it'll do for now)
TODO: memoise _filtered_discounts

Tests:
- Correct nesting behaviour
 - do we get different cache objects every time we get a cache in non-batched
   contexts?
 - do we get the same cache object for nested caches?
  - do we get different cache objects when we back out of a batch and enter a
   new one
- are cache clears independent for different users?
- ``end_batch`` behaviour for CartController (use for_user *A LOT*)
  - discounts not calculated until outermost batch point exits.
  - Revision number shouldn't change until outermost batch point exits.
- Make sure memoisation ONLY happens when we're in a batch.

'''
