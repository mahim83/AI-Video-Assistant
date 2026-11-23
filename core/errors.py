class UserFacingError(Exception):
    """
    A refusal or failure whose message is written for the user and is safe to
    show as is. Any other exception is logged and replaced by a generic message,
    because its text can contain file paths or provider responses.
    """


class GuardrailError(UserFacingError):
    """A request refused by a guardrail: bad input, a limit, or a busy server."""


class QuotaExceeded(GuardrailError):
    """A per-user daily limit or rate limit was reached."""


class AccessDenied(UserFacingError):
    """A signed-in identity that may not use the app."""
