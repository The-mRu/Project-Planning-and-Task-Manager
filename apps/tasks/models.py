import re
from django.utils import timezone
from django.db import models
from django.contrib.auth import get_user_model
from apps.projects.models import Project
from django.db.models import F
from markdown import markdown
from bleach import Cleaner
from bleach.linkifier import LinkifyFilter
User = get_user_model()

class Task(models.Model):
    STATUS_CHOICES = (
        ("not_started", "Not Started"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("overdue", "Overdue"),
    )

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    name = models.CharField(max_length=255)
    description = models.TextField(default="", blank=True)  # Avoid null handling inconsistencies
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    due_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="not_started"
    )
    assigned_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="tasks_creator"
    )
    total_assignees = models.PositiveIntegerField(default=0)
    need_approval = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,  # Use SET_NULL to retain task even if the approver is deleted
        related_name="tasks_approver",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "tasks"
        ordering = ["-due_date", "status"]
        indexes = [  # Indexes for optimizing frequent queries
            models.Index(fields=["due_date"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return self.name


class TaskAssignment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="assignments")
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="task_assignments"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "task_assignments"
        unique_together = ("task", "user")  # Ensures each user-task pair is unique
        indexes = [  # Indexes for optimizing assignment queries
            models.Index(fields=["task"]),
            models.Index(fields=["user"]),
        ]

    def __str__(self):
        return f"{self.user.username} assigned to {self.task.name}"


# =================#
# Comment Features #
# =================#

class Comment(models.Model):
    task = models.ForeignKey('Task', on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='task_comments')
    content = models.TextField(max_length=1000)  # Limit content to 1000 characters
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    mentioned_users = models.ManyToManyField(User, related_name='mentions', blank=True)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='replies')
    reply_count = models.PositiveIntegerField(default=0)
    mention_count = models.PositiveIntegerField(default=0)

    # Markdown and XSS protection settings
    ALLOWED_TAGS = [
        'p', 'div', 'span', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li',
        'strong', 'em', 'a', 'code', 'pre', 'blockquote', 'hr', 'br', 'table',
        'thead', 'tbody', 'tr', 'th', 'td'
    ]
    
    ALLOWED_ATTRIBUTES = {
        'a': ['href', 'title', 'target'],
        'code': ['class'],
        'pre': ['class'],
        'span': ['class'],
        'div': ['class'],
        'p': ['class'],
        'img': ['src', 'alt', 'title', 'width', 'height'],
    }

    ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['task']),
            models.Index(fields=['author']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        if self.parent:
            return f"Reply by {self.author.username} to comment {self.parent.id} on Task {self.task.id}"
        return f"Comment by {self.author.username} on Task {self.task.id}"

    def get_rendered_content(self):
        """Render markdown content with XSS protection"""
        # First pass: Convert markdown to HTML
        html = markdown(self.content, extensions=['fenced_code', 'tables'])
        
        # Second pass: Clean and sanitize HTML
        cleaner = Cleaner(
            tags=self.ALLOWED_TAGS,
            attributes=self.ALLOWED_ATTRIBUTES,
            protocols=self.ALLOWED_PROTOCOLS,
            filters=[LinkifyFilter]
        )
        
        return cleaner.clean(html)
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            self.process_mentions()
            if self.parent:
                Comment.objects.filter(pk=self.parent.pk).update(reply_count=F('reply_count') + 1)

    def process_mentions(self):
        mentioned_usernames = {
            word[1:] for word in self.content.split() if word.startswith('@') and len(word) > 1
        }
        if mentioned_usernames:
            mentioned_users = User.objects.filter(username__in=mentioned_usernames)
            self.mentioned_users.set(mentioned_users)
            self.mention_count = mentioned_users.count()
            self.save(update_fields=['mention_count'])

    def delete(self, *args, **kwargs):
        if self.parent:
            Comment.objects.filter(pk=self.parent.pk).update(reply_count=F('reply_count') - 1)
        super().delete(*args, **kwargs)


# ======================#
# Status Change Request #
# ======================#
class StatusChangeRequest(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected")
    ]

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="status_change_requests")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="status_change_requests")
    request_time = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, related_name="status_change_approvals", null=True, blank=True
    )
    resolution_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "status_change_requests"
        indexes = [
            models.Index(fields=["task"]),
            models.Index(fields=["status"]),
            models.Index(fields=["user"]),
            models.Index(fields=["request_time"]),
        ]
        ordering = ['-request_time']

    def __str__(self):
        return f"Request from {self.user.username} for task '{self.task.name}' status change"

    def approve(self, approved_by):
        self.status = "approved"
        self.approved_by = approved_by
        self.resolution_time = timezone.now()
        self.save()

    def reject(self, rejected_by):
        self.status = "rejected"
        self.approved_by = rejected_by
        self.resolution_time = timezone.now()
        self.save()
