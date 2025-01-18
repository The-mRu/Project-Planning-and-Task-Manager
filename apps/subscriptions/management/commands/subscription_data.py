import stripe
from django.core.management.base import BaseCommand
from apps.subscriptions.models import SubscriptionPlan
from django.conf import settings
class Command(BaseCommand):
    help = "Populate subscription plans (Basic, Pro, Enterprise) into the database."

    def handle(self, *args, **kwargs):
        # Set your Stripe secret key
        stripe.api_key = settings.STRIPE_SECRET_KEY

        # Define subscription plan details
        plans = [
            {
                "name": "basic",
                "description": "Basic plan with limited features.",
                "price": 0.00,
                "duration_days": 30,
                "max_projects": 2,
                "max_members_per_project": 5,
            },
            {
                "name": "pro",
                "description": "Pro plan with enhanced features.",
                "price": 4.99,
                "duration_days": 30,
                "max_projects": 10,
                "max_members_per_project": 30,
            },
            {
                "name": "enterprise",
                "description": "Enterprise plan with unlimited access.",
                "price": 49.99,
                "duration_days": 30,
                "max_projects": -1,
                "max_members_per_project": -1,
            },
        ]

        for plan in plans:
            # Fetch or create the Stripe product
            stripe_product = stripe.Product.create(
                name=plan["name"].capitalize(),
                description=plan["description"],
            )

            # Fetch or create the Stripe price
            stripe_price = stripe.Price.create(
                unit_amount=int(plan["price"] * 100),  # Stripe uses the smallest currency unit
                currency="usd",
                recurring={"interval": "month"},
                product=stripe_product.id,
            )

            # Save the plan in the database
            subscription_plan, created = SubscriptionPlan.objects.update_or_create(
                name=plan["name"],
                defaults={
                    "description": plan["description"],
                    "price": plan["price"],
                    "duration_days": plan["duration_days"],
                    "stripe_price_id": stripe_price.id,
                    "max_projects": plan["max_projects"],
                    "max_members_per_project": plan["max_members_per_project"],
                },
            )
            if created:
                self.stdout.write(f"Created plan: {subscription_plan.name}")
            else:
                self.stdout.write(f"Updated plan: {subscription_plan.name}")
