from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.validators import MinValueValidator

from apps.notifications.models import STATUS_CHOICES

User = get_user_model()

class SubscriptionPlan(models.Model):
    """
    Represents a subscription plan with various tiers (Basic, Pro, Enterprise).
    
    Attributes:
        - name: The name of the plan, chosen from predefined types.
        - description: A detailed explanation of the plan (optional).
        - price: The cost of the plan.
        - duration_days: The validity period of the plan in days.
        - stripe_price_id: The unique identifier for Stripe integration.
        - max_projects: The maximum number of projects allowed (-1 for unlimited).
        - max_members_per_project: The maximum number of members allowed per project (-1 for unlimited).
    """
    PLAN_TYPES = (
        ('basic', 'Basic'),
        ('pro', 'Pro'),
        ('enterprise', 'Enterprise')
    )

    name = models.CharField(max_length=100, choices=PLAN_TYPES, unique=True)
    description = models.TextField(null=True, blank=True)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    duration_days = models.PositiveIntegerField(default=30)
    stripe_price_id = models.CharField(max_length=100, unique=True)
    max_projects = models.IntegerField(validators=[MinValueValidator(-1)])  # -1 represents unlimited
    max_members_per_project = models.IntegerField(validators=[MinValueValidator(-1)])  # -1 represents unlimited

    def __str__(self):
        """
        Returns a user-friendly string representation of the plan.
        """
        return self.name

class Subscription(models.Model):
    """
    Represents a subscription for a user tied to a specific subscription plan.
    
    Attributes:
        - user: The user owning the subscription (One-to-One relationship).
        - plan: The plan associated with this subscription.
        - start_date: The starting date of the subscription.
        - end_date: The expiration date of the subscription.
        - is_active: A boolean indicating whether the subscription is active.
        - stripe_subscription_id: The unique identifier for Stripe subscription.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT, related_name='subscriptions', default=1)
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    stripe_subscription_id = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        """
        Returns a user-friendly string representation of the subscription.
        """
        return f"{self.user.username}'s {self.plan.name} subscription"

    def is_valid(self):
        """
        Checks if the subscription is currently valid.
        Returns:
            bool: True if the subscription is active and the end date is in the future.
        """
        return self.is_active and self.end_date > timezone.now()
    
    def revert_to_basic(self):
        """
        Reverts the subscription to the basic plan.
        """
        self.plan = SubscriptionPlan.objects.get(name='basic')
        self.start_date = timezone.now()
        self.end_date = timezone.now() + timezone.timedelta(days=self.plan.duration_days)
        self.save()
class Payment(models.Model):
    """
    Represents a payment made by a user for their subscription.
    
    Attributes:
        - subscription: The subscription associated with this payment.
        - amount: The payment amount.
        - date: The timestamp of when the payment was made.
        - stripe_payment_intent_id: The unique identifier for the Stripe payment intent.
    """
    STATUS_CHOICES = (
        ('succeeded', 'Succeeded'),
        ('failed', 'Failed'),
        ('pending', 'Pending'),
    )
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=6, decimal_places=2)
    date = models.DateTimeField(default=timezone.now)
    stripe_payment_intent_id = models.CharField(max_length=100)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=50, default='card')
    def __str__(self):
        """
        Returns a user-friendly string representation of the payment.
        """
        return f"Payment of ${self.amount} for {self.subscription}"
