from django.core.exceptions import ValidationError


class CartValidationError(ValidationError):
    pass
