from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404


class ForId(object):
    ''' Mixin class that gives you new classmethods: for_id for_id_or_404.
    These let you retrieve an instance of the class by specifying the model ID.

    Your subclass must define __MODEL__ as a class attribute. This will be the
    model class that we wrap. There must also be a constructor that takes a
    single argument: the instance of the model that we are controlling. '''

    @classmethod
    def for_id(cls, id_):
        id_ = int(id_)
        obj = cls.__MODEL__.objects.get(pk=id_)
        return cls(obj)

    @classmethod
    def for_id_or_404(cls, id_):
        try:
            return cls.for_id(id_)
        except ObjectDoesNotExist:
            return Http404
