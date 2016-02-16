from django.conf import settings
from django.contrib.auth import logout
from django.core.exceptions import ObjectDoesNotExist
from requests.exceptions import RequestException, HTTPError
import logging

logger = logging.getLogger(__name__)


class AgaveTokenRefreshMiddleware(object):

    def process_request(self, request):
        if request.path != '/logout/' and request.user.is_authenticated():
            session_key = getattr(settings, 'AGAVE_TOKEN_SESSION_ID')
            if session_key in request.session:
                try:
                    token = request.user.agave_oauth
                    if token and token.expired:
                        try:
                            token.refresh()
                            request.session[session_key] = \
                                token.token
                        except HTTPError as e:
                            logger.exception('Failed to refresh token for user=%s. '
                                             'Forcing logout: %s' %
                                             (request.user.username, e.response))
                            logout(request)
                except ObjectDoesNotExist:
                    logger.warn('Agave Token missing for user=%s. Forcing logout...' %
                                request.user.username)
                    logout(request)
                except RequestException:
                    logger.exception('Agave Token refresh failed for user=%s. '
                                     'Forcing logout...' %
                                     request.user.username)
                    logout(request)