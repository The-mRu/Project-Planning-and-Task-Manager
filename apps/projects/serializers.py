# local imports
from apps.projects.models import Project, ProjectMembership, ProjectInvitation
from apps.users.serializers import CustomUserSerializer, DetailedUserSerializer
# django imports
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from django.urls import reverse
# third-party imports
from datetime import timedelta
from rest_framework import serializers



User = get_user_model()


# Serializer for ProjectMembership
class ProjectMembershipSerializer(serializers.ModelSerializer):
    user = serializers.CharField(source='user.username')  # Display username instead of the full user object
    membership_url = serializers.SerializerMethodField()  # URL for the membership detail

    class Meta:
        model = ProjectMembership
        fields = ['id', 'user', 'joined_at', 'membership_url', 'role']

    def get_membership_url(self, obj):
        """Build absolute URL for membership detail."""
        request = self.context.get('request')
        if request is not None:
            return request.build_absolute_uri(reverse('project-membership-detail', kwargs={'id': obj.id}))
        return None


# Detailed serializer for ProjectMembership with user details
class DetailedProjectMembershipSerializer(serializers.ModelSerializer):
    user = DetailedUserSerializer(read_only=True)  # Use a detailed user serializer for richer information

    class Meta:
        model = ProjectMembership
        fields = ['user', 'joined_at', 'total_tasks', 'completed_tasks']


# Serializer for detailed Project information
class ProjectSerializer(serializers.ModelSerializer):
    owner = CustomUserSerializer(read_only=True)  # Display project owner's information
    members = ProjectMembershipSerializer(source='memberships', many=True, read_only=True)  # Serialize project members

    class Meta:
        model = Project
        fields = [
            'id', 'name', 'description', 'created_at', 
            'total_tasks', 'status', 'due_date', 'total_member_count', 
            'owner', 'members'
        ]
        read_only_fields = ['id', 'owner', 'created_at', 'total_tasks', 'total_member_count']


# Serializer for listing projects with minimal fields
class ProjectListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['id', 'name', 'description', 'status', 'due_date']


# Serializer for creating a new project
class ProjectCreateSerializer(serializers.ModelSerializer):
    members = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), many=True, write_only=True, required=False)

    class Meta:
        model = Project
        fields = ['name', 'description', 'due_date', 'members', 'status']
        json_encoder = DjangoJSONEncoder

    def validate_due_date(self, value):
        """Ensure due date is not in the past."""
        if value and value.date() < timezone.now().date():
            raise serializers.ValidationError("Due date cannot be in the past.")
        return value

    def validate_members(self, value):
        """Limit the number of members in a project."""
        if len(value) > 10:
            raise serializers.ValidationError("A project cannot have more than 10 members.")
        return value

    def create(self, validated_data):
        """
        Create a new project and add members, including the owner.
        """
        members = validated_data.pop('members', [])
        owner = self.context['request'].user

        # Remove 'owner' field if accidentally included
        if 'owner' in validated_data:
            validated_data.pop('owner')

        # Create the project with the authenticated user as owner
        project = Project.objects.create(**validated_data, owner=owner)

        # Automatically add the owner as a member
        ProjectMembership.objects.create(project=project, user=owner)

        # Validate plan restrictions for adding members
        subscription = owner.subscription
        plan = subscription.plan if subscription else None
        if plan and plan.max_members_per_project > 1:
            if len(members) > plan.max_members_per_project:
                raise serializers.ValidationError("You have exceeded the maximum number of members allowed by your plan.")

        # Add other members, ensuring no duplication of owner
        for user in members:
            if user != owner:
                ProjectMembership.objects.create(project=project, user=user)

        # Save members to context for additional processing if needed
        self.context['members'] = members
        return project

    def to_representation(self, instance):
        """Custom representation of the project."""
        return {
            'id': instance.id,
            'name': instance.name,
            'description': instance.description,
            'due_date': instance.due_date,
            'owner': CustomUserSerializer(instance.owner).data,
            'members': ProjectMembershipSerializer(instance.memberships.all(), many=True).data
        }


# Serializer for updating an existing project
class ProjectUpdateSerializer(serializers.ModelSerializer):
    members = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), many=True, required=False)

    class Meta:
        model = Project
        fields = ['name', 'description', 'due_date', 'status', 'members']

    def validate_due_date(self, value):
        """Ensure due date is not in the past."""
        if value and value < timezone.now().date():
            raise serializers.ValidationError("Due date cannot be in the past.")
        return value

    def validate_members(self, value):
        """Ensure members list respects subscription limits and removes duplicates."""
        value = list(set(value))  # Remove duplicate entries
        user = self.context['request'].user
        subscription = user.subscription
        plan = subscription.plan if subscription else None
        
        # Check if the project has admin_override
        instance = self.instance
        if instance and instance.admin_override:
            return value  # Skip the member limit check if admin_override is True

        if plan and plan.max_members_per_project > 1:
            if len(value) > plan.max_members_per_project:
                raise serializers.ValidationError("You have exceeded the maximum number of members allowed by your plan.")
        return value

    def update(self, instance, validated_data):
        """Update project and manage membership changes."""
        members = validated_data.pop('members', None)
        if members is not None:
            members = list(set(members))  # Ensure unique member entries

        # Track membership changes
        new_members = []
        removed_members = []

        # Update other fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if members is not None:
            # Determine members to add and remove
            current_members = set(instance.memberships.values_list('user', flat=True))
            new_members_set = set(member.id for member in members)
            
            # Ensure the owner remains a member
            if instance.owner.id not in new_members_set:
                raise serializers.ValidationError("Owner cannot be removed from the project.")

            # Calculate members to add and remove
            to_remove = current_members - new_members_set
            to_add = new_members_set - current_members

            # Remove members no longer in the project
            if to_remove:
                ProjectMembership.objects.filter(project=instance, user__in=to_remove).delete()
                removed_members = list(to_remove)

            # Add new members
            if to_add:
                for user_id in to_add:
                    ProjectMembership.objects.create(project=instance, user_id=user_id)
                new_members = list(to_add)
            instance.update_member_count()
            instance.refresh_from_db()  # Refresh instance to reflect changes
            # Save changes to context for potential use
            self.context['new_members'] = User.objects.filter(id__in=new_members)
            self.context['removed_members'] = User.objects.filter(id__in=removed_members)

        return instance

    def to_representation(self, instance):
        """Use the detailed project serializer for output."""
        return ProjectSerializer(instance, context=self.context).data


class ProjectInvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectInvitation
        fields = ['id', 'project', 'email', 'project_name', 'inviter_email', 'inviter_name', 'created_at', 'expires_at', 'accepted', 'accepted_at']
        read_only_fields = ['id', 'project_name', 'inviter_email', 'inviter_name', 'created_at', 'expires_at', 'accepted', 'accepted_at']

    def create(self, validated_data):
        # Check if there's an existing active invitation
        existing_invitation = ProjectInvitation.objects.filter(
            project=validated_data['project'],
            email=validated_data['email'],
            accepted=False,
            expires_at__gt=timezone.now()
        ).first()

        if existing_invitation:
            # If there's an active invitation, return it instead of creating a new one
            return existing_invitation

        # If no active invitation exists, create a new one
        validated_data['invited_by'] = self.context['request'].user
        validated_data['expires_at'] = timezone.now() + timedelta(days=7)
        return super().create(validated_data)

class ProjectInvitationAcceptSerializer(serializers.Serializer):
    token = serializers.UUIDField()

    def validate_token(self, value):
        try:
            invitation = ProjectInvitation.objects.get(token=value, accepted=False)
            if invitation.is_expired():
                raise serializers.ValidationError("This invitation has expired.")
            return value
        except ProjectInvitation.DoesNotExist:
            raise serializers.ValidationError("Invalid or already accepted invitation token.")