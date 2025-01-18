# local imports
from apps.notifications.models import Notification, NotificationPreference
from apps.notifications.serializers import (
    NotificationListSerializer,
    NotificationDetailSerializer,
    NotificationPreferenceSerializer
)
from apps.notifications.filters import NotificationFilter
# third-party imports
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from rest_framework import generics, permissions, status, filters
from rest_framework.response import Response


class NotificationListView(generics.ListAPIView):
    """
    API view to list notifications for the authenticated user.
    Supports filtering and ordering of notifications.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationListSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = NotificationFilter
    ordering_fields = ['created_at', 'priority']
    ordering = ['-created_at']

    def get_queryset(self):
        """
        Return notifications for the authenticated user only.
        """
        return Notification.objects.filter(recipient=self.request.user)

    @extend_schema(
        summary="List Notifications",
        parameters=[
            OpenApiParameter(name='is_read', type=bool, description='Filter by read status'),
            OpenApiParameter(name='notification_type', type=str, description='Filter by notification type'),
            OpenApiParameter(name='priority', type=str, description='Filter by priority'),
            OpenApiParameter(name='ordering', type=str, description='Order by field (e.g. created_at, -priority)'),
        ],
        responses={
            200: NotificationListSerializer(many=True),
        }
    )
    def list(self, request, *args, **kwargs):
        """
        List notifications based on GET request with filtering and ordering.
        """
        notifications = super().list(request, *args, **kwargs)
        return Response({
            "message": "Notifications fetched successfully.",
            "code": status.HTTP_200_OK,
            "data": notifications.data
        }, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Mark Notifications as Read",
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'ids': {
                        'type': 'array',
                        'items': {'type': 'integer'},
                        'description': 'List of notification IDs to mark as read. If empty, all unread notifications will be marked as read.',
                    }
                },
                'example': {'ids': [1, 2, 3]}
            }
        },
        responses={
            200: {
                "message": "Notifications marked as read successfully.",
                "code": 200,
                "data": {"marked_count": 3}
            }
        }
    )
    def post(self, request, *args, **kwargs):
        """
        Handle POST request to mark notifications as read.
        """
        ids = request.data.get('ids', [])
        if ids:
            queryset = Notification.objects.filter(id__in=ids, recipient=request.user)
        else:
            # Mark all unread notifications as read
            queryset = Notification.objects.filter(is_read=False, recipient=request.user)
        
        marked_count = queryset.update(is_read=True)
        
        return Response({
            "message": f"{marked_count} notification(s) marked as read.",
            "code": status.HTTP_200_OK,
            "data": {"marked_count": marked_count}
        }, status=status.HTTP_200_OK)


class NotificationDetailView(generics.RetrieveUpdateAPIView):
    """
    API view to retrieve and update a specific notification.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationDetailSerializer

    def get_queryset(self):
        """
        Ensure users can only access their own notifications.
        """
        return Notification.objects.filter(recipient=self.request.user)

    @extend_schema(
        summary="Retrieve Notification Details",
        responses={
            200: NotificationDetailSerializer,
        }
    )
    def get(self, request, *args, **kwargs):
        """
        Retrieve details of a specific notification.
        """
        notification = super().get(request, *args, **kwargs)
        return Response({
            "message": "Notification details retrieved successfully.",
            "code": status.HTTP_200_OK,
            "data": notification.data
        }, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Update Notification",
        request=NotificationDetailSerializer,
        responses={
            200: NotificationDetailSerializer,
        }
    )
    def put(self, request, *args, **kwargs):
        """
        Update a notification (e.g., mark as read).
        """
        notification = super().put(request, *args, **kwargs)
        return Response({
            "message": "Notification updated successfully.",
            "code": status.HTTP_200_OK,
            "data": notification.data
        }, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Partially Update Notification",
        request=NotificationDetailSerializer,
        responses={
            200: NotificationDetailSerializer,
        }
    )
    def patch(self, request, *args, **kwargs):
        """
        Partially update a notification.
        """
        notification = super().patch(request, *args, **kwargs)
        return Response({
            "message": "Notification partially updated successfully.",
            "code": status.HTTP_200_OK,
            "data": notification.data
        }, status=status.HTTP_200_OK)


class NotificationPreferenceView(generics.RetrieveUpdateAPIView):
    """
    API view to retrieve and update notification preferences for the authenticated user.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationPreferenceSerializer

    def get_object(self):
        """
        Get or create notification preferences for the authenticated user.
        """
        return NotificationPreference.objects.get_or_create(user=self.request.user)[0]

    @extend_schema(
        summary="Get Notification Preferences",
        responses={
            200: NotificationPreferenceSerializer,
        }
    )
    def get(self, request, *args, **kwargs):
        """
        Retrieve notification preferences for the authenticated user.
        """
        preferences = super().get(request, *args, **kwargs)
        return Response({
            "message": "Notification preferences retrieved successfully.",
            "code": status.HTTP_200_OK,
            "data": preferences.data
        }, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Update Notification Preferences",
        request=NotificationPreferenceSerializer,
        responses={
            200: NotificationPreferenceSerializer,
        }
    )
    def put(self, request, *args, **kwargs):
        """
        Update all notification preferences for the authenticated user.
        """
        preferences = super().put(request, *args, **kwargs)
        return Response({
            "message": "Notification preferences updated successfully.",
            "code": status.HTTP_200_OK,
            "data": preferences.data
        }, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Partially Update Notification Preferences",
        request=NotificationPreferenceSerializer,
        responses={
            200: NotificationPreferenceSerializer,
        }
    )
    def patch(self, request, *args, **kwargs):
        """
        Partially update notification preferences for the authenticated user.
        """
        preferences = super().patch(request, *args, **kwargs)
        return Response({
            "message": "Notification preferences partially updated successfully.",
            "code": status.HTTP_200_OK,
            "data": preferences.data
        }, status=status.HTTP_200_OK)
