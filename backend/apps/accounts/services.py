"""Business logic for authentication. Views stay thin and delegate here."""
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken

from .exceptions import InvalidCredentials


def authenticate_user(*, email: str, password: str):
    """Return the user for valid credentials, else raise InvalidCredentials (401)."""
    user = authenticate(username=email.lower(), password=password)
    if user is None:
        raise InvalidCredentials("Incorrect email or password.")
    if not user.is_active:
        raise InvalidCredentials("This account is disabled.")
    return user


def issue_tokens(user) -> tuple[str, str]:
    """Mint (access, refresh) JWTs for a user."""
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token), str(refresh)


def rotate_access_token(refresh_token: str) -> tuple[str, str]:
    """Validate a refresh token and return fresh (access, refresh) strings."""
    try:
        refresh = RefreshToken(refresh_token)
    except Exception as exc:  # token errors -> 401, not 500
        raise InvalidCredentials("Session expired. Please sign in again.") from exc
    access = str(refresh.access_token)
    # ROTATE_REFRESH_TOKENS is on; return the (possibly rotated) refresh too.
    return access, str(refresh)
