import jwt
from channels.auth import AuthMiddlewareStack
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth import get_user_model

User = get_user_model()

@database_sync_to_async
def get_user_from_token(token):
    """
    Retrieves the user associated with the provided JWT token.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user = User.objects.get(id=payload["user_id"])
        return user
    except (jwt.ExpiredSignatureError, jwt.DecodeError, User.DoesNotExist):
        return AnonymousUser()

class JWTAuthMiddleware:
    """
    Custom middleware for authenticating WebSocket connections using JWT.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        headers = dict(scope["headers"])
        token = None

        # Extract the token from the query string or headers
        if b"authorization" in headers:
            auth_header = headers[b"authorization"].decode("utf-8")
            if auth_header.startswith("Bearer "):
                token = auth_header.split("Bearer ")[1]
        elif "token" in scope["query_string"].decode():
            query_params = dict(qc.split('=') for qc in scope["query_string"].decode().split("&"))
            token = query_params.get("token")

        if token:
            scope["user"] = await get_user_from_token(token)
        else:
            scope["user"] = AnonymousUser()

        return await self.inner(scope, receive, send)

def JWTAuthMiddlewareStack(inner):
    """
    Wraps the default AuthMiddlewareStack with JWT authentication.
    """
    return JWTAuthMiddleware(AuthMiddlewareStack(inner))
