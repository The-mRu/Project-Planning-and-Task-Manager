from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from apps.notifications.models import Notification

RETRY_DELAY = 60  # seconds
def send_real_time_notification(user, message, notification_type, content_type, object_id):
    """
    Sends a real-time WebSocket notification and saves it to the database.
    """
    channel_layer = get_channel_layer()

    notification = Notification.objects.create(
        recipient=user,
        message=message['body'],
        notification_type=notification_type,
        content_type_id=content_type,
        object_id=object_id,
        status="pending"
    )

    try:
        async_to_sync(channel_layer.group_send)(
            f'user_{user.id}',
            {
                'type': 'send_notification',
                'data': {
                    'title': message['title'],
                    'body': message['body'],
                    'url': message.get('url'),
                }
            }
        )
        notification.status = 'delivered'
    except Exception:
        notification.status = 'failed'
        from core.tasks import retry_failed_notifications
        retry_failed_notifications.apply_async((notification.id,), countdown=RETRY_DELAY)
    finally:
        notification.save()