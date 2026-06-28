from rest_framework.permissions import BasePermission


class HasValidIngestToken(BasePermission):
    """
    Requires that StaticBearerTokenAuthentication succeeded for this
    request. Checked via request.successful_authenticator rather than
    request.user.is_authenticated, since the bearer scheme used here
    has no underlying Django User.
    """

    message = "A valid Bearer token is required for this endpoint."

    def has_permission(self, request) -> bool:
        from rates.authentication import StaticBearerTokenAuthentication

        return isinstance(request.successful_authenticator, StaticBearerTokenAuthentication)
