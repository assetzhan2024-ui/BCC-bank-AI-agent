class ValidatorError(Exception):
    """Expected, user-facing validator error."""


class DocumentError(ValidatorError):
    """The source document cannot be read or has no usable text."""


class LLMError(ValidatorError):
    """The language-model request or response is invalid."""


class FatalLLMError(LLMError):
    """A request error that retrying cannot fix (bad key, unknown model, no quota).

    The pipeline stops immediately instead of spending more requests.
    """


class QuotaExceededError(FatalLLMError):
    """The daily request quota of the Gemini project is used up."""
