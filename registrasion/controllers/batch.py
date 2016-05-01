import contextlib
import functools

from django.contrib.auth.models import User


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
    _NESTING_KEY = "nesting_count"

    @classmethod
    @contextlib.contextmanager
    def batch(cls, user):
        ''' Marks the entry point for a batch for the given user. '''

        cls._enter_batch_context(user)
        try:
            yield
        finally:
            # Make sure we clean up in case of errors.
            cls._exit_batch_context(user)

    @classmethod
    def _enter_batch_context(cls, user):
        if user not in cls._user_caches:
            cls._user_caches[user] = cls._new_cache()

        cache = cls._user_caches[user]
        cache[cls._NESTING_KEY] += 1

    @classmethod
    def _exit_batch_context(cls, user):
        cache = cls._user_caches[user]
        cache[cls._NESTING_KEY] -= 1

        if cache[cls._NESTING_KEY] == 0:

            for key in cache:
                item = cache[key]
                if hasattr(item, 'end_batch') and callable(item.end_batch):
                    item.end_batch()

            del cls._user_caches[user]

    @classmethod
    def memoise(cls, func):
        ''' Decorator that stores the result of the stored function in the
        user's results cache until the batch completes. Keyword arguments are
        not yet supported.

        Arguments:
            func (callable(*a)): The function whose results we want
                to store. The positional arguments, ``a``, are used as cache
                keys.

        Returns:
            callable(*a): The memosing version of ``func``.

        '''

        @functools.wraps(func)
        def f(*a):

            for arg in a:
                if isinstance(arg, User):
                    user = arg
                    break
            else:
                raise ValueError("One position argument must be a User")

            func_key = (func, tuple(a))
            cache = cls.get_cache(user)

            if func_key not in cache:
                cache[func_key] = func(*a)

            return cache[func_key]

        return f

    @classmethod
    def get_cache(cls, user):
        if user not in cls._user_caches:
            # Return blank cache here, we'll just discard :)
            return cls._new_cache()

        return cls._user_caches[user]

    @classmethod
    def _new_cache(cls):
        ''' Returns a new cache dictionary. '''
        cache = {}
        cache[cls._NESTING_KEY] = 0
        return cache
