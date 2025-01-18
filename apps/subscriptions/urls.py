from django.urls import path
from apps.subscriptions import views

# URL patterns define the routing for the subscription-related APIs
urlpatterns = [
    # Lists all available subscription plans
    path('plans/', views.SubscriptionPlanListView.as_view(), name='subscription-plan-list'),

    # Retrieves details of the current user's subscription
    path('me/', views.SubscriptionDetailView.as_view(), name='subscription-detail'),

    # Upgrades the current user's subscription plan
    path('upgrade/', views.UpgradeSubscriptionView.as_view(), name='upgrade-subscription'),

    # Cancels the current user's subscription
    path('cancel/', views.CancelSubscriptionView.as_view(), name='cancel-subscription'),

    # Lists all payments made by the current user
    path('payments/', views.PaymentListView.as_view(), name='payment-list'),

    # Creates a Stripe checkout session for upgrading subscriptions
    path('checkout-session/', views.CreateCheckoutSessionView.as_view(), name='create-checkout-session'),

    # Handles Stripe webhook events for subscription and payment updates
    path('stripe/webhook/', views.StripeWebhookView.as_view(), name='stripe-webhook'),
]
