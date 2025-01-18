from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from datetime import timedelta

class User(AbstractUser):
    """
    Custom user model extending Django's AbstractUser to include additional fields 
    like role, subscription type, email verification, and OTP support.
    """
    email = models.EmailField(unique=True)  # Unique email address
    role_choices = [
        ('admin', 'Admin'),  # System-wide admin
        ('user', 'User')     # Regular user
    ]
    role = models.CharField(max_length=10, choices=role_choices, default='user')
    
    # Add a boolean field for staff to identify internal staff or superusers
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    last_seen = models.DateTimeField(null=True, blank=True)  # Last seen timestamp
    date_joined = models.DateTimeField(auto_now_add=True)  # Date when user joined
    last_login = models.DateTimeField(null=True, blank=True)  # Date of the last login
    email_verified = models.BooleanField(default=False)  # Whether the user's email is verified
    pending_email = models.EmailField(null=True, blank=True, unique=True)  # Pending email before verification

    # Many-to-many relationships with Group and Permission
    groups = models.ManyToManyField('auth.Group', related_name='custom_user_groups', blank=True)
    user_permissions = models.ManyToManyField('auth.Permission', related_name='custom_user_permissions', blank=True)

    def __str__(self):
        return f"{self.username} ({self.role})"


class Profile(models.Model):
    """
    Profile model to store additional user information like address, 
    phone number, profile picture, and project participation details.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    
    # Personal Information
    address = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True,default='default.jpg')
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    
    # For Owners (or members part of specific projects)
    owned_projects_count = models.PositiveIntegerField(default=0)  # For Owners
    participated_projects_count = models.PositiveIntegerField(default=0)  # For Members

    def __str__(self):
        return f"Profile of {self.user.username}"
    def update_project_counts(self):
        """
        Updates the project counts for the user's profile.
        This should be called whenever projects are added or removed.
        """
        self.owned_projects_count = self.user.owned_projects.count()
        self.participated_projects_count = self.user.project_memberships.count()
        self.save()


# class UserMetadata(models.Model):
#     """
#     UserMetadata model is created to store user metadata such as username, email,
#     and profile picture for faster access and retrieval.
#     """
#     user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='metadata')
#     username = models.CharField(max_length=150)
#     email = models.EmailField()
#     profile_picture = models.ImageField(upload_to='profile_pictures/', null=True, blank=True) 

#     def sync_from_user(self):
#         """
#         Synchronize user metadata from the associated User model.
#         """
#         self.username = self.user.username
#         self.email = self.user.email
#         self.profile_picture = self.user.profile.profile_picture.url if self.user.profile.profile_picture else None
        
#     def save(self, *args, **kwargs):
#         if not self.pk:
#             self.sync_from_user()  # Sync when creating
#         super().save(*args, **kwargs)

#     def __str__(self):
#         return f"Metadata for {self.user.username}"


class OTPVerification(models.Model):
    """
    OTPVerification model stores OTP details for actions such as registration, 
    email change, and password reset, including OTP secrets, attempt count, 
    and verification status.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    email = models.EmailField()
    otp_secret = models.CharField(max_length=100)  # Store base32 secret
    purpose = models.CharField(max_length=20, choices=[
        ('REGISTRATION', 'Registration'),
        ('EMAIL_CHANGE', 'Email Change'),
        ('PASSWORD_RESET', 'Password Reset')
    ])
    attempt_count = models.PositiveSmallIntegerField(default=1)  # Number of attempts made
    last_attempt = models.DateTimeField(auto_now=True)  # Timestamp of last attempt
    created_at = models.DateTimeField(auto_now_add=True)  # Timestamp when OTP was created
    is_verified = models.BooleanField(default=False)  # Whether OTP was verified

    class Meta:
        indexes = [
            models.Index(fields=['user', 'purpose']),  # Index for user and OTP purpose
            models.Index(fields=['created_at']),  # Index for creation date
        ]

    def increment_attempt(self):
        """
        Increment the OTP attempt count and update the last attempt timestamp.
        """
        self.attempt_count += 1
        self.last_attempt = timezone.now()
        self.save()

    @classmethod
    def cleanup_expired_otps(cls):
        """
        Clean up OTPs that are older than 2 hours.
        """
        expiry_time = timezone.now() - timedelta(hours=2)
        cls.objects.filter(created_at__lt=expiry_time).delete()
