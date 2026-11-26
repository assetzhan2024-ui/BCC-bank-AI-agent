class ValidatorError(Exception):
    """Expected, user-facing validator error."""


class DocumentError(ValidatorError):
    """The source document cannot be read or has no usable text."""


class LLMError(ValidatorError):
    """The language-model request or response is invalid."""
