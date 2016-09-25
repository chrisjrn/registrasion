import string
import sys

from django.utils.crypto import get_random_string


def generate_access_code():
    ''' Generates an access code for users' payments as well as their
    fulfilment code for check-in.
    The access code will 4 characters long, which allows for 1,500,625
    unique codes, which really should be enough for anyone. '''

    length = 6
    # all upper-case letters + digits 1-9 (no 0 vs O confusion)
    chars = string.uppercase + string.digits[1:]
    # 6 chars => 35 ** 6 = 1838265625 (should be enough for anyone)
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


def get_object_from_name(name):
    ''' Returns the named object.

    Arguments:
        name (str): A string of form `package.subpackage.etc.module.property`.
            This function will import `package.subpackage.etc.module` and
            return `property` from that module.

    '''

    dot = name.rindex(".")
    mod_name, property_name = name[:dot], name[dot + 1:]
    __import__(mod_name)
    return getattr(sys.modules[mod_name], property_name)
