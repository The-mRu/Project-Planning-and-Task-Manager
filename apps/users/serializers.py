# App imports
from apps import subscriptions
from apps.users.models import Profile, OTPVerification, User
from apps.users.utils import OTPHandler
from apps.subscriptions.serializers import SubscriptionSerializer
# Django imports
import pyotp
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError, ObjectDoesNotExist
# Third-party imports
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import UntypedToken


# Custom Token Serializer
class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom serializer to add additional claims in the JWT token.
    """
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['email'] = user.email
        token['role'] = user.role
        return token

# User Registration Serializer
class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for registering a new user with email verification.
    """
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password2', 'first_name', 'last_name')

    def validate(self, attrs):
        """
        Validate that the two provided passwords match.
        """
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def create(self, validated_data):
        """
        Create a new user with email verification and inactive status.
        """
        email = validated_data.pop('email')
        validated_data.pop('password2')

        # Create user with pending email for verification
        user = User.objects.create_user(
            email=email,
            pending_email=email,
            **validated_data
        )
        user.is_active = False  # Set user as inactive until email verification
        user.save()

        # Create profile
        Profile.objects.create(user=user)
        # Generate OTP for email verification
        secret = pyotp.random_base32()
        OTPVerification.objects.create(
            user=user,
            email=email,
            otp_secret=secret,
            purpose='REGISTRATION'
        )
        return user


# User Login Serializer
class UserLoginSerializer(serializers.Serializer):
    """
    Serializer for user login.
    """
    username = serializers.CharField()
    password = serializers.CharField()

class UserLogoutSerializer(serializers.Serializer):
    """
    Serializer for user logout.
    """
    pass

# User Serializer
class UserSerializer(serializers.ModelSerializer):
    """
    Serializer to display user details.
    """
    plan = serializers.CharField(source='subscription.plan.name', read_only=True)
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'email_verified', 'plan')
        read_only_fields = ('email','username',)
        
# User Serializer for listview
class CustomUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username']
# User Serializer for create,update,delete view
class DetailedUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'last_login']

# Profile Serializer
class ProfileSerializer(serializers.ModelSerializer):
    """
    Serializer to handle user profile updates, including nested user updates and email changes.
    """
    user = UserSerializer()  # Nested User Serializer
    pending_email = serializers.EmailField(write_only=True, required=False)
    first_name = serializers.CharField(source='user.first_name', required=False)
    last_name = serializers.CharField(source='user.last_name', required=False)

    class Meta:
        model = Profile
        fields = (
            'user', 'address', 'city', 'country', 'date_of_birth','first_name','last_name',
            'profile_picture', 'phone_number', 'pending_email', 'owned_projects_count', 'participated_projects_count'
        )

    def update(self, instance, validated_data):
        """
        Update profile and handle nested user updates and email change if necessary.
        """
        # Extract and process nested user data
        user_data = validated_data.pop('user', {})
        print(user_data)
        user = instance.user

        for field, value in user_data.items():
            # Avoid updating read-only fields like 'email' or 'username'
            if field in ['email', 'username', 'role', 'email_verified', 'subscription', 'is_active', 'is_staff', 'is_superuser']:
                continue
            setattr(user, field, value)
        user.save()

        # Handle pending email change if provided
        pending_email = validated_data.pop('pending_email', None)
        if pending_email:
            self.handle_email_change(user, pending_email)

        # Update profile fields
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()

        return instance

    def handle_email_change(self, user, pending_email):
        """
        Set pending email and mark it as unverified.
        """
        user.pending_email = pending_email
        user.email_verified = False
        user.save()


# Change Password Serializer
class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for changing user password.
    """
    old_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True, required=True)

    def validate_old_password(self, value):
        """
        Validate the old password.
        """
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value

    def validate(self, data):
        """
        Validate that new_password and confirm_password match.
        """
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "New passwords do not match."})
        return data

    def save(self, **kwargs):
        """
        Save the new password for the user.
        """
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()


# Password Reset Request Serializer
class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Serializer to request a password reset.
    """
    email = serializers.EmailField()

    def validate_email(self, value):
        """
        Ensure that the provided email exists.
        """
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("No user found with this email.")
        return value


# Password Reset Confirm Serializer
class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Serializer to confirm password reset with a token.
    """
    reset_token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        """
        Validate the reset token and new password.
        """
        reset_token = attrs['reset_token']
        new_password = attrs['new_password']

        # Validate the new password
        try:
            validate_password(new_password)
        except ValidationError as e:
            raise serializers.ValidationError({"new_password": e.messages})

        try:
            payload = UntypedToken(reset_token)
            user_id = payload.get('user_id')
            user = User.objects.get(id=user_id)
        except Exception:
            raise serializers.ValidationError("Invalid or expired reset token.")

        attrs['user'] = user
        attrs['new_password'] = new_password
        return attrs

    def save(self, **kwargs):
        """
        Update the user's password.
        """
        user = self.validated_data['user']
        new_password = self.validated_data['new_password']
        user.set_password(new_password)
        user.save()


# OTP Send Serializer
class OtpSendSerializer(serializers.Serializer):
    """
    Serializer to send OTP for various purposes.
    """
    email = serializers.EmailField(required=True)
    purpose = serializers.ChoiceField(choices=['REGISTRATION', 'EMAIL_CHANGE', 'PASSWORD_RESET'], required=True)

    def validate_email(self, value):
        """
        Validate the email based on the purpose.
        """
        purpose = self.initial_data.get('purpose')

        if purpose == 'REGISTRATION':
            user = User.objects.filter(pending_email=value).first()
            if not user:
                raise serializers.ValidationError("No pending registration found for this email.")
            if User.objects.filter(email=value, is_active=True).exists():
                raise serializers.ValidationError("Email is already registered and verified.")

        elif purpose == 'PASSWORD_RESET':
            if not User.objects.filter(email=value, is_active=True).exists():
                raise serializers.ValidationError("No active user found with this email.")

        elif purpose == 'EMAIL_CHANGE':
            user = self.context.get('request').user
            if not user.is_authenticated:
                raise serializers.ValidationError("Authentication required for email change.")
            if User.objects.filter(email=value, is_active=True).exists():
                raise serializers.ValidationError("This email is already in use.")

        return value

    def create(self, validated_data):
        """
        Send OTP for the specified purpose.
        """
        email = validated_data['email']
        purpose = validated_data['purpose']

        user = User.objects.get(pending_email=email) if purpose == 'REGISTRATION' else User.objects.get(email=email)
        otp_handler = OTPHandler(user=user, email=email, purpose=purpose)
        result = otp_handler.send_otp()

        if not result.get("status"):
            raise serializers.ValidationError({"error": result.get("error", "Failed to send OTP")})

        return {"message": f"OTP sent to {email} for {purpose.lower().replace('_', ' ')}."}


# OTP Verification Serializer
class OtpVerificationSerializer(serializers.Serializer):
    """
    Serializer to verify OTP.
    """
    email = serializers.EmailField()
    otp = serializers.CharField()
    purpose = serializers.ChoiceField(choices=['REGISTRATION', 'EMAIL_CHANGE', 'PASSWORD_RESET'])

    def validate(self, attrs):
        """
        Validate the OTP for the specified purpose.
        """
        email = attrs['email']
        purpose = attrs['purpose']

        try:
            if purpose == 'REGISTRATION' or purpose == 'EMAIL_CHANGE':
                try:
                    user = User.objects.get(pending_email=email)
                except ObjectDoesNotExist:
                    raise serializers.ValidationError({"email": "No pending registration found for this email."})
            elif purpose == 'PASSWORD_RESET':
                user = User.objects.get(email=email)
            otp_handler = OTPHandler(user, email, purpose)
            result, message = otp_handler.verify(attrs['otp'])

            if not result:
                raise serializers.ValidationError({"otp": message})
            attrs['otp_handler'] = otp_handler
            attrs['otp_obj'] = otp_handler.otp_obj
            attrs['user'] = user
            return attrs

        except ObjectDoesNotExist:
            raise serializers.ValidationError({"email": "No user found with this email."})
