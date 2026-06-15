"""Auth API views. Thin: validate input, delegate to services, shape the response."""
from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .cookies import clear_auth_cookies, set_auth_cookies
from .serializers import CurrentUserSerializer, LoginSerializer


class LoginView(APIView):
    """POST email + password -> sets httpOnly JWT cookies, returns the profile."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.authenticate_user(**serializer.validated_data)
        access, refresh = services.issue_tokens(user)

        body = CurrentUserSerializer(user).data
        response = Response(body, status=status.HTTP_200_OK)
        return set_auth_cookies(response, access=access, refresh=refresh)


class LogoutView(APIView):
    """Clears the auth cookies. Safe to call even when not authenticated."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, _request):
        response = Response(status=status.HTTP_204_NO_CONTENT)
        return clear_auth_cookies(response)


class RefreshView(APIView):
    """Rotates the access cookie using the refresh cookie."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        refresh = request.COOKIES.get(settings.AUTH_COOKIE_REFRESH)
        if not refresh:
            return clear_auth_cookies(Response(status=status.HTTP_401_UNAUTHORIZED))
        access, new_refresh = services.rotate_access_token(refresh)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        return set_auth_cookies(response, access=access, refresh=new_refresh)


class MeView(APIView):
    """Returns the currently authenticated user's profile."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(CurrentUserSerializer(request.user).data)
