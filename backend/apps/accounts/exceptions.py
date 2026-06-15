"""Consistent JSON error envelope for all API errors.

Shape: {"error": {"code", "message", "details"}} with the correct HTTP status.
"""
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler


class InvalidCredentials(APIException):
    """401 for bad login / expired session.

    A plain APIException (not AuthenticationFailed) so DRF keeps the 401 even on
    views with no authentication classes — it only downgrades 401->403 for
    NotAuthenticated/AuthenticationFailed.
    """

    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Incorrect email or password."
    default_code = "invalid_credentials"


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None  # let Django produce a 500 (logged); never leak internals

    data = response.data
    code = getattr(exc, "default_code", "error")
    if isinstance(data, dict) and "detail" in data and len(data) == 1:
        message, details = str(data["detail"]), None
    else:
        message, details = "Request failed.", data

    response.data = {"error": {"code": code, "message": message, "details": details}}
    return response
