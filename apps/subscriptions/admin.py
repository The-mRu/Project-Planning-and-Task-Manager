from django.contrib import admin
from apps.subscriptions.models import Subscription, SubscriptionPlan, Payment

admin.site.register(Subscription)
admin.site.register(SubscriptionPlan)
admin.site.register(Payment)

