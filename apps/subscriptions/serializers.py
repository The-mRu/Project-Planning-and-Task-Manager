# Local imports
from apps.subscriptions.models import SubscriptionPlan, Subscription, Payment
# Third-party imports
from rest_framework import serializers

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    """
    Serializer for the SubscriptionPlan model.
    Converts the SubscriptionPlan model instances into JSON and vice versa.
    """
    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'name', 'description', 'price', 'duration_days', 'max_projects', 'max_members_per_project']


class SubscriptionSerializer(serializers.ModelSerializer):
    """
    Serializer for the Subscription model.
    Includes details about the plan using a nested SubscriptionPlanSerializer.
    """
    plan = SubscriptionPlanSerializer(read_only=True)  # Nested serializer for plan details

    class Meta:
        model = Subscription
        fields = ['id', 'user', 'plan', 'start_date', 'end_date', 'is_active']
        read_only_fields = ['user', 'start_date', 'end_date', 'is_active']  # Fields managed internally


class PaymentSerializer(serializers.ModelSerializer):
    """
    Serializer for the Payment model.
    Handles serialization of payment records for subscriptions.
    """
    class Meta:
        model = Payment
        fields = ['id', 'subscription', 'amount', 'date']
        read_only_fields = ['subscription', 'date']  # These fields are set automatically
