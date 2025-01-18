from rest_framework import permissions
from apps.projects.models import Project, ProjectMembership
from apps.tasks.models import Task, TaskAssignment

class IsProjectOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if isinstance(obj, Project):
            return obj.owner == request.user
        elif hasattr(obj, 'project'):
            return obj.project.owner == request.user
        return False

class IsProjectMember(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if isinstance(obj, Project):
            return ProjectMembership.objects.filter(project=obj, user=request.user).exists()
        elif hasattr(obj, 'project'):
            return ProjectMembership.objects.filter(project=obj.project, user=request.user).exists()
        return False

class IsTaskAssignee(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if isinstance(obj, Task):
            return TaskAssignment.objects.filter(task=obj, user=request.user).exists()
        elif hasattr(obj, 'task'):
            return TaskAssignment.objects.filter(task=obj.task, user=request.user).exists()
        return False

class CanManageTask(permissions.BasePermission):
    def has_permission(self, request, view):
        task_id = view.kwargs.get('pk')
        if task_id:
            task = Task.objects.get(id=task_id)
            return task.project.owner == request.user
        return False

    def has_object_permission(self, request, view, obj):
        return obj.project.owner == request.user or obj.assigned_by == request.user

class ReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS

class IsAdminUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.role == 'admin'

