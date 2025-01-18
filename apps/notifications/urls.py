from django.urls import path
from apps.notifications.views import (
    NotificationListView,
    NotificationDetailView,
    NotificationPreferenceView,
)

urlpatterns = [
    # Base url : /api/v1/notifications/
    # List all notifications and if post request is made, mark all/specific notifications as read
    path('', NotificationListView.as_view(), name='notification-list'),
    # Retrieve, update, or delete a specific notification
    path('<int:pk>/', NotificationDetailView.as_view(), name='notification-detail'),
    # Update notification preferences for the authenticated user
    path('preferences/', NotificationPreferenceView.as_view(), name='notification-preference'),
]
