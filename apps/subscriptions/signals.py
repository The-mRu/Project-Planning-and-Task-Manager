from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from .models import SubscriptionPlan, Subscription

User = get_user_model()

@receiver(post_save, sender=User)
def create_user_subscription(sender, instance, created, **kwargs):
    """
    Signal to automatically assign a basic subscription to a newly created user.

    Args:
        sender (class): The model class that sent the signal (in this case, User).
        instance (User): The actual instance of the user that was saved.
        created (bool): A boolean indicating whether a new record was created (True) 
                        or an existing one was updated (False).
        **kwargs: Additional keyword arguments.

    Functionality:
        - When a new user is created (`created=True`), the function retrieves the 'basic' subscription plan.
        - Calculates the subscription end date based on the plan's duration.
        - Creates a new Subscription object for the user with the 'basic' plan.
    """
    if created:
        # Retrieve the 'basic' subscription plan
        basic_plan = SubscriptionPlan.objects.get(name='basic')
        
        # Calculate the subscription end date
        end_date = timezone.now() + timedelta(days=basic_plan.duration_days)
        
        # Create a new Subscription object with the 'basic' plan for the user
        Subscription.objects.create(
            user=instance,
            plan=basic_plan,
            start_date=timezone.now(),
            end_date=end_date
        )
