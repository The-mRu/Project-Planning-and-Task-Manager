from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.notifications.models import NotificationPreference, NOTIFICATION_TYPES

User = get_user_model()

class Command(BaseCommand):
    help = "Populates all users' notification preferences with all set to True"

    def handle(self, *args, **kwargs):
        # Fetch all users
        users = User.objects.all()

        # Loop through all users and set their preferences
        for user in users:
            # Check if NotificationPreference exists for the user, otherwise create it
            preference, created = NotificationPreference.objects.get_or_create(user=user)

            # Set all preferences to True
            default_preferences = {k: True for k, _ in NOTIFICATION_TYPES}
            preference.preferences = default_preferences
            preference.save()

            # Output to indicate success
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created preferences for {user.username}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"Updated preferences for {user.username}"))

        self.stdout.write(self.style.SUCCESS("All users' notification preferences have been populated."))
