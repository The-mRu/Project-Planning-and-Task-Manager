import logging
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta

logger = logging.getLogger('project_planner')

from rest_framework_simplejwt.authentication import JWTAuthentication

class LastSeenMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.jwt_authentication = JWTAuthentication()

    def __call__(self, request):
        try:
            auth_result = self.jwt_authentication.authenticate(request)
            if auth_result:
                user, token = auth_result
                request.user = user
                
                cache_key = f'user_last_seen_{user.id}'
                last_seen = cache.get(cache_key)

                if not last_seen or (timezone.now() - last_seen) > timedelta(minutes=5):
                    cache.set(cache_key, timezone.now(), 60 * 60)
        except Exception as e:
            logger.debug(f"JWT Authentication error: {str(e)}")

        response = self.get_response(request)
        return response
