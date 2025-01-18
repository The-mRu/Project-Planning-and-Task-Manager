# App imports
from apps.users.models import Profile, User
from apps.users.utils import OTPHandler
from apps.users.serializers import (
    ChangePasswordSerializer,MyTokenObtainPairSerializer,OtpVerificationSerializer,
    ProfileSerializer,PasswordResetConfirmSerializer,PasswordResetRequestSerializer,
    UserLoginSerializer,UserRegistrationSerializer,OtpSendSerializer, UserLogoutSerializer
)

# Django imports
from django.contrib.auth import authenticate, update_session_auth_hash
from django.utils import timezone
# Third party imports
import logging
from rest_framework import status, serializers
from rest_framework.generics import CreateAPIView, RetrieveUpdateAPIView, GenericAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample, OpenApiResponse

# Configure logging
logger = logging.getLogger(__name__)


@extend_schema(
    description="Custom token view that uses MyTokenObtainPairSerializer",
    responses={200: OpenApiResponse(description="Returns access and refresh tokens")}
)
class MyTokenObtainPairView(TokenObtainPairView):
    """Custom token view that uses MyTokenObtainPairSerializer"""
    serializer_class = MyTokenObtainPairSerializer


@extend_schema(
    description="Handles OTP sending for various purposes like registration or password reset",
    request=OtpSendSerializer,
    responses={
        200: OpenApiResponse(description="OTP sent successfully"),
        400: OpenApiResponse(description="Invalid request data")
    }
)
class SendOTPView(APIView):
    """
    Handles OTP sending for various purposes like registration or password reset.
    """
    permission_classes = (AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = OtpSendSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            # Retrieve the success message from the serializer
            success_message = serializer.save()  # Calls the create method and returns the message
            return Response(success_message, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    description="Handles OTP verification for various purposes",
    request=OtpVerificationSerializer,
    responses={
        200: OpenApiResponse(description="OTP verified successfully, returns tokens"),
        400: OpenApiResponse(description="Invalid or expired OTP")
    }
)
class VerifyOTPView(APIView):
    """
    Handles OTP verification for various purposes.
    """
    permission_classes = (AllowAny,)

    def post(self, request):
        try:
            serializer = OtpVerificationSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            otp_handler = serializer.validated_data['otp_handler']
            otp_obj = serializer.validated_data['otp_obj']

            if not otp_obj:
                return Response({"error": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)

            tokens = otp_handler.process_verification()
            return Response(tokens, status=status.HTTP_200_OK)

        except serializers.ValidationError as e:
            return Response({"error": e.detail}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"OTP verification failed: {str(e)}")
            return Response(
                {"error": "OTP verification failed. Please try again."},
                status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema(
    description="Handles user registration and sends verification OTP",
    request=UserRegistrationSerializer,
    responses={
        201: OpenApiResponse(description="Registration successful, OTP sent"),
        200: OpenApiResponse(description="User exists but email not verified, OTP resent"),
        400: OpenApiResponse(description="Invalid registration data")
    }
)
class UserRegistrationView(CreateAPIView):
    """
    Handles user registration and sends verification OTP.
    """
    serializer_class = UserRegistrationSerializer
    permission_classes = (AllowAny,)

    def create(self, request, *args, **kwargs):
        username = request.data.get('username')
        email = request.data.get('email')

        # Check for an existing user with pending verification
        existing_user = User.objects.filter(
            username=username,
            pending_email=email,
            is_active=False
        ).first()

        if existing_user:
            # Resend OTP for existing pending user
            otp_handler = OTPHandler(existing_user, email, 'REGISTRATION')
            otp_handler.send_otp()
            return Response({
                "message": "User exists but email not verified. OTP resent.",
                "email": email
            }, status=status.HTTP_200_OK)

        # Create a new user
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Send OTP for email verification
        otp_handler = OTPHandler(user, user.pending_email, 'REGISTRATION')
        otp_handler.send_otp()

        return Response({
            "message": "Registration successful. Please verify your email.",
            "email": user.pending_email
        }, status=status.HTTP_201_CREATED)


@extend_schema(
    description="Handles user login and returns JWT tokens",
    request=UserLoginSerializer,
    responses={
        200: OpenApiResponse(description="Login successful, returns tokens"),
        401: OpenApiResponse(description="Invalid credentials"),
        403: OpenApiResponse(description="Email not verified")
    }
)
class UserLoginView(APIView):
    """
    Handles user login and returns JWT tokens.
    """
    permission_classes = (AllowAny,)
    
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = authenticate(
            username=serializer.validated_data['username'],
            password=serializer.validated_data['password']
        )
        
        if user is None:
            return Response({
                'error': 'Invalid credentials'
            }, status=status.HTTP_401_UNAUTHORIZED)
            
        if not user.email_verified:
            return Response({
                'error': 'Please verify your email first'
            }, status=status.HTTP_403_FORBIDDEN)
        if not user.is_active:
            return Response({
                'error': 'Your account is inactive'
            }, status=status.HTTP_403_FORBIDDEN)
        refresh = RefreshToken.for_user(user)
        user.last_login = timezone.now()
        user.save()
        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'username': user.username,
            'email': user.email,
            'role': user.role
        })


@extend_schema(
    description="Handles user logout by blacklisting the refresh token",
    responses={
        205: OpenApiResponse(description="Logged out successfully"),
        400: OpenApiResponse(description="Invalid token")
    }
)
class LogoutView(APIView):
    """
    Handles user logout by blacklisting the refresh token.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserLogoutSerializer
    def post(self, request):
        try:
            # Get the refresh token from the request data
            refresh_token = request.data["refresh"]
            # Instantiate a RefreshToken object with the refresh token
            token = RefreshToken(refresh_token)
            # Add the token to the blacklist
            token.blacklist()
            return Response({"message": "Logged out successfully"}, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({"error": "Invalid token"}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    description="Handles user profile retrieval and updates",
    methods=['GET', 'PUT', 'PATCH'],
    responses={
        200: ProfileSerializer,
        403: OpenApiResponse(description="Permission denied"),
        404: OpenApiResponse(description="Profile not found")
    }
)
class ProfileView(RetrieveUpdateAPIView):
    """
    Handles user profile retrieval and updates, ensuring only the authenticated user can access and update their profile.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ProfileSerializer

    def get_object(self):
        """
        Return the profile of the authenticated user.
        This ensures only the logged-in user can access their own profile.
        """
        return self.request.user.profile

    def update(self, request, *args, **kwargs):
        """
        Handle profile updates for the authenticated user only.
        """
        # Ensure the request is for the logged-in user's profile
        instance = request.user.profile
        partial = kwargs.pop('partial', True)  # Allow partial updates
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        try:
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)

            response_data = {
                "message": "Profile updated successfully",
                "profile": serializer.data,
                "email_status": "verified"
            }

            # Handle OTP sending if email is being updated
            if 'pending_email' in request.data:
                self.trigger_email_change_otp(request.user, request.data['pending_email'])
                response_data.update({
                    "email_status": "pending_verification",
                    "email_change": "Email verification OTP has been sent. Please verify your new email address."
                })

            # Log the update
            logger.info(f"User {request.user.username} updated their profile.")
            return Response(response_data)

        except serializers.ValidationError as e:
            logger.error(f"Validation error updating profile for user {request.user.username}: {str(e)}")
            return Response({"error": e.detail}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error updating profile for user {request.user.username}: {str(e)}")
            return Response(
                {"error": "An unexpected error occurred while updating your profile. Please try again."},
                status=status.HTTP_400_BAD_REQUEST
            )

    def trigger_email_change_otp(self, user, pending_email):
        """
        Trigger the OTP process for email change verification.
        """
        try:
            otp_handler = OTPHandler(user, pending_email, 'EMAIL_CHANGE')
            otp_handler.send_otp()
            logger.info(f"OTP sent to {pending_email} for user {user.username}.")
        except Exception as e:
            logger.error(f"Error sending OTP for user {user.username}: {str(e)}")
            raise serializers.ValidationError({"pending_email": "Failed to send verification OTP. Please try again."})

    def perform_update(self, serializer):
        """
        Perform the actual update of the profile instance.
        """
        serializer.save()


@extend_schema(
    description="An endpoint for changing the user password",
    request=ChangePasswordSerializer,
    responses={
        200: OpenApiResponse(description="Password updated successfully"),
        400: OpenApiResponse(description="Invalid password data")
    }
)
class ChangePasswordView(APIView):
    """
    An endpoint for changing the user password.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            # Save the new password
            serializer.save()

            # Update the session to keep the user logged in
            update_session_auth_hash(request, request.user)

            # Optional: Invalidate all other tokens and issue a new token
            try:
                # Blacklist old refresh tokens if using Simple JWT
                if hasattr(request.user, 'auth_token'):  # Token-based auth
                    request.user.auth_token.delete()

                # If using JWT, generate a new token
                refresh = RefreshToken.for_user(request.user)

                return Response({
                    'message': 'Password updated successfully.',
                    'access': str(refresh.access_token),
                    'refresh': str(refresh)
                }, status=status.HTTP_200_OK)

            except Exception as e:
                return Response({
                    'message': 'Password updated, but error refreshing token.',
                    'error': str(e)
                }, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    description="Handles password reset requests by sending OTP",
    request=PasswordResetRequestSerializer,
    responses={
        200: OpenApiResponse(description="Password reset OTP sent successfully"),
        404: OpenApiResponse(description="User not found")
    }
)
class PasswordResetRequestView(APIView):
    """
    Handles password reset requests by sending OTP.
    """
    permission_classes = (AllowAny,)

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                return Response({"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND)

            otp_handler = OTPHandler(user, email, 'PASSWORD_RESET')
            otp_handler.send_otp()

            return Response({"detail": "Password reset OTP sent successfully"}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    description="Handles password reset confirmation and token generation",
    request=PasswordResetConfirmSerializer,
    responses={
        200: OpenApiResponse(description="Password reset successful, returns new tokens"),
        400: OpenApiResponse(description="Invalid reset data")
    }
)
class PasswordResetConfirmView(GenericAPIView):
    """
    Handles password reset confirmation and token generation.
    """
    serializer_class = PasswordResetConfirmSerializer
    permission_classes = (AllowAny,)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        serializer.save()
        refresh = RefreshToken.for_user(user)
        tokens = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }
        return Response(
            {
                "message": "Password has been reset successfully.",
                "tokens": tokens
            },
            status=status.HTTP_200_OK
        )