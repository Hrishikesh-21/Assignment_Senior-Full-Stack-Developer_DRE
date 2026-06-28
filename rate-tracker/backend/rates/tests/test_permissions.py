from unittest.mock import MagicMock

from rates.authentication import StaticBearerTokenAuthentication
from rates.permissions import HasValidIngestToken


class TestHasValidIngestToken:
    def test_grants_permission_when_bearer_auth_succeeded(self):
        request = MagicMock()
        request.successful_authenticator = StaticBearerTokenAuthentication()

        assert HasValidIngestToken().has_permission(request) is True

    def test_denies_permission_when_no_authenticator_matched(self):
        request = MagicMock()
        request.successful_authenticator = None

        assert HasValidIngestToken().has_permission(request) is False

    def test_denies_permission_when_different_authenticator_matched(self):
        request = MagicMock()
        request.successful_authenticator = object()  # some other auth class

        assert HasValidIngestToken().has_permission(request) is False
