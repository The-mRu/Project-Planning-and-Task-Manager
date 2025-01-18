import os
import time
import requests
from datetime import datetime, timedelta
from threading import Thread

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Count, F, Q, Sum, Prefetch
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter, OpenApiResponse, OpenApiExample
from rest_framework import filters, permissions, status, viewsets, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import UserRateThrottle

from apps.admins.models import AdminActionLog
from apps.admins.serializers import (
    AdminActionLogSerializer, AdminCommentCreateUpdateSerializer,
    AdminCommentDetailSerializer, AdminCommentListSerializer,
    AdminPaymentHistorySerializer, AdminProjectCreateSerializer,
    AdminProjectDetailSerializer, AdminProjectListSerializer,
    AdminProjectMembershipCreateUpdateSerializer, AdminProjectInvitationSerializer,
    AdminProjectMembershipSerializer, AdminProjectUpdateSerializer,
    AdminSubscriptionDetailSerializer, AdminSubscriptionListSerializer,
    AdminSubscriptionPlanSerializer, AdminTaskBulkAssignSerializer,
    AdminTaskBulkUnassignSerializer, AdminTaskBulkUpdateSerializer,
    AdminTaskCreateSerializer, AdminTaskDetailSerializer,
    AdminTaskListSerializer, AdminTaskStatusChangeRequestDetailSerializer,
    AdminTaskStatusChangeRequestListSerializer, AdminTaskUpdateSerializer,
    AdminUserDetailSerializer, AdminUserListSerializer,
    NotificationAdminSerializer, AdminTaskAssignmentSerializer,
)
from apps.notifications.models import Notification
from apps.projects.models import Project, ProjectMembership, ProjectInvitation
from apps.projects.views import InvitationEmailMixin
from apps.subscriptions.models import Payment, Subscription, SubscriptionPlan
from apps.tasks.models import (Comment, StatusChangeRequest, Task,
                                TaskAssignment)
from core.permissions import IsAdminUser
from core.tasks import send_email, send_real_time_notification
if settings.DEBUG:
    from project_planner.logging import DEBUG, ERROR, INFO, project_logger

User = get_user_model()


class AdminViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    throttle_classes = [UserRateThrottle]
    json_encoder = DjangoJSONEncoder
    def perform_create(self, serializer):
        instance = serializer.save()
        self.log_admin_action('create', instance, serializer.data)

    def perform_update(self, serializer):
        old_instance = self.get_object()
        old_data = self.get_serializer(old_instance).data
        instance = serializer.save()
        new_data = serializer.data
        changes = {
            field: {'old': old_data.get(field), 'new': new_data.get(field)}
            for field in new_data.keys()
            if old_data.get(field) != new_data.get(field)
        }
        self.log_admin_action('update', instance, changes)

    def perform_destroy(self, instance):
        self.log_admin_action('delete', instance, {})
        instance.delete()

    def log_admin_action(self, action, instance=None, changes=None):
        """
        Logs an administrative action to the AdminActionLog model.
        """
        user = self.request.user
        content_type = ContentType.objects.get_for_model(instance) if instance else None
        object_id = instance.id if instance else None
        if isinstance(changes, dict):
            changes = {
                k: v.isoformat() if isinstance(v, datetime) else v 
                for k, v in changes.items()
            }
        AdminActionLog.objects.create(
            user=user,
            action=action,
            content_type=content_type,
            object_id=object_id,
            changes=changes or {},
        )
@extend_schema_view(
    list=extend_schema(
        description="Retrieve a list of users with filtering, ordering, and searching capabilities."
    ),
    bulk_activate=extend_schema(
        request={
            'application/json': {
                'type': 'object',
                'properties': {'user_ids': {'type': 'array', 'items': {'type': 'integer'}}}
            }
        },
        responses={200: {'description': 'Success'}},
        description="Activate multiple users or all users."
    ),
    bulk_deactivate=extend_schema(
        request={
            'application/json': {
                'type': 'object',
                'properties': {'user_ids': {'type': 'array', 'items': {'type': 'integer'}}}
            }
        },
        responses={200: {'description': 'Success'}},
        description="Deactivate multiple users or all users, excluding admin roles."
    ),
    send_email=extend_schema(
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'user_ids': {'type': 'array', 'items': {'type': 'integer'}},
                    'subject': {'type': 'string'},
                    'message': {'type': 'string'}
                }
            }
        },
        responses={200: {'description': 'Emails sent successfully'}},
        description="Send emails to specific users or all users."
    ),
)
class UserAdminViewSet(AdminViewSet):
    """
    Admin ViewSet for managing users. Provides CRUD operations,
    bulk actions (activate/deactivate), and email sending functionalities.
    Supports filtering, searching, and ordering of user records.
    """

    # Set the base queryset with optimized related object retrieval
    queryset = User.objects.all().select_related('profile')
    # Define filters, ordering, and throttling for the API
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['is_active', 'role', 'email_verified']
    search_fields = ['username', 'email']
    ordering_fields = ['date_joined', 'last_login']
    throttle_classes = [UserRateThrottle]

    def get_serializer_class(self):
        """
        Dynamically return the appropriate serializer class based on the action.
        """
        if self.action == 'list':
            return AdminUserListSerializer
        return AdminUserDetailSerializer

    def get_queryset(self):
        """
        Retrieve and optionally cache the queryset for performance optimization.
        """
        cache_key = "users_list"
        cached_queryset = cache.get(cache_key)
        if cached_queryset is None:
            queryset = super().get_queryset()
            cache.set(cache_key, queryset, timeout=60 * 5)  # Cache for 5 minutes
            return queryset
        return cached_queryset

    @action(detail=False, methods=['post'], name='Bulk Activate Users', url_path='activate')
    def bulk_activate(self, request):
        """
        Activate multiple users in bulk or all users if 'all' is specified.
        
        - Accepts a list of user IDs or 'all'.
        - Logs admin action for audit purposes.
        """
        user_ids = request.data.get('user_ids', None)
        
        if user_ids == 'all':
            updated_count = User.objects.update(is_active=True)
            self.log_admin_action('bulk_activate_all', None, {'user_ids': 'all'})
            return Response({'status': f'All {updated_count} users activated'})

        if not user_ids:
            return Response({'error': 'No user IDs provided'}, status=status.HTTP_400_BAD_REQUEST)

        updated_count = User.objects.filter(id__in=user_ids).update(is_active=True)
        self.log_admin_action('bulk_activate', None, {'user_ids': user_ids})
        return Response({'status': f'{updated_count} users activated'})

    @action(detail=False, methods=['post'], name='Bulk Deactivate Users', url_path='deactivate')
    def bulk_deactivate(self, request):
        """
        Deactivate multiple users in bulk or all users if 'all' is specified.
        
        - Excludes admin roles from deactivation.
        - Accepts a list of user IDs or 'all'.
        - Logs admin action for audit purposes.
        """
        user_ids = request.data.get('user_ids', None)
        
        if user_ids == 'all':
            # Deactivate all users except the admin roles
            updated_count = User.objects.exclude(role='admin').update(is_active=False)
            self.log_admin_action('bulk_deactivate_all', None, {'user_ids': 'all'})
            return Response({'status': f'All {updated_count} users deactivated'})

        if not user_ids:
            return Response({'error': 'No user IDs provided'}, status=status.HTTP_400_BAD_REQUEST)
        # Deactivate the specified users except the admin roles
        updated_count = User.objects.exclude(role='admin').filter(id__in=user_ids).update(is_active=False)
        self.log_admin_action('bulk_deactivate', None, {'user_ids': user_ids})
        return Response({'status': f'{updated_count} users deactivated'})

    @action(detail=False, methods=['post'])
    def send_email(self, request):
        """
        Send emails to specific users or all users.
        
        - Requires `subject` and `message` in the request data.
        - Accepts a list of user IDs or 'all'.
        - Uses Celery for asynchronous email sending.
        - Logs admin action for audit purposes.
        """
        user_ids = request.data.get('user_ids', None)  # List of user IDs or 'all'
        subject = request.data.get('subject')
        message = request.data.get('message')

        if not subject or not message:
            return Response({'error': 'Subject and message are required'}, status=status.HTTP_400_BAD_REQUEST)

        if user_ids == 'all':  # Send to all users
            recipients = User.objects.values_list('email', flat=True)
        else:  # Send to specific users
            recipients = User.objects.filter(id__in=user_ids).values_list('email', flat=True)

        if not recipients:
            return Response({'error': 'No recipients found'}, status=status.HTTP_400_BAD_REQUEST)

        for recipient in recipients:
            send_email.delay(subject, message, recipient)  # Async email sending via Celery

        self.log_admin_action('send_email', None, {'user_ids': user_ids, 'subject': subject})
        return Response({'status': 'emails sent'})

@extend_schema_view(
    list=extend_schema(
        description="Retrieve a list of projects with filtering, ordering, and searching capabilities."
    ),
    bulk_delete=extend_schema(
        request={
            'application/json': {
                'type': 'object',
                'properties': {'project_ids': {'type': 'array', 'items': {'type': 'integer'}}}
            }
        },
        responses={200: {'description': 'Projects deleted successfully'}},
        description="Delete multiple projects in bulk based on their IDs."
    ),
    bulk_change_status=extend_schema(
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'project_ids': {'type': 'array', 'items': {'type': 'integer'}},
                    'status': {'type': 'string', 'enum': list(dict(Project.PROJECT_STATUS_CHOICES).keys())}
                }
            }
        },
        responses={200: {'description': 'Project statuses updated successfully'}},
        description="Change the status of multiple projects in bulk. Validates status against allowed choices."
    ),
    project_invitations=extend_schema(
        request=AdminProjectInvitationSerializer,
        responses={201: {'description': 'Project invitations sent successfully'}},
        description="Send project invitations to users."
    )
)
class ProjectAdminViewSet(AdminViewSet, InvitationEmailMixin):
    """
    Admin ViewSet for managing projects. Supports CRUD operations,
    bulk actions (delete and status change, invite), filtering, searching,
    and ordering of project records.
    """
    # Set the base queryset with optimized related object retrieval
    queryset = Project.objects.all().select_related('owner')
    # Define filters, ordering, and searching for the API
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['status', 'owner']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'due_date', 'total_tasks']
    json_encoder = DjangoJSONEncoder
    def get_serializer_class(self):
        """
        Dynamically return the appropriate serializer class based on the action.
        """
        if self.action == 'list':
            return AdminProjectListSerializer
        elif self.action == 'retrieve':
            return AdminProjectDetailSerializer
        elif self.action == 'create':
            return AdminProjectCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return AdminProjectUpdateSerializer
        return AdminProjectDetailSerializer

    def get_queryset(self):
        """
        Retrieve and optionally cache the queryset for performance optimization.
        """
        cache_key = "admin_projects_list"
        cached_queryset = cache.get(cache_key)
        if cached_queryset is None:
            queryset = super().get_queryset()
            cache.set(cache_key, queryset, timeout=60 * 5)  # Cache for 5 minutes
            return queryset
        return cached_queryset
    
    def get_serializer_context(self):
        """
        Provide additional context to the serializers.
        """
        context = super().get_serializer_context()
        context['request'] = self.request
        return context
    
    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        """
        Delete multiple projects in bulk based on their IDs.

        - Accepts a list of project IDs to delete.
        - Logs the admin action for audit purposes.
        """
        project_ids = request.data.get('project_ids', [])
        deleted_count = Project.objects.filter(id__in=project_ids).delete()[0]
        self.log_admin_action('bulk_delete_projects', None, {'project_ids': project_ids, 'deleted_count': deleted_count})
        project_logger.log(INFO, f"Admin bulk deleted {deleted_count} projects")
        return Response({'status': f'{deleted_count} projects deleted'})

    @action(detail=False, methods=['post'])
    def bulk_change_status(self, request):
        """
        Change the status of multiple projects in bulk.

        - Accepts a list of project IDs and the new status.
        - Validates the status against predefined choices.
        - Logs the admin action for audit purposes.
        """
        project_ids = request.data.get('project_ids', [])
        new_status = request.data.get('status')
        if new_status not in dict(Project.PROJECT_STATUS_CHOICES).keys():
            project_logger.log(ERROR, f"Admin attempted invalid bulk status change")
            return Response({'error': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)
        
        updated_count = Project.objects.filter(id__in=project_ids).update(status=new_status)
        self.log_admin_action('bulk_change_project_status', None, {'project_ids': project_ids, 'new_status': new_status, 'updated_count': updated_count})
        project_logger.log(INFO, f"Admin bulk changed status for {updated_count} projects to {new_status}")
        return Response({'status': f'{updated_count} projects updated to status {new_status}'})
    
    @action(detail=False, methods=['post'], url_path='invite')
    def invite_project_members(self, request):
        """
        Custom action to send invitations to users for a specific project.
        This action sends invitations to a list of emails, and excludes existing members.
        """
        # Retrieve the project ID from the payload
        project_id = request.data.get('project')
        if not project_id:
            return Response({"error": "Project ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Retrieve the project from the database using the project ID
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return Response({"error": "Project not found."}, status=status.HTTP_404_NOT_FOUND)

        # Initialize the serializer with the request data and project
        serializer = AdminProjectInvitationSerializer(data=request.data, context={'request': request, 'project': project})
        serializer.is_valid(raise_exception=True)

        # Perform the creation of invitations
        invitations = serializer.save()

        # Use InvitationEmailMixin to send emails for each invitation
        self.send_invitation_emails(invitations)

        # Prepare response data
        response_data = {
            "message": "Invitations created successfully.",
            "invitations": [
                {
                    "email": invitation.email,
                    "expires_at": invitation.expires_at.strftime('%Y-%m-%d %H:%M:%S')
                }
                for invitation in invitations
            ],
            "existing_members": serializer.context.get('existing_members', [])
        }

        return Response(response_data, status=status.HTTP_201_CREATED)

    def send_invitation_emails(self, invitations):
        """
        Sends invitation emails to each user in the list of invitations.
        """
        for invitation in invitations:
            # Using the mixin's method to send the email
            self.send_invitation_email(self.request, invitation)
@extend_schema_view(
    list=extend_schema(
        description="Retrieve a list of project memberships with filtering, searching, and ordering capabilities."
    ),
    bulk_add=extend_schema(
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'project_id': {'type': 'integer'},
                    'user_ids': {'type': 'array', 'items': {'type': 'integer'}},
                    'role': {'type': 'string', 'default': 'member'}
                },
                'required': ['project_id', 'user_ids']
            }
        },
        responses={200: {'description': 'Members added successfully'}},
        description="Add multiple users to a project as members. Skips users already in the project."
    ),
    bulk_remove=extend_schema(
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'project_id': {'type': 'integer'},
                    'user_ids': {'oneOf': [
                        {'type': 'array', 'items': {'type': 'integer'}},
                        {'type': 'string', 'enum': ['all']}
                    ]}
                },
                'required': ['project_id']
            }
        },
        responses={200: {'description': 'Members removed successfully'}},
        description="Remove multiple users from a project. Use 'all' to remove all members except the project owner."
    ),
)
class ProjectMembershipAdminViewSet(viewsets.ViewSet):
    """
    Admin ViewSet for managing project memberships. 
    Supports CRUD operations and bulk actions (add and remove members).
    """

    # Set the base queryset for project memberships
    queryset = ProjectMembership.objects.all()

    # Define filters, searching, and ordering for the API
    filterset_fields = ['project', 'user', 'role']
    search_fields = ['user__username', 'user__email']
    ordering_fields = ['joined_at']

    def get_serializer_class(self):
        """
        Dynamically return the appropriate serializer class based on the action.
        """
        if self.action in ['create', 'update', 'partial_update']:
            return AdminProjectMembershipCreateUpdateSerializer
        return AdminProjectMembershipSerializer

    @action(detail=False, methods=['post'], name='Bulk Add Members')
    def bulk_add(self, request):
        """
        Add multiple users to a project as members.

        - Requires `project_id`, `user_ids` (list of user IDs), and `role` (default: 'member').
        - Validates the project and users before creating memberships.
        - Skips users already in the project.
        """
        project_id = request.data.get('project_id')
        user_ids = request.data.get('user_ids', [])
        role = request.data.get('role', 'member')

        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)

        users = User.objects.filter(id__in=user_ids)
        existing_memberships = ProjectMembership.objects.filter(project=project, user__in=users)
        existing_user_ids = existing_memberships.values_list('user_id', flat=True)

        # Create memberships for users not already part of the project
        new_memberships = [
            ProjectMembership(project=project, user=user, role=role)
            for user in users if user.id not in existing_user_ids
        ]
        ProjectMembership.objects.bulk_create(new_memberships)
        added_count = len(new_memberships)

        # Log the admin action
        self.log_admin_action('bulk_add_members', project, {'user_ids': user_ids, 'role': role, 'added_count': added_count})
        project_logger.log(INFO, f"Admin bulk added {added_count} members to project: {project.id}")

        return Response({'status': f'{added_count} members added'})

    @action(detail=False, methods=['post'], name='Bulk Remove Members')
    def bulk_remove(self, request):
        """
        Remove multiple users from a project.

        - Requires `project_id` and `user_ids` (list of user IDs or 'all' to remove all members).
        - Excludes the project owner from removal.
        """
        project_id = request.data.get('project_id')
        user_ids = request.data.get('user_ids', [])

        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)

        memberships_to_remove = ProjectMembership.objects.filter(project=project)

        if user_ids == 'all':
            # Remove all members except the project owner
            memberships_to_remove = memberships_to_remove.exclude(user=project.owner)
        else:
            # Remove specific members, excluding the project owner
            memberships_to_remove = memberships_to_remove.filter(user_id__in=user_ids).exclude(user=project.owner)

        removed_count = memberships_to_remove.count()
        memberships_to_remove.delete()

        # Log the admin action
        self.log_admin_action('bulk_remove_members', project, {'user_ids': user_ids, 'removed_count': removed_count})
        project_logger.log(INFO, f"Admin bulk removed {removed_count} members from project: {project.id}")

        return Response({'status': f'{removed_count} members removed'})

@extend_schema_view(
    list=extend_schema(description="List tasks with filtering, searching, and ordering."),
    retrieve=extend_schema(description="Retrieve detailed information about a task."),
    create=extend_schema(description="Create a new task."),
    update=extend_schema(description="Update an existing task."),
    bulk_update=extend_schema(
        description="Bulk update multiple tasks.",
        request=AdminTaskBulkUpdateSerializer,
        responses={200: {"description": "Tasks updated successfully"}}
    ),
    bulk_assign=extend_schema(
        description="Bulk assign users to tasks.",
        request=AdminTaskBulkAssignSerializer,
        responses={200: {"description": "Users assigned to tasks successfully"}}
    ),
    bulk_unassign=extend_schema(
        description="Bulk unassign users from tasks.",
        request=AdminTaskBulkUnassignSerializer,
        responses={200: {"description": "Users unassigned from tasks successfully"}}
    )
)
class TaskAdminViewSet(viewsets.ViewSet):
    """
    ViewSet for managing tasks with admin privileges. 
    Includes bulk update, assign, and unassign actions.
    """
    queryset = Task.objects.select_related("project", "assigned_by", "approved_by").prefetch_related("assignments")
    serializer_class = AdminTaskDetailSerializer
    filterset_fields = ["status", "project", "need_approval", "assignments__user"]
    search_fields = ["name", "description", "project__name", "assignments__user__username"]
    ordering_fields = ["due_date", "status", "total_assignees"]
    ordering = ["-due_date"]
    json_encoder_class = DjangoJSONEncoder

    def get_serializer_class(self):
        """
        Return the appropriate serializer based on the action.
        """
        if self.action == 'list':
            return AdminTaskListSerializer
        elif self.action == 'retrieve':
            return AdminTaskDetailSerializer
        elif self.action == 'create':
            return AdminTaskCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return AdminTaskUpdateSerializer
        return super().get_serializer_class()

    def get_queryset(self):
        """
        Cache the queryset to improve performance for frequently accessed data.
        """
        cache_key = "admin_tasks_list"
        cached_queryset = cache.get(cache_key)
        if not cached_queryset:
            queryset = super().get_queryset()
            cache.set(cache_key, queryset, timeout=60 * 5)  # Cache for 5 minutes
            return queryset
        return cached_queryset

    @action(detail=False, methods=['post'], url_path='bulk-update')
    def bulk_update(self, request):
        """
        Bulk update multiple tasks with the specified fields.
        """
        serializer = AdminTaskBulkUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tasks = Task.objects.filter(id__in=serializer.validated_data['task_ids'])
        update_fields = {
            key: value
            for key, value in serializer.validated_data.items()
            if key in ['due_date', 'project', 'status']
        }

        updated_count = tasks.update(**update_fields)
        self.log_admin_action('bulk_update', None, {
            'task_ids': serializer.validated_data['task_ids'],
            'updates': update_fields,
            'updated_count': updated_count
        })
        project_logger.log(INFO, f"Bulk updated {updated_count} tasks.")

        return Response({'status': f'{updated_count} tasks updated'})

    @action(detail=False, methods=['post'], url_path='assign')
    def bulk_assign(self, request):
        """
        Bulk assign users to tasks.
        """
        serializer = AdminTaskBulkAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        assignments = [
            TaskAssignment(task_id=task_id, user_id=user_id)
            for task_id in serializer.validated_data['task_ids']
            for user_id in serializer.validated_data['user_ids']
        ]

        created = TaskAssignment.objects.bulk_create(assignments, ignore_conflicts=True)
        Task.objects.filter(id__in=serializer.validated_data['task_ids']).update(
            total_assignees=F('total_assignees') + len(serializer.validated_data['user_ids'])
        )

        self.log_admin_action('bulk_assign', None, {
            'task_ids': serializer.validated_data['task_ids'],
            'user_ids': serializer.validated_data['user_ids'],
            'assignments_created': len(created)
        })
        project_logger.log(INFO, f"Bulk assigned users to {len(created)} tasks.")

        return Response({'status': f'{len(created)} assignments created'})

    @action(detail=False, methods=['post'], url_path='unassign')
    def bulk_unassign(self, request):
        """
        Bulk unassign users from tasks.
        """
        serializer = AdminTaskBulkUnassignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        assignments_to_delete = TaskAssignment.objects.filter(
            task_id__in=serializer.validated_data['task_ids'],
            user_id__in=serializer.validated_data['user_ids']
        )

        task_counts = assignments_to_delete.values('task_id').annotate(count=Count('id'))
        for task_count in task_counts:
            Task.objects.filter(id=task_count['task_id']).update(
                total_assignees=F('total_assignees') - task_count['count']
            )

        deleted_count = assignments_to_delete.delete()[0]
        self.log_admin_action('bulk_unassign', None, {
            'task_ids': serializer.validated_data['task_ids'],
            'user_ids': serializer.validated_data['user_ids'],
            'assignments_deleted': deleted_count
        })
        project_logger.log(INFO, f"Bulk unassigned users from {deleted_count} tasks.")

        return Response({'status': f'{deleted_count} assignments deleted'})
    
@extend_schema_view(
    list=extend_schema(
        description="List task assignments with filtering, searching, and ordering.",
        responses={200: AdminTaskAssignmentSerializer(many=True)},
    ),
    retrieve=extend_schema(
        description="Retrieve detailed information about a task assignment.",
        responses={200: AdminTaskAssignmentSerializer},
    )
)
class TaskAssignmentAdminViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing task assignments with admin privileges.
    Includes caching for improved performance.
    """
    queryset = TaskAssignment.objects.select_related(
        'task', 'task__project', 'user', 'user__profile', 'assigned_by', 'assigned_by__profile'
    ).prefetch_related(
        Prefetch('task__assignments'),
        Prefetch('task__comments')
    )
    serializer_class = AdminTaskAssignmentSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    filterset_fields = ['task__project', 'user']
    search_fields = ['task__name', 'user__username']
    ordering_fields = ['assigned_at']
    ordering = ['-assigned_at']

    def get_queryset(self):
        """
        Override to include caching for the admin task assignments list.
        Caches results for 5 minutes, scoped to the admin user.
        """
        cache_key = f'admin_task_assignments_{self.request.user.id}'
        queryset = cache.get(cache_key)
        if not queryset:
            queryset = super().get_queryset()
            cache.set(cache_key, queryset, timeout=60 * 5)  # Cache for 5 minutes
            project_logger.log(INFO, f"Cached queryset for user {self.request.user.id}")
        return queryset
    
@extend_schema_view(
    list=extend_schema(
        description="Retrieve a list of status change requests with the ability to filter by status, task, and user.",
        responses={200: AdminTaskStatusChangeRequestListSerializer},
    ),
    bulk_update=extend_schema(
        description="Bulk update the status of multiple status change requests. Approve or reject the requests.",
        responses={
            200: OpenApiResponse(description="Bulk update successful."),
            400: OpenApiResponse(description="Invalid parameters provided."),
        },
    )
)
class AdminStatusChangeRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing status change requests with admin privileges.
    Includes caching for improved performance and bulk update functionality.
    """
    queryset = StatusChangeRequest.objects.select_related(
        'task', 'task__project', 'user', 'user__profile', 'approved_by', 'approved_by__profile'
    ).prefetch_related(
        'task__assignments', 'task__comments'
    )
    permission_classes = [IsAdminUser]
    filterset_fields = ['status', 'task__project', 'user']
    search_fields = ['task__name', 'user__username', 'reason']
    ordering_fields = ['request_time', 'status']
    ordering = ['-request_time']

    def get_queryset(self):
        """
        Override to include caching for the admin status change requests list.
        Caches results for 5 minutes, scoped to the admin user.
        """
        cache_key = f'admin_status_change_requests_{self.request.user.id}'
        queryset = cache.get(cache_key)
        
        if not queryset:
            queryset = super().get_queryset()
            cache.set(cache_key, queryset, timeout=300)  # Cache for 5 minutes
            project_logger.log(INFO, f"Cached queryset for user {self.request.user.id}")
        
        return queryset

    def get_serializer_class(self):
        """
        Returns the appropriate serializer class based on the action.
        """
        if self.action == 'list':
            return AdminTaskStatusChangeRequestListSerializer
        return AdminTaskStatusChangeRequestDetailSerializer

    @action(detail=False, methods=['post'], url_path='bulk-update')
    def bulk_update(self, request):
        """
        Bulk update the status of status change requests.
        The 'approve' or 'reject' actions update the status accordingly.
        """
        action = request.data.get('action')
        request_ids = request.data.get('request_ids', [])
        
        if not request_ids or action not in ['approve', 'reject']:
            return Response(
                {"error": "Invalid parameters"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # Fetch the status change requests that are pending
            requests = self.get_queryset().filter(
                id__in=request_ids,
                status='pending'
            )
            
            for request_obj in requests:
                if action == 'approve':
                    request_obj.approve(self.request.user)
                    request_obj.task.status = 'completed'
                    request_obj.task.approved_by = self.request.user
                    request_obj.task.save()
                elif action == 'reject':
                    request_obj.reject(self.request.user)
                    request_obj.task.status = 'pending'
                    request_obj.task.approved_by = None
                    request_obj.task.save()
                
                # Log the admin action
                self.log_admin_action(
                    f"{action}_status_change_request",
                    request_obj,
                    {'status': request_obj.status}
                )
        
        # Clear relevant caches after bulk update
        cache.delete_many([
            f'admin_status_change_requests_{self.request.user.id}',
            'task_stats',
            'project_stats'
        ])
        project_logger.log(INFO, f"Bulk update completed for status change requests by admin {self.request.user.id}")
        
        return Response({"detail": "Bulk update completed."}, status=status.HTTP_200_OK)
    

@extend_schema_view(
    list=extend_schema(
        description="List all subscriptions with filtering, searching, and ordering.",
        responses={200: OpenApiResponse(description='List of subscriptions', examples={'application/json': {'id': 1, 'user': 'user123', 'plan': 'premium', 'start_date': '2024-01-01'}})}
    ),
    retrieve=extend_schema(
        description="Retrieve detailed information about a subscription.",
        responses={200: OpenApiResponse(description='Subscription details', examples={'application/json': {'id': 1, 'user': 'user123', 'plan': 'premium', 'start_date': '2024-01-01', 'is_active': True}})}
    ),
    cancel_subscription=extend_schema(
        description="Cancel a subscription and revert to the basic plan.",
        request=OpenApiParameter('reason', type=str, required=False, description="Reason for cancellation"),
        responses={
            200: OpenApiResponse(description='Subscription cancelled successfully', examples={'application/json': {'status': 'Subscription cancelled and reverted to basic plan', 'new_plan': 'basic'}}),
            400: OpenApiResponse(description='Bad request, invalid parameters')
        }
    ),
    renew_subscription=extend_schema(
        description="Renew a subscription for another 30 days.",
        responses={
            200: OpenApiResponse(description='Subscription renewed successfully', examples={'application/json': {'status': 'Subscription renewed'}}),
            400: OpenApiResponse(description='Bad request, invalid parameters')
        }
    ),
    plans=extend_schema(
        description="Get all available subscription plans.",
        responses={200: OpenApiResponse(description='List of subscription plans', examples={'application/json': [{'id': 1, 'name': 'premium', 'duration_days': 30}]})}
    ),
    plan_stats=extend_schema(
        description="Get statistics for each subscription plan.",
        responses={200: OpenApiResponse(description='Plan statistics', examples={'application/json': [{'id': 1, 'name': 'premium', 'subscriber_count': 100, 'revenue': 1000.0}]})}
    ),
    payments=extend_schema(
        description="Get payment history for subscriptions.",
        responses={200: OpenApiResponse(description='List of payments', examples={'application/json': [{'id': 1, 'subscription_id': 1, 'amount': 50.0, 'status': 'completed'}]})}
    ),
    payment_stats=extend_schema(
        description="Get payment statistics for completed payments.",
        responses={200: OpenApiResponse(description='Payment statistics', examples={'application/json': {'total_revenue': 5000.0, 'monthly_revenue': 1000.0}})}
    ),
    dashboard_stats=extend_schema(
        description="Get overall subscription, plan, and payment statistics.",
        responses={200: OpenApiResponse(description='Dashboard statistics', examples={'application/json': {'subscriptions': {'active': 50, 'total': 100}, 'plans': [...], 'payments': {...}}})}
    ),
)
class SubscriptionAdminViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing subscriptions with admin privileges.
    Handles subscription actions (cancel, renew) and provides statistics.
    """
    queryset = Subscription.objects.select_related('user', 'plan').prefetch_related('payments')
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['is_active', 'plan', 'user']
    search_fields = ['user__username', 'user__email']
    ordering_fields = ['start_date', 'end_date']

    def get_serializer_class(self):
        """
        Returns the appropriate serializer class based on the action.
        """
        if self.action == 'list':
            return AdminSubscriptionListSerializer
        return AdminSubscriptionDetailSerializer

    # Subscription Actions
    @action(detail=True, methods=['post'], url_path='cancel-subscription')
    def cancel_subscription(self, request, pk=None):
        """
        Cancels the subscription and reverts it to the basic plan.
        Logs the change with the reason for cancellation.
        """
        subscription = self.get_object()
        reason = request.data.get('reason', '')
        
        # Log current plan before cancellation
        old_plan = subscription.plan
        
        # Revert to basic plan
        subscription.revert_to_basic_plan()
        
        # Log the cancellation
        self.log_admin_action('cancel_subscription', subscription, {
            'reason': reason,
            'old_plan': old_plan.name,
            'new_plan': 'basic'
        })
        
        return Response({
            'status': 'Subscription cancelled and reverted to basic plan',
            'new_plan': 'basic'
        })

    @action(detail=True, methods=['post'], url_path='renew-subscription')
    def renew_subscription(self, request, pk=None):
        """
        Renews a subscription by extending the end date.
        """
        subscription = self.get_object()
        subscription.is_active = True
        subscription.end_date = timezone.now() + timedelta(days=30 * subscription.plan.duration_days)
        subscription.save()

        # Log the renewal action
        self.log_admin_action('renew_subscription', subscription, {'new_end_date': subscription.end_date})

        return Response({'status': 'Subscription renewed'})

    # Plan Actions
    @action(detail=False, methods=['get'], url_path='plans')
    def plans(self, request):
        """
        Returns all available subscription plans.
        """
        plans = SubscriptionPlan.objects.all()
        serializer = AdminSubscriptionPlanSerializer(plans, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='plan-stats')
    def plan_stats(self, request):
        """
        Returns statistics about each subscription plan, such as active subscribers and revenue.
        """
        stats = SubscriptionPlan.objects.annotate(
            subscriber_count=Count('subscriptions', filter=Q(subscriptions__is_active=True)),
            revenue=Sum('subscriptions__payments__amount', filter=Q(subscriptions__payments__status='completed'))
        ).values('id', 'name', 'subscriber_count', 'revenue')
        
        return Response(stats)

    # Payment Actions
    @action(detail=False, methods=['get'], url_path='payments')
    def payments(self, request):
        """
        Retrieves payment history for all subscriptions.
        """
        payments = Payment.objects.select_related('subscription', 'subscription__user').all()
        serializer = AdminPaymentHistorySerializer(payments, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='payment-stats')
    def payment_stats(self, request):
        """
        Returns statistics for completed payments in the last 30 days, including revenue and payment methods.
        """
        today = timezone.now()
        thirty_days_ago = today - timedelta(days=30)

        stats = {
            'total_revenue': Payment.objects.filter(status='completed').aggregate(Sum('amount')),
            'monthly_revenue': Payment.objects.filter(
                status='completed',
                date__gte=thirty_days_ago
            ).aggregate(Sum('amount')),
            'payment_methods': Payment.objects.values('payment_method').annotate(
                count=Count('id'),
                total=Sum('amount')
            )
        }

        return Response(stats)

    # Overall Statistics
    @action(detail=False, methods=['get'], url_path='dashboard-stats')
    def dashboard_stats(self, request):
        """
        Returns overall statistics for subscriptions, plans, and payments.
        """
        return Response({
            'subscriptions': {
                'active': Subscription.objects.filter(is_active=True).count(),
                'total': Subscription.objects.count()
            },
            'plans': self.plan_stats(request).data,
            'payments': self.payment_stats(request).data
        })

@extend_schema_view(
    list=extend_schema(
        description="List all notifications with filtering, searching, and ordering.",
        responses={200: OpenApiResponse(description='List of notifications', examples={'application/json': [{'id': 1, 'message': 'New Notification', 'recipient': 'user123', 'status': 'unread'}]})}
    ),
    retrieve=extend_schema(
        description="Retrieve detailed information about a notification.",
        responses={200: OpenApiResponse(description='Notification details', examples={'application/json': {'id': 1, 'message': 'New Notification', 'recipient': 'user123', 'status': 'unread'}})}
    ),
    send=extend_schema(
        description="Send a notification to specific users or all users.",
        request=[
            OpenApiParameter('user_ids', type=[int], required=False, description="List of user IDs or 'all'"),
            OpenApiParameter('title', type=str, required=True, description="Title of the notification"),
            OpenApiParameter('body', type=str, required=True, description="Body of the notification"),
            OpenApiParameter('url', type=str, required=False, description="Optional URL to include in the notification")
        ],
        responses={
            200: OpenApiResponse(description='Notifications sent successfully', examples={'application/json': {'status': 'notifications sent'}}),
            400: OpenApiResponse(description='Bad request, missing required parameters')
        }
    ),
    bulk_delete=extend_schema(
        description="Delete notifications in bulk.",
        request=OpenApiParameter('notification_ids', type=[int], required=True, description="List of notification IDs to delete"),
        responses={
            200: OpenApiResponse(description='Bulk delete successful', examples={'application/json': {'status': '3 notifications deleted'}}),
            400: OpenApiResponse(description='Bad request, no notifications specified')
        }
    ),
    stats=extend_schema(
        description="Get statistics for notifications, including total count, unread count, and breakdown by type, status, and priority.",
        responses={200: OpenApiResponse(description='Notification statistics', examples={'application/json': {'total': 100, 'unread': 50, 'by_type': [{'notification_type': 'info', 'count': 10}], 'by_status': [{'status': 'unread', 'count': 50}]}})}
    ),
    resend=extend_schema(
        description="Resend a specific notification.",
        responses={
            200: OpenApiResponse(description='Notification resent successfully', examples={'application/json': {'status': 'Notification resent successfully'}}),
            400: OpenApiResponse(description='Failed to resend notification', examples={'application/json': {'status': 'Notification resend failed'}})
        }
    ),
)

class NotificationAdminViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing notifications with admin privileges.
    Handles actions like sending, deleting, and viewing stats.
    """
    queryset = Notification.objects.all()
    serializer_class = NotificationAdminSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = {
        'is_read': ['exact'],
        'notification_type': ['exact', 'in'],
        'recipient': ['exact'],
        'status': ['exact', 'in'],
        'priority': ['exact', 'in'],
        'created_at': ['gte', 'lte'],
    }
    search_fields = ['message', 'recipient__username', 'sender__username']
    ordering_fields = ['created_at', 'priority', 'status', 'retry_count']
    ordering = ['-created_at']

    def get_queryset(self):
        """
        Returns the queryset for notifications with optimized selects.
        """
        return Notification.objects.select_related(
            'recipient', 'sender', 'content_type'
        ).prefetch_related('content_object')

    @action(detail=False, methods=['post'])
    def send(self, request):
        """
        Send a notification to specific users or all users.
        """
        user_ids = request.data.get('user_ids', None)  # List of user IDs or 'all'
        title = request.data.get('title')
        body = request.data.get('body')
        url = request.data.get('url', '')  # Optional URL

        if not title or not body:
            return Response({'error': 'Title, body, and URL are required'}, status=status.HTTP_400_BAD_REQUEST)

        if user_ids == 'all':  # Notify all users
            users = User.objects.all()
        else:  # Notify specific users
            users = User.objects.filter(id__in=user_ids)

        if not users.exists():
            return Response({'error': 'No recipients found'}, status=status.HTTP_400_BAD_REQUEST)

        for user in users:
            send_real_time_notification.delay(
                user=user,
                message={
                    "title": title,
                    "body": body,
                    "url": url,
                },
                notification_type="admin_notification",
                content_type=ContentType.objects.get_for_model(User).id,
                object_id=user.id
            )

        self.log_admin_action('send_notification', None, {'user_ids': user_ids, 'title': title})
        return Response({'status': 'notifications sent'})

    @action(detail=False, methods=['post'])
    def bulk_delete(self, request):
        """
        Delete notifications in bulk by their IDs.
        """
        notification_ids = request.data.get('notification_ids', [])
        
        if not notification_ids:
            return Response({'error': 'No notifications specified'}, status=400)
            
        deleted_count = Notification.objects.filter(id__in=notification_ids).delete()[0]
        
        self.log_admin_action('bulk_delete_notifications', None, {
            'notification_ids': notification_ids,
            'deleted_count': deleted_count
        })
        
        return Response({
            'status': f'{deleted_count} notifications deleted'
        })

    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Retrieve statistics about notifications.
        Includes total, unread, and breakdown by type, status, and priority.
        """
        stats = {
            'total': Notification.objects.count(),
            'unread': Notification.objects.filter(is_read=False).count(),
            'by_type': Notification.objects.values('notification_type').annotate(
                count=Count('id')
            ),
            'by_status': Notification.objects.values('status').annotate(
                count=Count('id')
            ),
            'by_priority': Notification.objects.values('priority').annotate(
                count=Count('id')
            )
        }
        return Response(stats)

    @action(detail=True, methods=['post'])
    def resend(self, request, pk=None):
        """
        Resend a specific notification to the recipient.
        """
        notification = self.get_object()
        success = notification.resend_notification()
        
        if success:
            return Response({'status': 'Notification resent successfully'})
        return Response(
            {'status': 'Notification resend failed'},
            status=400
        )

@extend_schema_view(
    list=extend_schema(
        description="List admin action logs with filtering and searching options.",
        responses={200: OpenApiResponse(description='List of admin action logs', examples={'application/json': [{'id': 1, 'user': 'admin', 'action': 'update', 'timestamp': '2025-01-01T12:00:00Z'}]})}
    )
)
class AdminActionLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing admin action logs with filtering and searching options.
    """
    queryset = AdminActionLog.objects.all()
    serializer_class = AdminActionLogSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]
    filterset_fields = ['user', 'action', 'content_type']
    search_fields = ['changes']
    ordering_fields = ['timestamp']


@extend_schema_view(
    user_activity=extend_schema(
        description="Get statistics on user activity (active users and new users) from the last 30 days.",
        responses={200: OpenApiResponse(description='User activity statistics', examples={'application/json': {'active_users_last_30_days': 100, 'new_users_last_30_days': 50}})}
    ),
    project_stats=extend_schema(
        description="Get statistics on projects including total count and count by status.",
        responses={200: OpenApiResponse(description='Project statistics', examples={'application/json': {'total_projects': 50, 'projects_by_status': [{'status': 'active', 'count': 30}, {'status': 'inactive', 'count': 20}]}})}
    ),
    task_stats=extend_schema(
        description="Get statistics on tasks including total count and count by status.",
        responses={200: OpenApiResponse(description='Task statistics', examples={'application/json': {'total_tasks': 200, 'tasks_by_status': [{'status': 'completed', 'count': 120}, {'status': 'pending', 'count': 80}]}})}
    ),
    subscription_stats=extend_schema(
        description="Get statistics on subscriptions, including total, active subscriptions, revenue, and subscriptions by plan.",
        responses={200: OpenApiResponse(description='Subscription statistics', examples={'application/json': {'total_subscriptions': 150, 'active_subscriptions': 100, 'total_revenue': 5000, 'subscriptions_by_plan': [{'plan_name': 'basic', 'count': 80}, {'plan_name': 'premium', 'count': 70}]}})}
    )
)
class AnalyticsView(viewsets.ViewSet):
    """
    ViewSet for fetching analytics data on users, projects, tasks, and subscriptions.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]

    @action(detail=False, methods=['get'])
    def user_activity(self, request):
        """
        Get statistics on user activity from the last 30 days (active and new users).
        """
        cache_key = 'user_activity_stats'
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)

        last_30_days = timezone.now() - timedelta(days=30)
        active_users = User.objects.filter(last_login__gte=last_30_days).count()
        new_users = User.objects.filter(date_joined__gte=last_30_days).count()
        data = {
            'active_users_last_30_days': active_users,
            'new_users_last_30_days': new_users
        }
        cache.set(cache_key, data, 3600)  # Cache for 1 hour
        return Response(data)

    @action(detail=False, methods=['get'])
    def project_stats(self, request):
        """
        Get project statistics including total count and projects grouped by status.
        """
        cache_key = 'project_stats'
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)

        total_projects = Project.objects.count()
        projects_by_status = Project.objects.values('status').annotate(count=Count('id'))
        data = {
            'total_projects': total_projects,
            'projects_by_status': projects_by_status
        }
        cache.set(cache_key, data, 3600)  # Cache for 1 hour
        return Response(data)

    @action(detail=False, methods=['get'])
    def task_stats(self, request):
        """
        Get task statistics including total count and tasks grouped by status.
        """
        cache_key = 'task_stats'
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)

        total_tasks = Task.objects.count()
        tasks_by_status = Task.objects.values('status').annotate(count=Count('id'))
        data = {
            'total_tasks': total_tasks,
            'tasks_by_status': tasks_by_status
        }
        cache.set(cache_key, data, 3600)  # Cache for 1 hour
        return Response(data)

    @action(detail=False, methods=['get'])
    def subscription_stats(self, request):
        """
        Get subscription statistics including total subscriptions, active subscriptions, total revenue, and subscriptions grouped by plan.
        """
        cache_key = 'subscription_stats'
        cached_data = cache.get(cache_key)
        if cached_data:
            return Response(cached_data)

        total_subscriptions = Subscription.objects.count()
        active_subscriptions = Subscription.objects.filter(is_active=True).count()
        revenue = Subscription.objects.filter(is_active=True).aggregate(total=Sum('plan__price'))
        subscriptions_by_plan = Subscription.objects.values('plan__name').annotate(count=Count('id'))
        
        data = {
            'total_subscriptions': total_subscriptions,
            'active_subscriptions': active_subscriptions,
            'total_revenue': revenue['total'],
            'subscriptions_by_plan': subscriptions_by_plan
        }
        cache.set(cache_key, data, 3600)  # Cache for 1 hour
        return Response(data)

@extend_schema_view(
    check=extend_schema(
        description="Perform health checks for all system components and services concurrently. Returns the health status of each component.",
        responses={200: OpenApiResponse(
            description='System Health Check Status',
            examples={
                'application/json': {
                    'database': 'healthy',
                    'cache': 'healthy',
                    'celery_worker': 'running',
                    'celery_beat': 'running',
                    'email': 'working',
                    'log_file': {'status': 'healthy', 'size': 1024},
                    'network': {'status': 'healthy', 'latency_ms': 120},
                    'stripe': 'healthy',
                    'worker_queue': {'status': 'healthy', 'total_tasks': 50}
                }
            }
        )}
    )
)
class SystemHealthView(viewsets.ViewSet):
    """
    A ViewSet to perform health checks for various system components and services.
    Optimized using a hybrid caching approach to improve performance and responsiveness.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminUser]

    @action(detail=False, methods=['get'])
    def check(self, request):
        """
        Perform health checks for all registered components in parallel.
        Results are returned as a JSON response, and logs capture the check statuses.
        """
        status = {}
        checks = [
            self.check_database,
            self.check_cache,
            self.check_celery_worker,
            self.check_celery_beat,
            self.check_email,
            self.check_log_file,
            self.check_network,
            self.check_stripe,
            self.check_worker_queue,
        ]
        from concurrent.futures import ThreadPoolExecutor
        # Execute health checks concurrently
        with ThreadPoolExecutor(max_workers=len(checks)) as executor:
            future_to_check = {executor.submit(check): check.__name__.replace("check_", "") for check in checks}
            for future in future_to_check:
                check_name = future_to_check[future]
                try:
                    result = future.result()
                    status.update(result)
                except Exception as e:
                    project_logger.log(ERROR, f"Error in {check_name}: {str(e)}")
                    status[check_name] = "error"

        project_logger.log(INFO, "System health check completed")
        return Response(status)

    def _hybrid_check(self, key, check_func, timeout=60):
        cached = cache.get(key)
        if cached is not None:
            Thread(target=lambda: cache.set(key, check_func(), timeout)).start()
            return cached
        else:
            result = check_func()
            cache.set(key, result, timeout)
            return result

    def check_database(self):
        return self._hybrid_check("health_check_database", self._check_database)

    def _check_database(self):
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return {"database": "healthy"}

    def check_cache(self):
        return self._hybrid_check("health_check_cache", self._check_cache)

    def _check_cache(self):
        cache.set("health_check", "ok", 10)
        return {"cache": "healthy" if cache.get("health_check") == "ok" else "unhealthy"}

    def check_celery_worker(self):
        return self._hybrid_check("health_check_celery_worker", self._check_celery_worker)

    def _check_celery_worker(self):
        from celery import current_app
        from celery.app.control import Control
        control = Control(current_app)
        return {"celery_worker": "running" if control.ping(timeout=1.0) else "not running"}

    def check_celery_beat(self):
        return self._hybrid_check("health_check_celery_beat", self._check_celery_beat)

    def _check_celery_beat(self):
        import psutil
        is_running = any(
            "celery" in process.info["name"] and "beat" in " ".join(process.info["cmdline"])
            for process in psutil.process_iter(["name", "cmdline"])
        )
        return {"celery_beat": "running" if is_running else "not running"}

    def check_email(self):
        return self._hybrid_check("health_check_email", self._check_email)

    def _check_email(self):
        from django.core.mail import send_mail
        try:
            send_mail(
                "Health Check",
                "This is a test email for health check.",
                settings.DEFAULT_FROM_EMAIL,
                [settings.EMAIL_HOST_USER],
                fail_silently=False,
            )
            return {"email": "working"}
        except Exception:
            return {"email": "error"}

    def check_log_file(self):
        return self._hybrid_check("health_check_log_file", self._check_log_file)

    def _check_log_file(self):
        log_path = os.path.join(settings.BASE_DIR, "logs", "application.log")
        max_size = getattr(settings, "LOG_FILE_MAX_SIZE_MB", 50) * 1024 * 1024
        log_size = os.path.getsize(log_path) if os.path.exists(log_path) else 0
        return {"log_file": {"status": "healthy" if log_size < max_size else "large", "size": log_size}}

    def check_network(self):
        return self._hybrid_check("health_check_network", self._check_network)

    def _check_network(self):
        start_time = time.time()
        try:
            response = requests.get("https://www.google.com", timeout=2)
            latency = (time.time() - start_time) * 1000
            status = "healthy" if response.status_code == 200 and latency < 500 else "slow"
            return {"network": {"status": status, "latency_ms": latency}}
        except requests.RequestException:
            return {"network": {"status": "error", "latency_ms": None}}

    def check_stripe(self):
        return self._hybrid_check("health_check_stripe", self._check_stripe)

    def _check_stripe(self):
        try:
            response = requests.get(
                "https://api.stripe.com/v1/charges?limit=1",
                headers={"Authorization": f"Bearer {settings.STRIPE_SECRET_KEY}"},
                timeout=5,
            )
            return {"stripe": "healthy" if response.status_code == 200 else "unreachable"}
        except requests.RequestException:
            return {"stripe": "error"}

    def check_worker_queue(self):
        return self._hybrid_check("health_check_worker_queue", self._check_worker_queue)

    def _check_worker_queue(self):
        from celery import Celery
        app = Celery("project_planner")
        app.config_from_object("django.conf:settings", namespace="CELERY")
        inspector = app.control.inspect()
        try:
            reserved = inspector.reserved() or {}
            active = inspector.active() or {}
            scheduled = inspector.scheduled() or {}
            total = (
                sum(len(v) for v in reserved.values())
                + sum(len(v) for v in active.values())
                + sum(len(v) for v in scheduled.values())
            )
            return {"worker_queue": {"status": "healthy" if total < 100 else "backlogged", "total_tasks": total}}
        except Exception:
            return {"worker_queue": {"status": "error", "total_tasks": 0}}

@extend_schema_view(
    list=extend_schema(
        description="List all comments (excluding replies). The results are filtered by task, project, author, and parent. Supports searching and ordering.",
        responses={200: AdminCommentListSerializer},
    ),
    replies=extend_schema(
        description="Get replies for a specific comment. The replies are returned in descending order of creation date.",
        responses={200: AdminCommentListSerializer},
    ),
    bulk_delete=extend_schema(
        description="Bulk delete comments by a list of comment IDs. The comments are permanently deleted.",
        responses={200: OpenApiResponse(description="Success status of the bulk delete operation")},
    )
)
class CommentAdminViewSet(AdminViewSet):
    queryset = Comment.objects.select_related('author', 'task', 'task__project').prefetch_related('mentioned_users')
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['task', 'task__project', 'author', 'parent']
    search_fields = ['content', 'author__username', 'task__name', 'task__project__name']
    ordering_fields = ['created_at', 'updated_at', 'reply_count', 'mention_count']
    ordering = ['-created_at']

    def get_serializer_class(self):
        if self.action == 'list':
            return AdminCommentListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return AdminCommentCreateUpdateSerializer
        return AdminCommentDetailSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == 'list':
            return queryset.filter(parent=None)
        return queryset

    @action(detail=True, methods=['get'])
    def replies(self, request, pk=None):
        """
        Get replies for a specific comment. Returns replies ordered by creation date in descending order.
        """
        comment = self.get_object()
        replies = Comment.objects.filter(parent=comment).order_by('-created_at')
        page = self.paginate_queryset(replies)
        if page is not None:
            serializer = AdminCommentListSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)
        serializer = AdminCommentListSerializer(replies, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['delete'])
    def bulk_delete(self, request):
        """
        Bulk delete comments by a list of comment IDs. The comments will be permanently deleted.
        """
        comment_ids = request.data.get('comment_ids', [])
        Comment.objects.filter(id__in=comment_ids).delete()
        self.log_admin_action('bulk_delete_comments', None, {'comment_ids': comment_ids})
        return Response({'status': 'comments deleted'})

