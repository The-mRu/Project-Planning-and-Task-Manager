import django_filters
from apps.notifications.models import Notification
from apps.notifications import models
class NotificationFilter(django_filters.FilterSet):
    """
    FilterSet for Notification model.
    Provides filtering options for notifications based on various fields.
    """
    is_read = django_filters.BooleanFilter(help_text="Filter by read status (true/false)")
    notification_type = django_filters.CharFilter(lookup_expr='iexact', help_text="Filter by exact notification type (case-insensitive)")
    priority = django_filters.ChoiceFilter(choices=models.PRIORITY_CHOICES, help_text="Filter by notification priority")
    created_at = django_filters.DateTimeFromToRangeFilter(help_text="Filter by creation date range")

    class Meta:
        model = Notification
        fields = ['is_read', 'notification_type', 'priority', 'created_at']

