"""Consistent JSON error envelope for all API errors.

Shape: {"error": {"code", "message", "details"}} with the correct HTTP status.
"""
import logging

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class InvalidCredentials(APIException):
    """401 for bad login / expired session.

    A plain APIException (not AuthenticationFailed) so DRF keeps the 401 even on
    views with no authentication classes — it only downgrades 401->403 for
    NotAuthenticated/AuthenticationFailed.
    """

    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Incorrect email or password."
    default_code = "invalid_credentials"


def _first_message(data):
    """Pull the first human-readable string out of a DRF error structure
    (which may be a str, list, or nested dict of field errors)."""
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        for item in data:
            msg = _first_message(item)
            if msg:
                return msg
    if isinstance(data, dict):
        for value in data.values():
            msg = _first_message(value)
            if msg:
                return msg
    return None


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        # DRF only builds a Response for Http404/PermissionDenied/APIException —
        # anything else (a storage/network error, a third-party library
        # exception, a bug) would otherwise propagate to Django's default handler,
        # which renders an HTML page. The frontend always expects JSON, so that
        # HTML gets swallowed by a failed `res.json()` parse and surfaces as a
        # blank "Upload failed."/"Something went wrong." with no real reason.
        # Log the real exception here (with the view for context) and still
        # return the same JSON envelope so callers always get a clear message.
        logger.exception("Unhandled exception in %s", context.get("view"), exc_info=exc)
        return Response(
            {"error": {"code": "server_error", "message": "Something went wrong. Please try again.", "details": None}},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    data = response.data
    code = getattr(exc, "default_code", "error")
    if isinstance(data, dict) and "detail" in data and len(data) == 1:
        message, details = str(data["detail"]), None
    else:
        # Surface the first field error so the UI shows a real reason, not a
        # generic "request failed". Keep the full map in details.
        message = _first_message(data) or "Request failed."
        details = data

    response.data = {"error": {"code": code, "message": message, "details": details}}
    return response
