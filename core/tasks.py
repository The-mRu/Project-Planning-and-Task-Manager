from celery import shared_task
from project_planner.logging import INFO, project_logger
from apps.projects.models import Project, ProjectMembership
from apps.tasks.models import Task, TaskAssignment
from apps.notifications.utils import send_real_time_notification
from apps.notifications.models import Notification, NotificationPreference
from django.core.mail import EmailMultiAlternatives
from django.core.cache import cache
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.utils.timezone import now
from django.utils.html import strip_tags
from datetime import timedelta
from django.urls import reverse
User = get_user_model()


# Task to send emails
@shared_task
def send_email(subject, message, recipient, content_type="text/plain"):
    """
    Task to send HTML emails using Django's EmailMultiAlternatives.
    Args:
        subject (str): Email subject.
        message (str): HTML content of the email.
        recipient (str): Recipient email address.
    """

    # Create an EmailMultiAlternatives object
    email = EmailMultiAlternatives(
        subject=subject,
        body='',  # Plain-text body
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )
    email.attach_alternative(message, content_type)
    # Send the email
    email.send()

@shared_task
def retry_failed_notifications(notification_id):
    """
    Retry sending a failed notification.
    """
    try:
        notification = Notification.objects.get(id=notification_id, status="failed" or "pending")
        notification.resend_notification()
    except Notification.DoesNotExist:
        pass
    
@shared_task
def prune_notifications():
    """
    Keep only the latest 50 notifications per user and delete the rest.
    Create a interval task on admin panel to run this task every 7 days.
    """
    users = Notification.objects.values_list('user_id', flat=True).distinct()  # Get all unique user IDs
    for user_id in users:
        notifications = Notification.objects.filter(user_id=user_id).order_by('-created_at')
        if notifications.count() > 50:  # Check if the user has more than 50 notifications
            # Delete notifications older than the 50th most recent
            notifications_to_delete = notifications[50:]
            notifications_to_delete.delete()
            
@shared_task
def check_overdue_items():
    current_time = now()
    base_url = settings.FRONTEND_URL

    # Check tasks nearing overdue
    tasks_to_notify = Task.objects.filter(
        due_date__isnull = False,
        due_date__lte=current_time + timedelta(hours=24),
        status__in=["not_started", "in_progress"]
    ).prefetch_related('assignments__user')
    for task in tasks_to_notify:
        task_members = task.assignments.all()
        for assignment in task_members:
            send_real_time_notification(
                user=assignment.user,
                message={
                    "title": "Task Nearing Due Date",
                    "body": f"The task '{task.name}' is nearing its due date.",
                    "url": f"{base_url}{reverse('task-retrieve-update-destroy', kwargs={'pk': task.id})}"
                },
                notification_type="task",
                content_type=ContentType.objects.get_for_model(Task).id,
                object_id=task.id
            )

    # Mark overdue tasks
    Task.objects.filter(
        due_date__isnull = False,
        due_date__lt=current_time,
        status__in=["not_started", "in_progress"]
    ).update(status="overdue")

    # Check projects nearing overdue
    projects_to_notify = Project.objects.filter(
        due_date__isnull = False,
        due_date__lte=current_time + timedelta(hours=24),
        status__in=["not_started", "in_progress"]
    ).prefetch_related('memberships__user')
    
    for project in projects_to_notify:
        project_members = project.memberships.all()
        for membership in project_members:
            send_real_time_notification(
                user=membership.user,
                message={
                    "title": "Project Nearing Due Date",
                    "body": f"The project '{project.name}' is nearing its due date.",
                    "url": f"{base_url}{reverse('project-retrieve-update-destroy', kwargs={'pk': project.id})}"
                },
                notification_type="project",
                content_type=ContentType.objects.get_for_model(Project).id,
                object_id=project.id
            )

    # Mark overdue projects
    Project.objects.filter(
        due_date__isnull = False,
        due_date__lt=current_time,
        status__in=["not_started", "in_progress"]
    ).update(status="overdue")
    
@shared_task
def update_last_seen():
    updated_count = 0
    for user in User.objects.all():
        cache_key = f'user_last_seen_{user.id}'
        last_seen = cache.get(cache_key)
        if last_seen:
            user.last_seen = last_seen
            user.save(update_fields=['last_seen'])
            cache.delete(cache_key)
            updated_count += 1
    
    project_logger.log(INFO, f"Updated last_seen for {updated_count} users")