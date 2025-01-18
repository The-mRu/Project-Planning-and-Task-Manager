from typing import Any

# Local imports
from apps.projects.models import Project, ProjectMembership
from apps.tasks.models import Task, TaskAssignment, Comment, StatusChangeRequest
from apps.tasks.filters import PermissionBasedFilterBackend
from apps.tasks.serializers import (
    TaskCreateSerializer, TaskListSerializer, TaskDetailSerializer,
    TaskUpdateSerializer, StatusChangeRequestSerializer,CommentCreateSerializer,
    CommentListSerializer, CommentDetailSerializer, TaskStatusChangeSerializer,
    StatusChangeActionSerializer
)
from core.permissions import (
    IsProjectOwner,
    IsProjectMember,
    IsTaskAssignee,
    CanManageTask,
    ReadOnly
)
from apps.notifications.utils import send_real_time_notification
# Django imports
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.urls import reverse
# Third-party imports
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import (
    extend_schema, OpenApiParameter, OpenApiExample, OpenApiTypes
)
from rest_framework import status, filters, permissions
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView, ListAPIView
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.throttling import UserRateThrottle
# Utility for standardized responses
def standardized_response(
    status_code: int,status_message: str,
    message: str,data: dict | None = None
) -> Response:
    """
    Utility to create standardized API responses.
    """
    response = {
        "status": status_message,
        "message": message,
    }
    if data is not None:
        response["data"] = data
    return Response(response, status=status_code)


#=================#
# Task Views      #
#=================#

class TaskListCreateView(ListCreateAPIView):
    """
    View to list all tasks or create a new task with assignees.
    """
    permission_classes = [IsAuthenticated, IsProjectMember | CanManageTask]
    throttle_classes = [UserRateThrottle]
    serializer_class = TaskCreateSerializer

    filter_backends = (DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter)
    filterset_fields = {
        'status': ['exact'],
        'due_date': ['exact', 'gte', 'lte'],
        'assigned_by': ['exact'],
        'project': ['exact'],
        'need_approval': ['exact'],
        'created_at': ['gte', 'lte'],
    }
    search_fields = ['name', 'description']
    ordering_fields = ['due_date', 'status', 'created_at', 'total_assignees']
    ordering = ['-due_date']

    def get_queryset(self):
        """
        Return tasks that the user is associated with either as:
        - An assignee
        - The project owner
        """
        user = self.request.user
        
        queryset = Task.objects.select_related(
            'project',
            'project__owner',
            'assigned_by'
        ).prefetch_related(
            'assignments__user'
        ).filter(
            Q(assignments__user=user) |  # Tasks assigned to user
            Q(project__owner=user)     # Tasks in projects owned by user
        ).distinct()

        # Additional filtering options
        project_id = self.request.query_params.get('project_id')
        if project_id:
            queryset = queryset.filter(project_id=project_id)

        assignee_id = self.request.query_params.get('assignee_id')
        if assignee_id:
            queryset = queryset.filter(assignments__user_id=assignee_id)

        priority = self.request.query_params.get('priority')
        if priority:
            queryset = queryset.filter(priority=priority)

        return queryset
    
    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated(), CanManageTask()]
        return super().get_permissions()
    
    def get_serializer_class(self):
        """
        Override to return the appropriate serializer class based on the request method.
        """
        if self.request.method == 'GET':
            return TaskListSerializer 
        return TaskCreateSerializer
    
    
    def perform_create(self, serializer):
        project = serializer.validated_data['project']
        if not ProjectMembership.objects.filter(project=project, user=self.request.user).exists():
            return standardized_response(
                status_code=403,
                status_message="forbidden",
                message="You do not have permission to create tasks for this project."
            )
        if not project.can_create_tasks():
            raise ValidationError(f"Cannot create tasks when project is {project.status}")
        task = serializer.save(assigned_by=self.request.user)
        assignees = serializer.validated_data.get('assignees', [])
        task_content_type = ContentType.objects.get_for_model(Task)
        request = self.request

        # Send notifications to assignees
        for assignee in assignees:
            send_real_time_notification(
                user=assignee,
                message={
                    "title": "New Task Assigned",
                    "body": f"You have been assigned to the task '{task.name}'.",
                    "url": request.build_absolute_uri(reverse('task-retrieve-update-destroy', kwargs={'pk': task.id})),
                },
                notification_type="task",
                content_type=task_content_type.id,
                object_id=task.id
            )
        return standardized_response(
            status_code=201,
            status_message="success",
            message="Task created successfully.",
            data={"task_id": task.id}
        )
    @extend_schema(
        summary="List and Create Tasks",
        description="Retrieve a list of tasks with filters or create a new task.",
        parameters=[
            OpenApiParameter(name='status', description='Filter tasks by status', required=False, type=str),
            OpenApiParameter(name='due_date', description='Filter tasks by due date', required=False, type=str),
            OpenApiParameter(name='assigned_by', description='Filter tasks by assigner ID', required=False, type=int),
            OpenApiParameter(name='project', description='Filter tasks by project ID', required=False, type=int),
            OpenApiParameter(name='need_approval', description='Filter tasks requiring approval', required=False, type=bool),
            OpenApiParameter(name='page', description='Page number for pagination', required=False, type=int),
            OpenApiParameter(name='page_size', description='Number of items per page', required=False, type=int),
        ],
        request=TaskCreateSerializer,
        responses={
            200: TaskListSerializer(many=True),
            201: TaskListSerializer,
            400: OpenApiExample(
                'Validation Error',
                value={"detail": "Invalid input."},
                response_only=True,
            ),
            403: OpenApiExample(
                'Forbidden',
                value={"detail": "You do not have permission to perform this action."},
                response_only=True,
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        try:
            response = super().post(request, *args, **kwargs)
            return standardized_response(
                status_code=response.status_code,
                status_message="success",
                message="Task created successfully." if response.status_code == 201 else "Tasks retrieved successfully.",
                data=response.data
            )
        except ValidationError as e:
            # Format validation errors into a clear structure
            error_messages = {}
            if hasattr(e.detail, 'items'):  # Handle dictionary of errors
                for field, errors in e.detail.items():
                    if isinstance(errors, list):
                        error_messages[field] = errors[0]
                    else:
                        error_messages[field] = str(errors)
            else:  # Handle list of errors or single error
                error_messages['detail'] = e.detail[0] if isinstance(e.detail, list) else str(e.detail)

            return standardized_response(
                status_code=400,
                status_message="validation_error",
                message="Validation failed",
                data={"errors": error_messages}
            )
        except PermissionDenied as e:
            return standardized_response(
                status_code=403,
                status_message="permission_denied", 
                message="You don't have permission to create tasks in this project."
            )
        except Project.DoesNotExist:
            return standardized_response(
                status_code=404,
                status_message="not_found",
                message="The specified project does not exist."
            )
        except Exception as e:
            return standardized_response(
                status_code=500,
                status_message="server_error",
                message="Failed to process task creation. Please try again."
            )


class TaskRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    """
    API view to retrieve, update, or delete a specific task.
    """
    queryset = Task.objects.all()
    permission_classes = [IsAuthenticated, IsTaskAssignee | CanManageTask]
    throttle_classes = [UserRateThrottle]
    serializer_class = TaskUpdateSerializer

    filter_backends = (DjangoFilterBackend, filters.OrderingFilter)
    filterset_fields = ['status', 'due_date', 'assigned_by', 'project']  # Fields to filter by
    ordering_fields = ['due_date', 'status', 'created_at']  # Allow ordering by these fields
    ordering = ['-due_date']  # Default ordering by due_date descending

    def get_serializer_class(self):
        """
        Use a different serializer for GET request to exclude certain fields.
        """
        if self.request.method == 'GET':
            return TaskDetailSerializer
        return TaskUpdateSerializer

    def get_queryset(self):
        """
        Return the task details with assignments, project, and owner info.
        Optimize the query by using select_related and prefetch_related.
        """
        queryset = Task.objects.select_related(
            'project',                     # Use select_related for the project field (foreign key)
            'project__owner'               # Use select_related for the project's owner (foreign key)
        ).prefetch_related(
            'assignments__user'            # Use prefetch_related for many-to-many relationships (task assignments)
        )

        # Filter tasks so that only those assigned to the user (or project owner) are returned
        user = self.request.user
        queryset = queryset.filter(
            Q(assignments__user=user) | Q(project__owner=user)
        ).distinct()  # Ensure distinct tasks are returned in case of multiple assignees

        # Apply additional filtering to the queryset if needed
        status_filter = self.request.query_params.get('status', None)
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset

    def get_permissions(self):
        if self.request.method in ['PUT', 'PATCH', 'DELETE']:
            return [permissions.IsAuthenticated(), CanManageTask()]
        return super().get_permissions()

    @extend_schema(
        summary="Retrieve Task Details",
        description="Retrieve task details, including assignees, project information, and task status.",
        responses={
            200: TaskDetailSerializer,
            404: OpenApiExample(
                'Task Not Found',
                value={"detail": "Task not found."},
                response_only=True,
            ),
        }
    )
    def get(self, request, *args, **kwargs):
        task = self.get_object()
        serializer = TaskDetailSerializer(task, context={'request': request})
        return standardized_response(
            status_code=status.HTTP_200_OK,
            status_message="success",
            message="Task details retrieved successfully.",
            data=serializer.data
        )

    @extend_schema(
        summary="Update Task",
        description="Update task details, such as assignees, status, or other fields.",
        request=TaskUpdateSerializer,
        responses={
            200: TaskDetailSerializer,
            400: OpenApiExample(
                'Bad Request',
                value={"status": "error", "message": "Invalid input.", "errors": {}},
                response_only=True,
            ),
            403: OpenApiExample(
                'Forbidden',
                value={"status": "error", "message": "You do not have permission to perform this action."},
                response_only=True,
            ),
        }
    )
    def put(self, request, *args, **kwargs):
        try:
            response =  super().put(request, *args, **kwargs)
            return standardized_response(
                status_code=response.status_code,
                status_message="success" if response.status_code == status.HTTP_200_OK else "error",
                message="Task updated successfully." if response.status_code == status.HTTP_200_OK else "Failed to update task.",
                data=response.data
            )
        except ValidationError as e:
            error_messages = {}
            if hasattr(e.detail, 'items'):
                for field, errors in e.detail.items():
                    error_messages[field] = errors[0] if isinstance(errors, list) else str(errors)
            else:
                error_messages['detail'] = e.detail[0] if isinstance(e.detail, list) else str(e.detail)

            return standardized_response(
                status_code=400,
                status_message="validation_error",
                message="Validation failed",
                data={"errors": error_messages}
            )
        except PermissionDenied as e:
            return standardized_response(
                status_code=403,
                status_message="permission_denied", 
                message="You don't have permission to update this task."
            )
        except Task.DoesNotExist:
            return standardized_response(
                status_code=404,
                status_message="not_found",
                message="Task not found."
            )
        except Exception as e:
            return standardized_response(
                status_code=500,
                status_message="server_error",
                message="Failed to process task update. Please try again."
            )

    @extend_schema(
        summary="Partially Update Task",
        description="Partially update task details.",
        request=TaskUpdateSerializer,
        responses={
            200: TaskDetailSerializer,
            400: OpenApiExample(
                'Bad Request',
                value={"status": "error", "message": "Invalid input.", "errors": {}},
                response_only=True,
            ),
            403: OpenApiExample(
                'Forbidden',
                value={"status": "error", "message": "You do not have permission to perform this action."},
                response_only=True,
            ),
        }
    )
    def patch(self, request, *args, **kwargs):
        try:
            response = super().patch(request, *args, **kwargs)
            
            return standardized_response(
                status_code=response.status_code,
                status_message="success" if response.status_code == status.HTTP_200_OK else "error",
                message="Task updated successfully." if response.status_code == status.HTTP_200_OK else "Failed to update task.",
                data=response.data
            )
        except ValidationError as e:
            error_messages = {}
            if hasattr(e.detail, 'items'):
                for field, errors in e.detail.items():
                    error_messages[field] = errors[0] if isinstance(errors, list) else str(errors)
            else:
                error_messages['detail'] = e.detail[0] if isinstance(e.detail, list) else str(e.detail)

            return standardized_response(
                status_code=400,
                status_message="validation_error",
                message="Validation failed",
                data={"errors": error_messages}
            )
        except PermissionDenied as e:
            return standardized_response(
                status_code=403,
                status_message="permission_denied", 
                message="You don't have permission to update this task."
            )
        except Task.DoesNotExist:
            return standardized_response(
                status_code=404,
                status_message="not_found",
                message="Task not found."
            )
        except Exception as e:
            return standardized_response(
                status_code=500,
                status_message="server_error",
                message="Failed to process task update. Please try again."
            )

    @extend_schema(
        summary="Delete Task",
        description="Delete a specific task and notify assignees.",
        responses={
            204: OpenApiExample(
                'Task Deleted',
                value={"detail": "Task has been deleted successfully."},
                response_only=True,
            ),
            403: OpenApiExample(
                'Forbidden',
                value={"detail": "You do not have permission to perform this action."},
                response_only=True,
            ),
            404: OpenApiExample(
                'Not Found',
                value={"detail": "Task not found."},
                response_only=True,
            ),
        }
    )
    def delete(self, request, *args, **kwargs):
        task = self.get_object()

        # Check if the current user is allowed to delete the task (project owner)
        if request.user != task.project.owner:
            return Response({"detail": "You do not have permission to perform this action."}, status=status.HTTP_403_FORBIDDEN)

        self.perform_destroy(task)
        return Response({"detail": "Task has been deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

    def perform_update(self, serializer):
        """
        Ensure that only the project owner can update the task.
        """
        task = serializer.instance
        request = self.request
        if request.user != task.project.owner:
            raise PermissionDenied("Only the project owner can update this task.")
        if not task.project.can_perform_activity:
            raise ValidationError(f"Can't update task of {task.project.status} project.")
        updated_task = serializer.save()
        add_assignees = serializer.context.get('new_assignees', [])
        remove_assignees = serializer.context.get('removed_assignees', [])
        print(remove_assignees)
        task_content_type = ContentType.objects.get_for_model(Task)

        # Notify users added to the task
        for assignee in add_assignees:
            send_real_time_notification(
                user=assignee,
                message={
                    "title": "Task Assigned",
                    "body": f"You have been assigned to the task '{updated_task.name}'.",
                    "url": request.build_absolute_uri(reverse('task-retrieve-update-destroy', kwargs={'pk': updated_task.id})),
                },
                notification_type="task",
                content_type=task_content_type.id,
                object_id=updated_task.id
            )
        
        # Notify users removed from the task
        for assignee in remove_assignees:
            send_real_time_notification(
                user=assignee,
                message={
                    "title": "Task Unassigned",
                    "body": f"You have been unassigned from the task '{updated_task.name}'.",
                    "url": request.build_absolute_uri(reverse('task-list-create')),
                },
                notification_type="task",
                content_type=task_content_type.id,
                object_id=updated_task.id
            )

    def perform_destroy(self, instance):
        """
        Delete the task and its associated task assignments.
        """
        task_content_type = ContentType.objects.get_for_model(Task)
        request = self.request
        for assignee in instance.assignments.all():
            send_real_time_notification.delay(
                user=assignee,
                message={
                    "title": "Task Deleted",
                    "body": f"The task '{instance.name}' has been deleted.",
                    "url": request.build_absolute_uri(reverse('task-list-create')),
                },
                notification_type="task",
                content_type=task_content_type.id,
                object_id=instance.id
            )
        TaskAssignment.objects.filter(task=instance).delete()
        instance.delete()
        
class TaskStatusChangeView(APIView):
    """
    API view for updating the task status without requiring approval.
    This view allows users to directly update the task status if the task 
    does not require approval and if the user is part of the task.
    """
    permission_classes = [IsAuthenticated, IsTaskAssignee | CanManageTask]

    @extend_schema(
        summary="Update Task Status",
        description="Update the status of a task if the user is assigned and the task does not require approval.",
        request=TaskStatusChangeSerializer,
        responses={
            200: OpenApiExample(
                'Success',
                value={"detail": "Task status updated successfully."},
                response_only=True,
            ),
            403: OpenApiExample(
                'Forbidden',
                value={"detail": "You must be assigned to the task to change its status."},
                response_only=True,
            ),
            404: OpenApiExample(
                'Not Found',
                value={"detail": "Task not found."},
                response_only=True,
            ),
            400: OpenApiExample(
                'Validation Error',
                value={"status": ["Invalid status value."]},
                response_only=True,
            ),
        },
    )
    def patch(self, request, pk):
        """
        Handles PATCH requests to update a task's status.

        Arguments:
            pk: The primary key of the task to be updated.

        Returns:
            Response with status code 200 for successful updates or 400 for failed validation.
        """
        try:
            task = Task.objects.get(id=pk)
        except Task.DoesNotExist:
            return Response({"detail": "Task not found."}, status=status.HTTP_404_NOT_FOUND)
        if not task.can_perform_activity:
            raise ValidationError(f"Can't update task of {task.project.status} project.")
        if task.need_approval:
            raise PermissionDenied("Task requires approval to change status.")
        
        if not TaskAssignment.objects.filter(task=task, user=request.user).exists():
            raise PermissionDenied("You must be assigned to the task to change its status.")

        serializer = TaskStatusChangeSerializer(task, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            request = self.request
            # Send notification to all assignees about the status change
            for assignee in task.assignees.all():
                send_real_time_notification.delay(
                    user=assignee,
                    message={
                        "title": "Task Status Updated",
                        "body": f"The status of the task '{task.name}' has been updated to '{serializer.validated_data['status']}'.",
                        "url": request.build_absolute_uri(reverse('task-retrieve-update-destroy', kwargs={'pk': task.id})),
                    },
                    notification_type="task",
                    content_type=ContentType.objects.get_for_model(Task).id,
                    object_id=task.id
                )
            return Response({"detail": "Task status updated successfully."}, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CommentListCreateView(ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsTaskAssignee | CanManageTask]
    filter_backends = [PermissionBasedFilterBackend, DjangoFilterBackend, filters.OrderingFilter, filters.SearchFilter]
    filterset_fields = ['task']
    ordering_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']
    search_fields = ['content', 'author__username']
    throttle_classes = [UserRateThrottle]

    def get_queryset(self):
        queryset = Comment.objects.select_related('author', 'task', 'task__project').prefetch_related('mentioned_users')
        
        # Handle parent_id filter
        parent_id = self.request.query_params.get('parent_id')
        if parent_id:
            queryset = queryset.filter(parent_id=parent_id)
        else:
            queryset = queryset.filter(parent=None)

        return queryset

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CommentCreateSerializer
        return CommentListSerializer

    @extend_schema(
        summary="List and Create Comments",
        description="Get a list of comments based on query parameters or create a new comment.",
        parameters=[
            OpenApiParameter(name='task_id', description='ID of the task', required=False, type=int),
            OpenApiParameter(name='project_id', description='ID of the project', required=False, type=int),
            OpenApiParameter(name='parent_id', description='ID of the parent comment for replies', required=False, type=int),
            OpenApiParameter(name='search', description='Search comments by content or author username', required=False, type=str),
            OpenApiParameter(name='page', description='Page number for pagination', required=False, type=int),
            OpenApiParameter(name='page_size', description='Number of items per page', required=False, type=int),
        ],
        responses={
            200: CommentListSerializer(many=True),
            201: CommentListSerializer,
            403: {"description": "Forbidden"},
        }
    )
    def post(self, request, *args, **kwargs):
        """
        Create a new comment after checking project status.
        """
        task_id = request.data.get('task')
        task = Task.objects.select_related('project').get(id=task_id)
        
        # Check project status
        if task.project.status == 'completed':
            return Response(
                {"error": "Cannot add comments to a completed project"},
                status=status.HTTP_403_FORBIDDEN
            )
            
        if task.project.status in ['not_started', 'on_hold']:
            return Response(
                {"error": f"Cannot add comments when project is {task.project.status}"},
                status=status.HTTP_403_FORBIDDEN
            )

        response = super().post(request, *args, **kwargs)
        if response.status_code == status.HTTP_201_CREATED:
            self.send_notifications(response.data['id'])
        return response

    def send_notifications(self, comment_id):
        comment = Comment.objects.select_related('parent', 'parent__author', 'task').get(id=comment_id)
        request = self.request
        content_type = ContentType.objects.get_for_model(Comment)

        for user in comment.mentioned_users.all():
            self.send_mention_notification(user, comment, request, content_type)

        if comment.parent and comment.parent.author != request.user:
            self.send_reply_notification(comment, request, content_type)

        # Notify task assignees about the new comment
        task_assignees = comment.task.assignments.exclude(user=request.user).select_related('user')
        for assignment in task_assignees:
            self.send_task_comment_notification(assignment.user, comment, request, content_type)

    def send_mention_notification(self, user, comment, request, content_type):
        send_real_time_notification(
            user=user,
            message={
                "title": "You were mentioned in a comment",
                "body": f"{request.user.username} mentioned you in a comment: '{comment.content[:50]}...'",
                "url": request.build_absolute_uri(reverse('comment-detail', kwargs={'pk': comment.id})),
            },
            notification_type="comment_mention",
            content_type=content_type.id,
            object_id=comment.id
        )

    def send_reply_notification(self, comment, request, content_type):
        send_real_time_notification(
            user=comment.parent.author,
            message={
                "title": "New Reply to Your Comment",
                "body": f"{request.user.username} replied to your comment: '{comment.content[:50]}...'",
                "url": request.build_absolute_uri(reverse('comment-detail', kwargs={'pk': comment.id})),
            },
            notification_type="comment_reply",
            content_type=content_type.id,
            object_id=comment.parent.id
        )

    def send_task_comment_notification(self, user, comment, request, content_type):
        send_real_time_notification(
            user=user,
            message={
                "title": "New Comment on Task",
                "body": f"{request.user.username} commented on task '{comment.task.name}': '{comment.content[:50]}...'",
                "url": request.build_absolute_uri(reverse('task-detail', kwargs={'pk': comment.task.id})),
            },
            notification_type="task_comment",
            content_type=content_type.id,
            object_id=comment.id
        )

class CommentDetailView(RetrieveUpdateDestroyAPIView):
    """
    API view to retrieve, update, or delete a specific comment.
    """
    queryset = Comment.objects.select_related('author', 'task', 'task__project').prefetch_related('mentioned_users')
    serializer_class = CommentDetailSerializer
    permission_classes = [IsAuthenticated, IsTaskAssignee | CanManageTask]
    throttle_classes = [UserRateThrottle]

    @extend_schema(
        summary="Retrieve, Update or Delete a Comment",
        description="Get details of a specific comment, update its content, or delete it.",
        responses={
            200: CommentDetailSerializer,
            204: None,
            403: OpenApiExample(
                'Forbidden',
                value={'detail': 'You do not have permission to perform this action.'},
                response_only=True,
            ),
        }
    )
    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """
        Handle GET request to retrieve comment details.
        """
        return super().get(request, *args, **kwargs)

    @extend_schema(
        summary="Update a Comment",
        description="Update the content of a specific comment.",
        responses={
            200: CommentDetailSerializer,
            403: OpenApiExample(
                'Forbidden',
                value={'detail': 'You do not have permission to perform this action.'},
                response_only=True,
            ),
        }
    )
    def put(self, request, *args, **kwargs):
        """
        Handle PUT request to update the comment and send notifications for new mentions.
        """
        comment = self.get_object()
        
        # Check project status
        if comment.task.project.status == 'completed':
            return Response(
                {"error": "Cannot update comments in a completed project"},
                status=status.HTTP_403_FORBIDDEN
            )
            
        if comment.task.project.status in ['not_started', 'on_hold']:
            return Response(
                {"error": f"Cannot update comments when project is {comment.task.project.status}"},
                status=status.HTTP_403_FORBIDDEN
            )

        original_mentioned_users = set(comment.mentioned_users.all())
        response = super().put(request, *args, **kwargs)

        if response.status_code == 200:
            updated_comment = self.get_object()
            updated_mentioned_users = set(updated_comment.mentioned_users.all())
            request = self.request
            new_mentions = updated_mentioned_users - original_mentioned_users
            
            for user in new_mentions:
                send_real_time_notification(
                    user=user,
                    message={
                        "title": "You were mentioned in a comment",
                        "body": f"{request.user.username} mentioned you in an updated comment: '{updated_comment.content}'",
                        "url": request.build_absolute_uri(reverse('comment-detail', kwargs={'pk': updated_comment.id})),
                    },
                    notification_type="task",
                    content_type=ContentType.objects.get_for_model(Comment).id,
                    object_id=updated_comment.id
                )

        return response

    @extend_schema(
        summary="Delete a Comment",
        description="Delete a specific comment.",
        responses={
            204: None,
            403: OpenApiExample(
                'Forbidden',
                value={'detail': 'You do not have permission to perform this action.'},
                response_only=True,
            ),
        }
    )
    def delete(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        """
        Handle DELETE request to delete the comment.
        """
        comment = self.get_object()
        if comment.author != request.user:
            return Response({"detail": "You do not have permission to delete this comment."}, status=status.HTTP_403_FORBIDDEN)
        return super().delete(request, *args, **kwargs)
class CommentRepliesView(ListAPIView):
    """
    Handles listing replies for a specific comment with pagination.
    """
    serializer_class = CommentListSerializer
    pagination_class = PageNumberPagination
    permission_classes = [IsAuthenticated, IsTaskAssignee | CanManageTask]
    def get_queryset(self):
        comment_id = self.kwargs['pk']
        return Comment.objects.filter(parent_id=comment_id).select_related('author')
class StatusChangeRequestListCreateView(ListCreateAPIView):
    """
    API view for listing and creating status change requests.
    """
    queryset = StatusChangeRequest.objects.all()
    serializer_class = StatusChangeRequestSerializer
    permission_classes = [IsAuthenticated, IsTaskAssignee | CanManageTask]
    
    throttle_classes = [UserRateThrottle]

    @extend_schema(
        summary="List Status Change Requests",
        description="Retrieve a paginated list of status change requests. Optionally filter by task or project ID.",
        parameters=[
            OpenApiParameter("task_id", OpenApiTypes.INT, description="Filter requests by Task ID"),
            OpenApiParameter("project_id", OpenApiTypes.INT, description="Filter requests by Project ID"),
        ],
        responses={
            200: StatusChangeRequestSerializer(many=True),
            404: OpenApiExample(
                "Not Found",
                value={"detail": "Task/Project not found."},
                response_only=True,
            ),
        }
    )
    def get_queryset(self):
        """
        Optionally filter status change requests by task or project.
        """
        queryset = StatusChangeRequest.objects.select_related('task', 'user')
        task_id = self.request.query_params.get('task_id')
        project_id = self.request.query_params.get('project_id')

        if task_id:
            # Check if the user is assigned to the task
            if not Task.objects.filter(
                id=task_id,
                assignments__user=self.request.user
            ).exists():
                raise PermissionDenied(detail="You are not assigned to this task.")
            queryset = queryset.filter(task__id=task_id)

        if project_id:
            # Check if the user is part of the project or the owner
            if not Project.objects.filter(
                Q(id=project_id) & 
                (Q(owner=self.request.user) | Q(memberships__user=self.request.user))
            ).exists():
                raise PermissionDenied(detail="You are not a member of this project or the owner.")
            queryset = queryset.filter(task__project__id=project_id)

        return queryset

    @extend_schema(
        summary="Create Status Change Request",
        description="Create a new status change request for a task.",
        request=StatusChangeRequestSerializer,
        responses={
            201: StatusChangeRequestSerializer,
            400: OpenApiExample(
                "Validation Error",
                value={"detail": "Invalid data."},
                response_only=True,
            ),
        }
    )
    def perform_create(self, serializer):
        """
        Automatically set the user making the request as the creator.
        """
        project = serializer.validated_data['task'].project
        if project.status == 'completed':
            raise ValidationError("Cannot create status change requests for completed projects.")
        if project.status == 'on_hold':
            raise ValidationError("Cannot create status change requests for on hold projects.")
        status_request = serializer.save(user=self.request.user)
        request = self.request
        send_real_time_notification(
            user=status_request.task.assigned_by,
            message={
                "title": "Status Change Request",
                "body": f"'{self.request.user}' created a status change request for task: '{status_request.task.name}'.",
                "url": request.build_absolute_uri(reverse('status-change-request-retrieve-update-destroy', kwargs={'pk': status_request.task.id}))
            },
            notification_type="task",
            content_type=ContentType.objects.get_for_model(StatusChangeRequest).id,
            object_id=status_request.id
        )

class StatusChangeRequestRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    """
    API view for retrieving, updating, or deleting a specific status change request.
    """
    queryset = StatusChangeRequest.objects.all()
    serializer_class = StatusChangeRequestSerializer
    permission_classes = [IsAuthenticated, IsTaskAssignee | CanManageTask]

    @extend_schema(
        summary="Retrieve Status Change Request",
        description="Retrieve details of a specific status change request by its ID.",
        responses={
            200: StatusChangeRequestSerializer,
            404: OpenApiExample(
                "Not Found",
                value={"detail": "Status change request not found."},
                response_only=True,
            ),
        }
    )
    def get(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        summary="Update Status Change Request",
        description="Update details of a status change request (excluding approval/rejection logic).",
        request=StatusChangeRequestSerializer,
        responses={
            200: StatusChangeRequestSerializer,
            400: OpenApiExample(
                "Validation Error",
                value={"detail": "Invalid data."},
                response_only=True,
            ),
        }
    )
    def perform_update(self, serializer):
        project = serializer.instance.task.project
        if project.status == 'completed':
            raise ValidationError("Cannot update status change requests for completed projects.")
        if project.status == 'on_hold':
            raise ValidationError("Cannot update status change requests for on hold projects.")
        super().perform_update(serializer)

    @extend_schema(
        summary="Delete Status Change Request",
        description="Delete a specific status change request.",
        responses={
            204: None,
            404: OpenApiExample(
                "Not Found",
                value={"detail": "Status change request not found."},
                response_only=True,
            ),
        }
    )
    def delete(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


class StatusChangeRequestAcceptRejectView(APIView):
    """
    API view for accepting or rejecting a status change request.
    """
    permission_classes = [IsAuthenticated, CanManageTask]
    serializer_class = StatusChangeActionSerializer
    @extend_schema(
        summary="Accept/Reject Status Change Request",
        description="Approve or reject a pending status change request.",
        request=StatusChangeActionSerializer,
        responses={
            200: StatusChangeRequestSerializer,
            400: OpenApiExample(
                "Invalid Action",
                value={"detail": "Invalid action. Must be 'accept' or 'reject'."},
                response_only=True,
            ),
            404: OpenApiExample(
                "Not Found",
                value={"detail": "Status change request not found."},
                response_only=True,
            ),
        }
    )

    def post(self, request, pk):
        try:
            status_change_request = StatusChangeRequest.objects.get(id=pk)
            action = request.data.get('action')

            if action not in ['accept', 'reject']:
                return standardized_response(
                    status_code=400,
                    status_message="validation_error",
                    message="Invalid action. Must be 'accept' or 'reject'."
                )

            if status_change_request.status != 'pending':
                return standardized_response(
                    status_code=400,
                    status_message="validation_error",
                    message="This status change request is not pending."
                )

            # Process the action
            if action == 'accept':
                status_change_request.status = 'approved'
                status_change_request.task.status = 'completed'
                status_change_request.approved_by = request.user
                status_change_request.task.save()
            else:
                status_change_request.status = 'rejected'

            status_change_request.save()
            request = self.request
            # Send notification
            send_real_time_notification(
                user=status_change_request.user,
                message={
                    "title": "Status Change Request Update",
                    "body": f"Your status change request for '{status_change_request.task.name}' has been '{action}'ed.",
                    "url": request.build_absolute_uri(reverse('accept-reject-status-change-request', kwargs={'pk': status_change_request.id}))
                },
                notification_type="task",
                content_type=ContentType.objects.get_for_model(StatusChangeRequest).id,
                object_id=status_change_request.id
            )

            serializer = StatusChangeRequestSerializer(status_change_request)
            return standardized_response(
                status_code=200,
                status_message="success",
                message=f"Status change request {action}ed successfully.",
                data=serializer.data
            )

        except StatusChangeRequest.DoesNotExist:
            return standardized_response(
                status_code=404,
                status_message="not_found",
                message="Status change request not found."
            )
        except PermissionDenied as e:
            return standardized_response(
                status_code=403,
                status_message="permission_denied",
                message=str(e)
            )
        except Exception as e:
            return standardized_response(
                status_code=500,
                status_message="server_error",
                message="Failed to process status change request."
            )