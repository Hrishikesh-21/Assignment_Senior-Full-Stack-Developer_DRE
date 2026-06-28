"""
Bearer token authentication for POST /rates/ingest.

The spec calls for "Bearer Token authentication using Django REST
Framework. No external authentication providers." DRF's built-in
TokenAuthentication sends `Authorization: Token <key>` rather than
`Authorization: Bearer <key>`, so this class implements the Bearer
scheme directly against a single static token from settings
(INGESTION_API_TOKEN) rather than DRF's per-user Token model.

This is a deliberate scope simplification for a take-home / portfolio
project: a real production system would issue per-client tokens via
DRF's TokenAuthentication + a proper client/API-key model, with
rotation and revocation. That tradeoff is documented in DECISIONS.md.
"""
from django.conf import settings
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed


class StaticBearerTokenAuthentication(BaseAuthentication):
    keyword = b"bearer"

    def authenticate(self, request):
        auth_header = get_authorization_header(request).split()

        if not auth_header or auth_header[0].lower() != self.keyword:
            return None  # No Bearer header present — let other auth classes (or AllowAny) handle it.

        if len(auth_header) != 2:
            raise AuthenticationFailed("Invalid Authorization header format. Expected: Bearer <token>.")

        token = auth_header[1].decode("utf-8")
        if token != settings.INGESTION_API_TOKEN:
            raise AuthenticationFailed("Invalid or expired token.")

        # DRF requires authenticate() to return a (user, auth) tuple.
        # There's no real user model for this single-token scheme, so
        # we return None for the user and rely on permission classes
        # checking `request.successful_authenticator` rather than
        # `request.user.is_authenticated`.
        return (None, token)
