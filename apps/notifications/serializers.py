from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from .models import Notification, NotificationPreference

User = get_user_model()

class UserMinimalSerializer(serializers.ModelSerializer):
    """
    Minimal serializer for User model, used for nested representations.
    """
    class Meta:
        model = User
        fields = ['id', 'username']

class ContentTypeSerializer(serializers.ModelSerializer):
    """
    Serializer for ContentType model, used for generic relations.
    """
    class Meta:
        model = ContentType
        fields = ['id', 'app_label', 'model']

class NotificationListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing notifications with essential information.
    Used in list views to provide a concise representation of notifications.
    """
    class Meta:
        model = Notification
        fields = ['id', 'message', 'is_read', 'created_at', 'notification_type', 'priority']
        read_only_fields = ['id', 'created_at']

class NotificationDetailSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for Notification model.
    Includes all fields and related information for a comprehensive view of a notification.
    """
    recipient = UserMinimalSerializer(read_only=True)
    content_type = ContentTypeSerializer(read_only=True)

    class Meta:
        model = Notification
        fields = ['id', 'recipient', 'message', 'is_read', 'created_at', 
                    'notification_type', 'status', 'priority', 'content_type', 'object_id']
        read_only_fields = ['id', 'created_at', 'status', 'recipient', 'content_type', 'object_id']

    def to_representation(self, instance):
        """
        Add a content_object_url to the serialized data for easy navigation to related object.
        """
        representation = super().to_representation(instance)
        representation['content_object_url'] = instance.get_content_object_url()
        return representation

class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """
    Serializer for NotificationPreference model.
    Handles user preferences for different types of notifications.
    """
    class Meta:
        model = NotificationPreference
        fields = ['user', 'preferences']
        read_only_fields = ['user']

    def to_representation(self, instance):
        """
        Customize the representation to only include non-null preferences.
        """
        representation = super().to_representation(instance)
        representation['preferences'] = {
            key: value for key, value in representation['preferences'].items()
            if value is not None  # Only include non-null preferences
        }
        return representation

