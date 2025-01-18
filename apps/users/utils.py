# App Imports
from apps.users.models import OTPVerification
from core.services.mail_service import EmailService
# Django Imports
import pyotp
from django.utils.timezone import now, timedelta
from django.core.exceptions import ObjectDoesNotExist
# Third-Party Imports
from rest_framework_simplejwt.tokens import RefreshToken
        
class OTPHandler:
    """
    Handler class to generate, verify, and process OTPs for different purposes (e.g., registration, email change).
    """
    def __init__(self, user, email, purpose):
        """
        Initializes the OTP handler for the given user, email, and purpose.
        Args:
            user (User): The user associated with the OTP.
            email (str): The email address to send OTP to.
            purpose (str): The purpose of the OTP (e.g., registration, email change).
        """
        self.user = user
        self.email = email
        self.purpose = purpose
        self.otp_obj = None
        self.email_service = EmailService()

    def generate(self):
        """
        Generate a new OTP and create or update the OTPVerification record.
        Returns:
            str: The generated OTP code.
        Raises:
            Exception: If there is an error while generating the OTP.
        """
        try:
            # Create or update the OTP record in the database
            otp_record, created = OTPVerification.objects.update_or_create(
                email=self.email,
                purpose=self.purpose,
                user=self.user,
                defaults={
                    "otp_secret": pyotp.random_base32(),  # Generate a random OTP secret
                    "created_at": now(),
                    "attempt_count": 0
                }
            )
            self.otp_obj = otp_record
            # Create a TOTP (Time-based One-Time Password) object with a 5-minute expiry
            totp = pyotp.TOTP(otp_record.otp_secret, interval=300)
            return totp.now()

        except Exception as e:
            raise Exception(f"Error while generating OTP: {str(e)}")

    def send_otp(self):
        """
        Generate the OTP and send it via email.
        """
        otp = self.generate()
        self.email_service.send_otp_email(otp, self.email)

    def verify(self, otp):
        """
        Verify the provided OTP.
        Args:
            otp (str): The OTP code to verify.
        Returns:
            tuple: A tuple containing a boolean indicating success and a message.
        """
        try:
            # Fetch OTP record based on email and purpose
            otp_record = OTPVerification.objects.get(email=self.email, purpose=self.purpose)
            self.otp_obj = otp_record
        except ObjectDoesNotExist:
            return False, "No pending verification found."

        # Check if the OTP has expired (older than 5 minutes)
        if otp_record.created_at < now() - timedelta(minutes=5):
            return False, "OTP has expired."

        # Check if maximum attempts have been reached
        if otp_record.attempt_count >= 5:
            return False, "Maximum OTP attempts reached. Please request a new OTP."

        # Verify the OTP code using TOTP
        totp = pyotp.TOTP(otp_record.otp_secret, interval=300)
        if not totp.verify(otp):
            otp_record.attempt_count += 1  # Increment attempt count
            otp_record.save()
            return False, "Invalid OTP."
        return True, "OTP is valid."

    def process_verification(self):
        """
        Process the verification based on the OTP's purpose (e.g., registration, email change).
        Returns:
            dict: A dictionary containing a message and any tokens (if applicable).
        Raises:
            ValueError: If the OTP object is None and verification cannot proceed.
        """
        if not self.otp_obj:
            raise ValueError("OTP object is None. Verification cannot be processed.")

        user = self.otp_obj.user
        tokens = None
        # Handle different OTP purposes
        if self.purpose == 'REGISTRATION':
            user.email_verified = True
            user.is_active = True
            user.email = self.otp_obj.email
            user.pending_email = None
            user.save()
            # Generate tokens for auto-login
            refresh = RefreshToken.for_user(user)
            tokens = {
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'username': user.username,
                'email': user.email,
                'role': user.role
            }
        elif self.purpose == 'EMAIL_CHANGE':
            user.email = self.otp_obj.email
            user.pending_email = None
            user.email_verified = True
            user.save()
        elif self.purpose in ['PASSWORD_RESET', 'LOGIN']:
            # Generate reset token for password reset or login verification
            reset_token = RefreshToken.for_user(user)
            tokens = {
                "message": "OTP verified successfully.",
                "reset_token": str(reset_token.access_token)
            }
        else:
            return {'message': 'Invalid OTP purpose.'}
        # Delete the used OTP record
        self.otp_obj.delete()
        return tokens
