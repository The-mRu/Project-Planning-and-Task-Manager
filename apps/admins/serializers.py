from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from rest_framework import serializers

from apps.admins.models import AdminActionLog
from apps.notifications.models import Notification
from apps.projects.models import Project, ProjectMembership, ProjectInvitation
from apps.projects.serializers import (
    DetailedProjectMembershipSerializer,ProjectCreateSerializer,
    ProjectListSerializer,ProjectMembershipSerializer,
    ProjectSerializer,ProjectUpdateSerializer
)
from apps.subscriptions.models import Payment, Subscription, SubscriptionPlan
from apps.tasks.models import Comment, StatusChangeRequest, Task,TaskAssignment
from apps.tasks.serializers import (
    CommentListSerializer,StatusChangeRequestSerializer,
    TaskCreateSerializer, TaskDetailSerializer,
    TaskListSerializer,TaskUpdateSerializer
)
from apps.users.models import Profile

User = get_user_model()

class AdminProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for the Profile model.
    Includes fields related to the user's profile, such as address, city, and country.
    """
    class Meta:
        model = Profile
        fields = ['address', 'city', 'country', 'date_of_birth', 'profile_picture', 'phone_number', 
                    'owned_projects_count', 'participated_projects_count']
        read_only_fields = ['owned_projects_count', 'participated_projects_count']

class AdminUserListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing users with minimal data.
    Only essential fields are included for the list view.
    """
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'role', 'is_active']  # Minimal fields for list view

class AdminUserDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for the User model with a nested Profile serializer.
    Allows detailed view of the user along with their profile information.
    """
    profile = AdminProfileSerializer(required=False)  # Include Profile as a nested serializer

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'role', 'is_staff', 'is_active', 'email_verified', 
                    'pending_email', 'date_joined', 'last_login', 'last_seen', 'profile']
        read_only_fields = ['date_joined', 'last_login', 'last_seen']

    def create(self, validated_data):
        """
        Override the create method to handle nested profile creation.
        Ensures the user is created first, followed by the profile.
        """
        profile_data = validated_data.pop('profile', {})  # Extract profile data
        user = super().create(validated_data)  # Create the user instance
        Profile.objects.create(user=user, **profile_data)  # Create associated profile
        return user
    
    def update(self, instance, validated_data):
        """
        Custom update method to handle nested Profile updates.
        Updates user fields first, then updates profile if profile data is present.
        """
        profile_data = validated_data.pop('profile', None)  # Extract profile data if present
        for attr, value in validated_data.items():
            setattr(instance, attr, value)  # Update User fields
        instance.save()

        # Update Profile fields if profile data exists
        if profile_data:
            profile_instance = instance.profile
            for attr, value in profile_data.items():
                setattr(profile_instance, attr, value)
            profile_instance.save()

        return instance

class AdminProjectMembershipSerializer(DetailedProjectMembershipSerializer):
    """
    Serializer for project memberships with additional fields for admin view.
    Inherits from DetailedProjectMembershipSerializer and adds the 'role' field.
    """
    class Meta(DetailedProjectMembershipSerializer.Meta):
        fields = ['project'] + DetailedProjectMembershipSerializer.Meta.fields + ['role']

class AdminProjectMembershipCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating project memberships with validation.
    Ensures that a user is not added to a project if they are already a member.
    """
    class Meta:
        model = ProjectMembership
        fields = ['id', 'project', 'user', 'role']
        read_only_fields = ['id']

    def validate(self, data):
        """
        Custom validation for ensuring a user is not already a member of the project.
        """
        project = data.get('project')
        user = data.get('user')
        
        # Check if this is an update operation
        if self.instance:
            # For updates, we only need to validate if the project or user is being changed
            if (project and project != self.instance.project) or (user and user != self.instance.user):
                if ProjectMembership.objects.filter(project=project, user=user).exclude(id=self.instance.id).exists():
                    raise serializers.ValidationError("This user is already a member of the project.")
        else:
            # For create operations, check if the membership already exists
            if ProjectMembership.objects.filter(project=project, user=user).exists():
                raise serializers.ValidationError("This user is already a member of the project.")
        
        return data
    
class AdminProjectListSerializer(ProjectListSerializer):
    """
    Serializer for listing projects with additional field for the owner's username.
    """
    owner = serializers.CharField(source='owner.username')

    class Meta(ProjectListSerializer.Meta):
        fields = ProjectListSerializer.Meta.fields + ['owner']

class AdminProjectDetailSerializer(ProjectSerializer):
    """
    Serializer for retrieving detailed information about a project with memberships.
    """
    members = ProjectMembershipSerializer(source='memberships', many=True, read_only=True)
    owner = serializers.CharField(source='owner.username')

    class Meta(ProjectSerializer.Meta):
        fields = ProjectSerializer.Meta.fields + ['updated_at']

class AdminProjectCreateSerializer(ProjectCreateSerializer):
    """
    Serializer for creating projects with additional logic for assigning the owner.
    Includes validation for the number of members allowed by the owner's subscription plan.
    """
    owner = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)

    class Meta(ProjectCreateSerializer.Meta):
        fields = ProjectCreateSerializer.Meta.fields + ['owner']
        json_encoder = DjangoJSONEncoder

    def create(self, validated_data):
        """
        Custom create method for handling project creation with validation on member count.
        Ensures the project owner and members are within the limits of their subscription plan.
        """
        members = validated_data.pop('members', [])
        owner = validated_data.pop('owner', None)

        if owner:
            # If an owner is specified, use it
            validated_data['owner'] = owner
        else:
            # If no owner is specified, use the authenticated user (admin)
            owner = self.context['request'].user

        # Check if owner has reached the maximum number of projects
        subscription = owner.subscription
        plan = subscription.plan if subscription else None
        if plan and plan.max_members_per_project > 1:
            if len(members) > plan.max_members_per_project:
                raise serializers.ValidationError("Owner has exceeded the maximum number of members allowed by their plan.")
        if Project.objects.filter(owner=owner).count() >= plan.max_projects:
            raise serializers.ValidationError("Owner has exceeded the maximum number of projects allowed by their plan.")

        # Create the project
        project = Project.objects.create(**validated_data)

        # Ensure the owner is added as a member with 'owner' role
        ProjectMembership.objects.create(project=project, user=owner, role='owner')

        # Add other members
        for member in members:
            if member != owner:
                ProjectMembership.objects.create(project=project, user=member, role='member')

        # Update total_member_count
        project.total_member_count = ProjectMembership.objects.filter(project=project).count()
        project.save()

        return project

    def to_representation(self, instance):
        """
        Custom representation method to return a serialized project with the specified serializer.
        """
        return ProjectSerializer(instance).data

class AdminProjectUpdateSerializer(ProjectUpdateSerializer):
    """
    Admin serializer for updating projects with special handling for ownership and membership updates.
    Allows the assignment of a new owner and manages membership roles accordingly.
    """
    owner = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)

    class Meta(ProjectUpdateSerializer.Meta):
        fields = ProjectUpdateSerializer.Meta.fields + ['owner']

    def update(self, instance, validated_data):
        """
        Custom update method to handle changes in ownership and membership.
        Ensures that the new owner is added correctly and roles are updated.
        """
        new_owner = validated_data.pop('owner', None)
        members = validated_data.get('members', None)

        # If the owner is being updated, move ownership and update memberships
        if new_owner and new_owner != instance.owner:
            old_owner = instance.owner
            instance.owner = new_owner
            instance.save()
            # Update memberships for the old owner and new owner
            ProjectMembership.objects.filter(project=instance, user=old_owner).update(role='member')
            ProjectMembership.objects.update_or_create(project=instance, user=new_owner, defaults={'role': 'owner'})

        # If members are being updated and the new owner isn't already a member, add them
        if members is not None and new_owner and new_owner.id not in [member.id for member in members]:
            members.append(new_owner)
            validated_data['members'] = members

        # Set the admin_override flag if the member count exceeds the plan limit
        owner = instance.owner
        subscription = owner.subscription
        plan = subscription.plan if subscription else None
        if plan and members and len(members) > plan.max_members_per_project:
            instance.admin_override = True
            instance.save()

        return super().update(instance, validated_data)

class AdminTaskListSerializer(TaskListSerializer):
    """
    Admin version of TaskListSerializer with additional fields for admins.
    Inherits from the standard TaskListSerializer, but may include more details for administrative use.
    """
    class Meta(TaskListSerializer.Meta):
        fields = TaskListSerializer.Meta.fields

class AdminTaskDetailSerializer(TaskDetailSerializer):
    """
    Admin version of TaskDetailSerializer providing additional administrative details,
    such as task approval and project association.
    """
    approved_by = serializers.StringRelatedField()  # Admin can see who approved the task
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())  # Admin can view or set the project

    class Meta(TaskDetailSerializer.Meta):
        fields = TaskDetailSerializer.Meta.fields + ['created_at', 'updated_at']  # Include timestamps for tracking task lifecycle

class AdminTaskCreateSerializer(TaskCreateSerializer):
    """
    Admin version of TaskCreateSerializer, with additional control over task creation, 
    such as optional task approval by an admin.
    """
    approved_by = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)  # Admin can specify who approved the task

    class Meta(TaskCreateSerializer.Meta):
        fields = TaskCreateSerializer.Meta.fields
        json_encoder = DjangoJSONEncoder  # Custom JSON encoding to handle complex data structures

    def create(self, validated_data):
        """
        Custom create method for tasks allowing optional pre-approval by an admin.
        """
        approved_by = validated_data.pop('approved_by', None)
        task = super().create(validated_data)
        if approved_by:
            task.approved_by = approved_by  # If specified, set the task's approved_by field
            task.save()
        return task



class AdminTaskUpdateSerializer(TaskUpdateSerializer):
    """
    Admin serializer for updating tasks with additional control over fields like
    approval, project assignment, assignees, and assignment by admin.
    """
    approved_by = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), required=False)
    assigned_by = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)

    class Meta(TaskUpdateSerializer.Meta):
        fields = TaskUpdateSerializer.Meta.fields + ['approved_by', 'total_assignees', 'assigned_by']
        json_encoder = DjangoJSONEncoder

    def validate_assignees(self, assignees):
        """
        Custom validation to ensure that all assignees are members of the project.
        """
        project = self.instance.project
        project_members = set(project.memberships.values_list('user_id', flat=True))
        invalid_users = [user.id for user in assignees if user.id not in project_members]
        if invalid_users:
            raise serializers.ValidationError(f"Users {invalid_users} are not members of the project")
        return assignees

    def update(self, instance, validated_data):
        """
        Custom update method to handle updates to task, project, assignees, approval, and assignment.
        Supports transaction management to ensure data integrity.
        """
        approved_by = validated_data.pop('approved_by', None)
        assigned_by = validated_data.pop('assigned_by', None)
        project = validated_data.pop('project', None)
        assignees = validated_data.get('assignees', None)

        with transaction.atomic():
            # Handle project change and revalidate assignees if the project changes
            if project and project != instance.project:
                instance.project = project
                if assignees:
                    self.validate_assignees(assignees)

            # Handle assignees update: add/remove assignees as necessary
            if assignees is not None:
                current_assignees = set(instance.assignments.values_list('user_id', flat=True))
                new_assignees = set(user.id for user in assignees)

                if current_assignees != new_assignees:
                    to_remove = current_assignees - new_assignees
                    to_add = new_assignees - current_assignees

                    if to_remove:
                        TaskAssignment.objects.filter(task=instance, user_id__in=to_remove).delete()
                    if to_add:
                        TaskAssignment.objects.bulk_create([
                            TaskAssignment(task=instance, user_id=user_id)
                            for user_id in to_add
                        ])
                    instance.total_assignees = len(new_assignees)

            # Handle fields that are part of the parent serializer
            task = super().update(instance, validated_data)

            # Update admin-specific fields (approval, assignment by admin)
            update_fields = []
            if approved_by:
                task.approved_by = approved_by
                update_fields.append('approved_by')
                task.status = 'completed'  # Automatically set status to 'completed' if approved
                update_fields.append('status')
            if assigned_by:
                task.assigned_by = assigned_by
                update_fields.append('assigned_by')

            if update_fields:
                task.save(update_fields=update_fields)

            # Return a fresh instance of the task with all related data
            return Task.objects.select_related(
                'project', 'assigned_by', 'approved_by'
            ).prefetch_related(
                'assignments__user'
            ).get(id=task.id)

    def to_representation(self, instance):
        """
        Custom representation to return a serialized task with detailed info including approval and assignment.
        """
        return AdminTaskDetailSerializer(instance, context=self.context).data


class AdminTaskBulkUpdateSerializer(serializers.Serializer):
    """
    Serializer to update multiple tasks in bulk, such as changing due date, project, or status.
    """
    task_ids = serializers.ListField(child=serializers.IntegerField())
    due_date = serializers.DateTimeField(required=False)
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), required=False)
    status = serializers.ChoiceField(choices=Task.STATUS_CHOICES, required=False)

    class Meta:
        json_encoder = DjangoJSONEncoder

    def validate_due_date(self, value):
        """
        Custom validation for due date, ensuring it's not in the past.
        """
        if value and value < timezone.now():
            raise serializers.ValidationError("Due date cannot be in the past.")
        return value


class AdminTaskBulkAssignSerializer(serializers.Serializer):
    """
    Serializer for bulk assigning users to multiple tasks.
    Validates the assignees to ensure they are valid members of the respective project.
    """
    task_ids = serializers.ListField(child=serializers.IntegerField())
    user_ids = serializers.ListField(child=serializers.IntegerField())

    def validate(self, data):
        """
        Validate the task IDs, user IDs, and ensure that the users are members of the respective project.
        """
        tasks = Task.objects.filter(id__in=data['task_ids'])
        users = User.objects.filter(id__in=data['user_ids'])
        
        # Check if all provided task IDs are valid
        if tasks.count() != len(data['task_ids']):
            raise serializers.ValidationError("Some task IDs are invalid")
            
        # Check if all provided user IDs are valid
        if users.count() != len(data['user_ids']):
            raise serializers.ValidationError("Some user IDs are invalid")

        # Ensure users are members of the respective projects
        for task in tasks:
            project_members = task.project.memberships.values_list('user_id', flat=True)
            invalid_users = [user.id for user in users if user.id not in project_members]
            if invalid_users:
                raise serializers.ValidationError(f"Users {invalid_users} are not members of project for task {task.id}")

        return data


class AdminTaskBulkUnassignSerializer(serializers.Serializer):
    """
    Serializer for bulk unassigning users from tasks.
    Validates that users are currently assigned to the tasks.
    """
    task_ids = serializers.ListField(child=serializers.IntegerField())
    user_ids = serializers.ListField(child=serializers.IntegerField())

    def validate(self, data):
        """
        Validate the task IDs and user IDs, ensuring the users are assigned to the tasks.
        """
        tasks = Task.objects.filter(id__in=data['task_ids'])
        
        # Verify that users are currently assigned to the provided tasks
        task_assignments = TaskAssignment.objects.filter(
            task_id__in=data['task_ids'],
            user_id__in=data['user_ids']
        ).values_list('task_id', 'user_id')
        
        # If no valid assignments are found, raise an error
        if not task_assignments:
            raise serializers.ValidationError("No matching task assignments found")
            
        return data


class AdminTaskStatusChangeRequestListSerializer(StatusChangeRequestSerializer):
    """
    Serializer for listing status change requests for tasks. 
    It includes task and user primary keys for easy reference.
    """
    task = serializers.PrimaryKeyRelatedField(queryset=Task.objects.all())  # For listing, show task PK
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())  # For listing, show user PK

    class Meta:
        model = StatusChangeRequest
        fields = ['id', 'task', 'status', 'user']  # List only the relevant fields for task status change requests


class AdminTaskStatusChangeRequestDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for showing detailed information about a specific status change request.
    """
    task = serializers.PrimaryKeyRelatedField(queryset=Task.objects.all())
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    approved_by = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())

    class Meta:
        model = StatusChangeRequest
        fields = [
            'id', 'request_time', 'reason', 'status', 'resolution_time',
            'approved_by', 'task', 'user',
        ]
        read_only_fields = ['id', 'request_time', 'resolution_time']  # These fields are read-only

    def validate(self, data):
        """
        Custom validation logic for creation of new status change requests.
        Ensures that the user is assigned to the task.
        """
        if self.instance:  # If instance exists (i.e., on update), skip validation
            return data

        task = data.get('task')
        user = data.get('user')

        # Ensure that the user is assigned to the task
        if not task.assignments.filter(user=user).exists():
            raise serializers.ValidationError(
                f"User with ID {user.id} is not assigned to the task with ID {task.id}."
            )

        return data

    def create(self, validated_data):
        """
        Handles the creation of a new status change request. 
        Inherits from the parent class's create method.
        """
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """
        Handles the updating of an existing status change request. 
        Updates the task's status based on the request's status.
        """
        status = validated_data.get('status', instance.status)
        approved_by = validated_data.get('approved_by', None) or self.context['request'].user

        # Handle approved status change: approve the request and mark task as completed
        if status == 'approved':
            instance.approve(approved_by)
            instance.task.status = 'completed'
            instance.task.approved_by = approved_by
            instance.task.save()
        
        # Handle rejected status change: reject the request and mark task as pending
        elif status == 'rejected':
            instance.reject(approved_by)
            instance.task.status = 'pending'
            instance.task.approved_by = None
            instance.task.save()
        
        # Handle pending status change: revert task status to in_progress
        elif status == 'pending':
            instance.task.status = 'in_progress'
            instance.task.approved_by = None
            instance.status = 'pending'
            instance.approved_by = None
            instance.save()
            instance.task.save()
        
        # Allow updating the user if provided
        instance.user = validated_data.get('user', instance.user)
        instance.save()

        return instance

    def to_representation(self, instance):
        """
        Custom representation to convert `request_time` and `resolution_time` to ISO 8601 format.
        """
        representation = super().to_representation(instance)
        # Convert `request_time` and `resolution_time` to ISO format
        representation['request_time'] = instance.request_time.isoformat()
        if instance.resolution_time:
            representation['resolution_time'] = instance.resolution_time.isoformat()
        return representation


class AdminSubscriptionPlanSerializer(serializers.ModelSerializer):
    """
    Serializer for SubscriptionPlan model, used in the admin interface for managing subscription plans.
    """
    class Meta:
        model = SubscriptionPlan
        fields = '__all__'  # Include all fields in the SubscriptionPlan model


class AdminPaymentHistorySerializer(serializers.ModelSerializer):
    """
    Serializer for Payment model to show payment history details, including amount and related payment intent.
    """
    class Meta:
        model = Payment
        fields = ['id', 'amount', 'date', 'stripe_payment_intent_id']  # Show basic payment details


class AdminSubscriptionListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing subscriptions, including user and plan details.
    Also includes a custom `status` field to show the current status of the subscription.
    """
    user = serializers.StringRelatedField()  # Display user as a string (user's string representation)
    plan = AdminSubscriptionPlanSerializer(read_only=True)  # Show plan details (read-only)
    status = serializers.SerializerMethodField()  # Custom field to show subscription status

    class Meta:
        model = Subscription
        fields = ['id', 'user', 'plan', 'start_date', 'end_date', 'is_active', 'status']  # Include relevant fields

    def get_status(self, obj):
        """
        Custom method to determine the status of the subscription:
        - 'active' if the subscription is active and not expired
        - 'expired' if the subscription has passed its end date
        - 'cancelled' if the subscription is marked as inactive
        """
        if not obj.is_active:
            return 'cancelled'
        if obj.end_date < timezone.now():
            return 'expired'
        return 'active'  # Default to 'active' if the subscription is ongoing


class AdminSubscriptionDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for providing detailed information about a user's subscription, including 
    payment history, usage stats, and associated plan details.
    """
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())  # Referencing the user associated with the subscription
    plan = AdminSubscriptionPlanSerializer(read_only=True)  # Read-only subscription plan details
    payment_history = AdminPaymentHistorySerializer(source='payments', many=True, read_only=True)  # List of payments made under the subscription
    usage_stats = serializers.SerializerMethodField()  # Custom field for showing subscription usage statistics

    class Meta:
        model = Subscription
        fields = [
            'id', 'user', 'plan', 'start_date', 'end_date', 'is_active',
                'payment_history', 'usage_stats'  # Fields to be included in the serialized output
        ]

    def get_usage_stats(self, obj):
        """
        Calculates and returns usage statistics for the subscription.
        - `total_projects`: The number of projects owned by the user.
        - `total_members`: The number of memberships the user has across projects.
        - `plan_limits`: Subscription limits (e.g., max projects and members per project) based on the plan.
        """
        return {
            'total_projects': Project.objects.filter(owner=obj.user).count(),  # Count of projects the user owns
            'total_members': ProjectMembership.objects.filter(user=obj.user).count(),  # Count of memberships the user has
            'plan_limits': {
                'max_projects': obj.plan.max_projects,  # Maximum number of projects allowed by the plan
                'max_members_per_project': obj.plan.max_members_per_project  # Max number of members allowed per project
            }
        }


class NotificationAdminSerializer(serializers.ModelSerializer):
    """
    Serializer for representing notifications in the admin interface.
    """
    class Meta:
        model = Notification
        fields = '__all__'  # Include all fields from the Notification model


class AdminActionLogSerializer(serializers.ModelSerializer):
    """
    Serializer for action logs performed by admin users, including user details and content type.
    """
    user = serializers.StringRelatedField()  # String representation of the user associated with the action log
    content_type = serializers.StringRelatedField()  # String representation of the content type of the action

    class Meta:
        model = AdminActionLog
        fields = '__all__'  # Include all fields from the AdminActionLog model


class AdminTaskAssignmentSerializer(serializers.ModelSerializer):
    """
    Serializer for task assignments, used to represent assignment details in the admin interface.
    """
    class Meta:
        model = TaskAssignment
        fields = '__all__'  # Include all fields from the TaskAssignment model


class AdminCommentListSerializer(CommentListSerializer):
    """
    Serializer for listing comments in the admin interface, with additional information about the project and rendered content.
    """
    project = serializers.SerializerMethodField()  # Custom field to provide project details for each comment
    rendered_content = serializers.SerializerMethodField()  # Custom field to render comment content

    class Meta(CommentListSerializer.Meta):
        fields = CommentListSerializer.Meta.fields + ['project', 'rendered_content']  # Add `project` and `rendered_content` fields to the base list

    def get_project(self, obj):
        """
        Retrieves the project associated with the comment's task.
        Returns a dictionary with the project's ID and name.
        """
        return {'id': obj.task.project.id, 'name': obj.task.project.name}

    def get_rendered_content(self, obj):
        """
        Renders the content of the comment (usually HTML or formatted text).
        """
        return obj.get_rendered_content()  # Assumes `get_rendered_content` method exists in the model


class AdminCommentDetailSerializer(serializers.ModelSerializer):
    """
    Serializer to represent a detailed view of a comment in the admin interface,
    including related task, project, and user information, as well as content rendering.
    """
    author = serializers.PrimaryKeyRelatedField(read_only=True)  # The author of the comment (read-only)
    mentioned_users = serializers.PrimaryKeyRelatedField(many=True, read_only=True)  # Users mentioned in the comment (read-only)
    task = serializers.SerializerMethodField()  # Custom field for task details
    project = serializers.SerializerMethodField()  # Custom field for project details
    has_replies = serializers.SerializerMethodField()  # Custom field to check if the comment has replies
    rendered_content = serializers.SerializerMethodField()  # Custom field for rendered content

    class Meta:
        model = Comment
        fields = [
            'id', 'task', 'project', 'author', 'content', 'rendered_content',
            'created_at', 'updated_at', 'mentioned_users', 'parent', 
            'reply_count', 'mention_count', 'has_replies'
        ]
        read_only_fields = [
            'id', 'author', 'created_at', 'updated_at', 
            'reply_count', 'mention_count', 'rendered_content'
        ]

    def get_task(self, obj):
        """
        Retrieves the task associated with the comment.
        Returns a dictionary with the task's ID and name.
        """
        return {'id': obj.task.id, 'name': obj.task.name}

    def get_project(self, obj):
        """
        Retrieves the project associated with the comment's task.
        Returns a dictionary with the project's ID and name.
        """
        return {'id': obj.task.project.id, 'name': obj.task.project.name}

    def get_has_replies(self, obj):
        """
        Checks if the comment has any replies by evaluating the `reply_count`.
        Returns `True` if there are replies, `False` otherwise.
        """
        return obj.reply_count > 0

    def get_rendered_content(self, obj):
        """
        Renders the comment content into HTML and also provides raw content and mentions.
        Returns a dictionary with raw content, HTML content, and mentioned users.
        """
        return {
            'raw': obj.content,  # The raw content of the comment
            'html': obj.get_rendered_content(),  # The HTML-rendered content of the comment
            'mentions': [
                {'id': user.id, 'username': user.username} 
                for user in obj.mentioned_users.all()  # List of mentioned users with their ID and username
            ]
        }


class AdminCommentCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and updating comments, with validation logic for task, parent,
    and nesting of comments up to a certain depth.
    """
    MAX_DEPTH = 3  # Maximum allowed nesting depth for replies

    class Meta:
        model = Comment
        fields = ['id', 'task', 'author', 'content', 'parent']  # Fields for comment creation and update
        read_only_fields = ['id']  # ID is read-only during creation and update

    def validate(self, attrs):
        """
        Custom validation logic for creating or updating a comment.
        - Ensures that a task is provided.
        - Validates the parent comment (if provided) to ensure it belongs to the same task and respects the max depth.
        """
        task = attrs.get('task')
        parent = attrs.get('parent')
        content = attrs.get('content')

        # Ensure that the task field is present
        if not task:
            raise serializers.ValidationError({"task": "Task is required."})

        # If the comment is a reply, validate the parent comment
        if parent:
            # Check if the parent comment belongs to the same task
            if parent.task != task:
                raise serializers.ValidationError(
                    {"parent": "The parent comment must belong to the same task."}
                )

            # Ensure the nesting depth does not exceed the maximum depth
            current_depth = 1  # Start from the current comment level
            while parent:
                current_depth += 1  # Move to the parent comment's level
                parent = parent.parent  # Go to the parent of the parent comment
                if current_depth > self.MAX_DEPTH:
                    raise serializers.ValidationError(
                        {"parent": f"Cannot nest comments more than {self.MAX_DEPTH} levels deep."}
                    )

        return attrs

    def create(self, validated_data):
        """
        Handles the creation of a new comment. After creation, processes mentions.
        """
        comment = Comment.objects.create(**validated_data)  # Create the comment instance
        comment.process_mentions()  # Process any user mentions in the comment
        return comment

    def update(self, instance, validated_data):
        """
        Updates an existing comment and processes mentions.
        """
        instance = super().update(instance, validated_data)  # Update the comment using the parent method
        instance.process_mentions()  # Re-process mentions in case the content was updated
        return instance

    def to_representation(self, instance):
        """
        Custom representation for the comment instance. Uses the `AdminCommentDetailSerializer`
        to convert the instance into a detailed representation.
        """
        return AdminCommentDetailSerializer(instance, context=self.context).data  # Return the detailed serializer data

class AdminProjectInvitationSerializer(serializers.ModelSerializer):
    # Field to accept a list of emails for bulk invitations (write-only).
    email = serializers.ListField(
        child=serializers.EmailField(),
        write_only=True
    )
    
    # Optional field to specify the inviter's email.
    inviter_email = serializers.EmailField(required=False)

    class Meta:
        model = ProjectInvitation
        fields = ['project', 'email', 'inviter_email']

    def validate(self, data):
        """
        Custom validation to ensure that project members who are already part of the project
        are excluded from the invitations.

        Args:
            data: Dictionary containing 'project', 'email', and 'inviter_email'.

        Returns:
            The validated data with the list of emails filtered and existing members added.
        """
        project = data['project']
        emails = data['email']
        
        # Get a list of existing project members' emails to exclude from the invitation list.
        existing_members = ProjectMembership.objects.filter(
            project=project,
            user__email__in=emails
        ).values_list('user__email', flat=True)
        
        # Filter out emails that belong to existing members.
        if existing_members:
            emails = [email for email in emails if email not in existing_members]
            data['email'] = emails
        
        # Add the list of existing members to the validated data for later use.
        data['existing_members'] = existing_members
        return data

    def create(self, validated_data):
        """
        Create project invitations for the provided email addresses, while excluding
        existing project members. Adds the existing members to the context for use in views.

        Args:
            validated_data: Dictionary containing the validated data, 
                            including the project,
                            email list, and inviter's email.

        Returns:
            A list of created invitations.
        """
        project = validated_data['project']
        emails = validated_data['email']
        inviter = None
        
        # Retrieve the list of existing members from the validated data
        existing_members = validated_data['existing_members']

        # If an inviter email is provided, use that to find the inviter; otherwise, use the current user.
        if 'inviter_email' in validated_data:
            try:
                inviter = User.objects.get(email=validated_data['inviter_email'])
            except User.DoesNotExist:
                # Raise an error if the inviter email does not exist.
                raise serializers.ValidationError("Specified inviter email does not exist")
        
        # Default to the current authenticated user if no inviter is specified.
        if not inviter:
            inviter = self.context['request'].user
            
        # Create invitations for each email in the filtered list.
        invitations = []
        for email in emails:
            invitation = ProjectInvitation.objects.create(
                project=project,
                email=email,
                invited_by=inviter,
                expires_at=timezone.now() + timedelta(days=7)  # Set expiration for 7 days.
            )
            invitations.append(invitation)
        
        # Store the existing members list in the context to send it back in the response.
        self.context['existing_members'] = existing_members
        
        return invitations