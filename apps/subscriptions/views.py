# Local imports
from apps.subscriptions.models import SubscriptionPlan, Subscription, Payment
from apps.subscriptions.serializers import SubscriptionPlanSerializer, SubscriptionSerializer, PaymentSerializer
# Django imports
from django.conf import settings
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from django.shortcuts import get_object_or_404
# Third-party imports
from datetime import timedelta
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
import stripe

# Initialize Stripe with the secret key from settings
stripe.api_key = settings.STRIPE_SECRET_KEY

class SubscriptionPlanListView(generics.ListAPIView):
    """
    List view for SubscriptionPlan model.
    """
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer

    @extend_schema(
        summary="List all subscription plans",
        description="Retrieve a list of all available subscription plans.",
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)


class SubscriptionDetailView(generics.RetrieveAPIView):
    """
    Retrieve the subscription details for the current user.
    """
    serializer_class = SubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Get current user's subscription details",
        description="Retrieve the details of the currently active subscription for the authenticated user.",
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_object(self):
        """
        Retrieve the subscription object for the current user.
        """
        return get_object_or_404(Subscription, user=self.request.user)


class UpgradeSubscriptionView(APIView):
    """
    API view for upgrading a user's subscription plan.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Upgrade subscription",
        description="Upgrade the authenticated user's subscription plan to a higher-tier plan.",
        parameters=[
            OpenApiParameter(name="plan_id", description="ID of the new subscription plan", required=True, type=int)
        ],
        responses={
            200: "Checkout session URL for upgrading subscription.",
            400: "Error response indicating why the upgrade is not allowed."
        },
    )
    def post(self, request):
        plan_id = request.data.get('plan_id')
        plan = get_object_or_404(SubscriptionPlan, id=plan_id)

        if plan.name == 'basic':
            return Response({"error": "Cannot upgrade to basic plan"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Get the current active subscription
            current_subscription = get_object_or_404(Subscription, user=request.user, is_active=True)

            # Ensure the upgrade is to a higher-tier plan
            if current_subscription.plan.price >= plan.price:
                return Response({"error": "Cannot downgrade plan"}, status=status.HTTP_400_BAD_REQUEST)

            # Create a Stripe checkout session
            checkout_session = stripe.checkout.Session.create(
                customer_email=request.user.email,
                payment_method_types=['card'],
                line_items=[{
                    'price': plan.stripe_price_id,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=request.build_absolute_uri(reverse('subscription-detail')),
                cancel_url=request.build_absolute_uri(reverse('subscription-detail')),
                metadata={
                    'user_id': request.user.id,
                    'plan_id': plan.id,
                }
            )
            return Response({'checkout_url': checkout_session.url}, status=status.HTTP_200_OK)

        except stripe.error.StripeError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class CancelSubscriptionView(APIView):
    """
    API view for cancelling a user's subscription.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Cancel subscription",
        description="Cancel the authenticated user's subscription and revert to the basic plan.",
        responses={
            200: "Subscription cancelled and reverted to the basic plan.",
            400: "Error response indicating why the cancellation is not allowed."
        },
    )
    def post(self, request):
        subscription = get_object_or_404(Subscription, user=request.user, is_active=True)

        if subscription.plan.name == 'basic':
            return Response({"error": "Cannot cancel basic plan"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Cancel the subscription in Stripe
            stripe.Subscription.delete(subscription.stripe_subscription_id)

            # Update the subscription to revert to the basic plan
            basic_plan = SubscriptionPlan.objects.get(name='basic')
            subscription.plan = basic_plan
            subscription.stripe_subscription_id = None
            subscription.save()

            return Response({"message": "Subscription cancelled and reverted to basic plan"}, status=status.HTTP_200_OK)

        except stripe.error.StripeError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PaymentListView(generics.ListAPIView):
    """
    List all payments made by the authenticated user.
    """
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="List user payments",
        description="Retrieve a list of all payments made by the authenticated user.",
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_queryset(self):
        """
        Filter payments to include only those belonging to the current user.
        """
        return Payment.objects.filter(subscription__user=self.request.user)


class CreateCheckoutSessionView(APIView):
    """
    API view for creating a Stripe checkout session.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Create checkout session",
        description="Generate a Stripe checkout session for the authenticated user to upgrade their subscription.",
        parameters=[
            OpenApiParameter(name="plan_id", description="ID of the subscription plan to upgrade to", required=True, type=int)
        ],
        responses={
            200: "Checkout session URL created successfully.",
            400: "Error response for invalid request."
        },
    )
    def post(self, request):
        plan_id = request.data.get('plan_id')
        plan = get_object_or_404(SubscriptionPlan, id=plan_id)

        if plan.name == 'basic':
            return Response({"error": "Cannot upgrade to basic plan"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Create Stripe checkout session
            checkout_session = stripe.checkout.Session.create(
                customer_email=request.user.email,
                payment_method_types=['card'],
                line_items=[{
                    'price': plan.stripe_price_id,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=request.build_absolute_uri(reverse('subscription-detail')),
                cancel_url=request.build_absolute_uri(reverse('subscription-detail')),
                metadata={
                    'user_id': request.user.id,
                    'plan_id': plan.id,
                }
            )
            return Response({'checkout_url': checkout_session.url}, status=status.HTTP_200_OK)

        except stripe.error.StripeError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class StripeWebhookView(APIView):
    """
    Handle Stripe webhook events.
    """
    @extend_schema(
        summary="Stripe webhook handler",
        description="Handle events sent by Stripe, such as checkout session completion.",
        responses={
            200: "Webhook processed successfully.",
            400: "Invalid webhook signature or payload."
        },
    )
    def post(self, request):
        payload = request.body
        sig_header = request.META['HTTP_STRIPE_SIGNATURE']
        event = None

        try:
            # Verify the webhook signature
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            return Response(status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.SignatureVerificationError:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        if event['type'] == 'checkout.session.completed':
            session = event['data']['object']
            user_id = session['metadata']['user_id']
            plan_id = session['metadata']['plan_id']

            user = User.objects.get(id=user_id)
            plan = SubscriptionPlan.objects.get(id=plan_id)

            # Update or create the subscription
            subscription, _ = Subscription.objects.update_or_create(
                user=user,
                defaults={
                    'plan': plan,
                    'start_date': timezone.now(),
                    'end_date': timezone.now() + timedelta(days=plan.duration_days),
                    'is_active': True,
                    'stripe_subscription_id': session['subscription']
                }
            )

            # Record payment
            Payment.objects.create(
                subscription=subscription,
                amount=plan.price,
                stripe_payment_intent_id=session['payment_intent']
            )

        return Response(status=status.HTTP_200_OK)