# Local imports
from apps.users import views
# Django imports
from django.urls import path
# Third party imports
from rest_framework_simplejwt.views import TokenRefreshView


urlpatterns = [
    # Authentication endpoints
    path('register/', views.UserRegistrationView.as_view(), name='register'),
    path('login/', views.UserLoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    
    # Token endpoints
    path('token/', views.MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Profile endpoints
    path('profile/', views.ProfileView.as_view(), name='profile'),
    
    # Password management endpoints
    path('password/change/', views.ChangePasswordView.as_view(), name='change_password'),
    path('password/reset/', views.PasswordResetRequestView.as_view(), name='password_reset_request'),
    path('password/reset/confirm/', views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    
    # OTP verification endpoints
    path('otp/send/', views.SendOTPView.as_view(), name='send_otp'),
    path('otp/verify/', views.VerifyOTPView.as_view(), name='verify_otp'),
]
