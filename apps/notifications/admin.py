from django.contrib import admin
from apps.notifications.models import Notification, NotificationPreference
# Register your models here.

admin.site.register(Notification)
admin.site.register(NotificationPreference)
