import string

from django.utils.crypto import get_random_string


def generate_access_code():
    ''' Generates an access code for users' payments as well as their
    fulfilment code for check-in.
    The access code will 4 characters long, which allows for 1,500,625
    unique codes, which really should be enough for anyone. '''

    length = 4
    # all upper-case letters + digits 1-9 (no 0 vs O confusion)
    chars = string.uppercase + string.digits[1:]
    # 4 chars => 35 ** 4 = 1500625 (should be enough for anyone)
    return get_random_string(length=length, allowed_chars=chars)


def all_arguments_optional(ntcls):
    ''' Takes a namedtuple derivative and makes all of the arguments optional.
    '''

    ntcls.__new__.__defaults__ = (
        (None,) * len(ntcls._fields)
    )

    return ntcls


def lazy(function, *args, **kwargs):
    ''' Produces a callable so that functions can be lazily evaluated in
    templates.

    Arguments:

        function (callable): The function to call at evaluation time.

        args: Positional arguments, passed directly to ``function``.

        kwargs: Keyword arguments, passed directly to ``function``.

    Return:

        callable: A callable that will evaluate a call to ``function`` with
            the specified arguments.

    '''

    NOT_EVALUATED = object()
    retval = [NOT_EVALUATED]

    def evaluate():
        if retval[0] is NOT_EVALUATED:
            retval[0] = function(*args, **kwargs)
        return retval[0]

    return evaluate
