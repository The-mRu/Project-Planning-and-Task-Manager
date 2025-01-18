from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

User = get_user_model()

class AdminActionLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='admin_actions')
    action = models.CharField(max_length=255)
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True  # Allow null for bulk actions
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)  # Allow null for non-object actions
    content_object = GenericForeignKey('content_type', 'object_id')
    changes = models.JSONField(default=dict, blank=True)  # Default to an empty dict
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        object_ref = f"{self.content_type} - {self.object_id}" if self.content_type else "No object"
        return f"{self.user.username} - {self.action} - {object_ref}"
