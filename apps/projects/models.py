import uuid
from django.db import models
from django.utils.timezone import now
from django.contrib.auth import get_user_model

User = get_user_model()


class Project(models.Model):
    """
    Represents a project with members and tasks.
    Tracks the total number of tasks, project status, and member count.
    """
    PROJECT_STATUS_CHOICES = [
        ('not_started', 'Not Started'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('on_hold', 'On Hold'),
        ('overdue', 'Overdue'),
    ]

    # Core fields
    name = models.CharField(max_length=255)  # Name of the project
    description = models.TextField(blank=True, null=True)  # Optional description
    owner = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='owned_projects'
    )  # Owner of the project
    created_at = models.DateTimeField(auto_now_add=True)  # Project creation timestamp
    updated_at = models.DateTimeField(auto_now=True)  # Last update timestamp
    # Tracking fields
    total_tasks = models.PositiveIntegerField(default=0)  # Total tasks associated with the project
    status = models.CharField(
        max_length=20, 
        choices=PROJECT_STATUS_CHOICES, 
        default='not_started'
    )  # Current status of the project
    due_date = models.DateTimeField(null=True, blank=True)  # Optional due date for the project
    total_member_count = models.PositiveIntegerField(default=1)  # Total members in the project (including the owner)
    admin_override = models.BooleanField(default=False)  # Flag to check admin override of project details (e.g., increase member count)
    def __str__(self):
        return self.name

    def update_task_counts(self):
        """
        Updates the total number of tasks in the project by counting associated tasks.
        This should be called whenever tasks are added or removed.
        """
        self.total_tasks = self.tasks.count()
        self.save()

    def update_member_count(self):
        """
        Updates the total number of members in the project by counting the memberships.
        This should be called whenever members are added or removed.
        """
        self.total_member_count = self.memberships.count()
        self.save()
    def can_create_task(self):
        """Check if tasks can be created based on project status"""
        return self.status in ['in_progress', 'overdue']

    def can_update_project(self):
        """Check if project can be updated based on status"""
        return self.status != 'completed'

    def is_read_only(self):
        """Check if project is in read-only state"""
        return self.status == 'completed'

    def can_perform_activity(self):
        """Check if project activities are allowed based on status"""
        return self.status not in ['not_started', 'on_hold', 'completed']

class ProjectMembershipQuerySet(models.QuerySet):
    """
    Custom QuerySet for ProjectMembership to optimize data fetching.
    """

    def with_related_data(self):
        """
        Optimizes fetching of related project and user data using select_related.
        Use this when you need to access related fields frequently.
        """
        return self.select_related('project', 'user')


class ProjectMembershipManager(models.Manager):
    """
    Custom Manager for ProjectMembership to provide optimized queries.
    """

    def get_queryset(self):
        """
        Overrides the default queryset to include the custom QuerySet.
        """
        return ProjectMembershipQuerySet(self.model, using=self._db)

    def with_related_data(self):
        """
        Provides an entry point to use the optimized QuerySet.
        """
        return self.get_queryset().with_related_data()


class ProjectMembership(models.Model):
    """
    Represents the membership of a user in a project.
    Tracks the user's tasks and completion statistics within the project.
    """
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('member', 'Member'),
    ]
    project = models.ForeignKey(
        Project, 
        on_delete=models.CASCADE, 
        related_name='memberships'
    )  # The project this membership is associated with
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='project_memberships'
    )  # The user who is a member of the project
    joined_at = models.DateTimeField(default=now)  # Timestamp of when the user joined the project

    # Task tracking fields
    total_tasks = models.PositiveIntegerField(default=0)  # Total tasks assigned to the user in this project
    completed_tasks = models.PositiveIntegerField(default=0)  # Total tasks completed by the user in this project
    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default='member'
    )  # Role of the user in the project
    # Custom manager
    objects = ProjectMembershipManager()

    class Meta:
        unique_together = ('project', 'user')  # Ensures a user cannot have duplicate memberships in a project

    def __str__(self):
        return f"{self.user.username} in {self.project.name}"

    def update_task_counts(self):
        """
        Updates the total and completed tasks for this user in the project.
        This should be called whenever tasks are assigned or their status changes.
        """
        self.total_tasks = self.project.tasks.filter(assignments__user=self.user).count()
        self.completed_tasks = self.project.tasks.filter(
            assignments__user=self.user, 
            status='completed'
        ).count()
        self.save()


class ProjectInvitation(models.Model):
    """
    Represents an invitation to join a project.
    Stores denormalized data to improve query performance and maintain historical accuracy.
    """
    project = models.ForeignKey(
        Project, 
        on_delete=models.CASCADE, 
        related_name='invitations'
    )
    email = models.EmailField()
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    invited_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='sent_invitations'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted = models.BooleanField(default=False)
    accepted_at = models.DateTimeField(null=True, blank=True)

    # Denormalized fields
    project_name = models.CharField(max_length=255)
    inviter_email = models.EmailField()
    inviter_name = models.CharField(max_length=255)

    class Meta:
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['email']),
            models.Index(fields=['project_name']),
            models.Index(fields=['inviter_email']),
        ]

    def __str__(self):
        return f"Invitation to {self.project_name} for {self.email}"

    def save(self, *args, **kwargs):
        if not self.pk:  # Only set these fields on creation
            self.project_name = self.project.name
            self.inviter_email = self.invited_by.email
            self.inviter_name = self.invited_by.get_full_name() or self.invited_by.username
        super().save(*args, **kwargs)

    def is_expired(self):
        return now() > self.expires_at

    def accept(self, user):
        if not self.is_expired() and not self.accepted:
            self.accepted = True
            self.accepted_at = now()
            self.save()
            
            # Create ProjectMembership for the user
            ProjectMembership.objects.create(
                project=self.project,
                user=user,
                role='member'
            )
            
            # Update project member count
            self.project.update_member_count()
            
            return True
        return False