from rest_framework import filters
from django.db.models import Q
from .models import Task, Project

class PermissionBasedFilterBackend(filters.BaseFilterBackend):
    """
    Filter that only allows users to see comments they have permission to view.
    """
    def filter_queryset(self, request, queryset, view):
        user = request.user
        task_id = request.query_params.get('task_id')
        project_id = request.query_params.get('project_id')

        if task_id:
            task = Task.objects.filter(
                Q(assignments__user=user) | Q(project__owner=user),
                id=task_id
            ).first()
            if task:
                return queryset.filter(task=task)
            return queryset.none()
        elif project_id:
            project = Project.objects.filter(
                Q(memberships__user=user) | Q(owner=user),
                id=project_id
            ).first()
            if project:
                return queryset.filter(task__project=project)
            return queryset.none()
        else:
            return queryset.filter(
                Q(author=user) |
                Q(task__assignments__user=user) |
                Q(task__project__owner=user)
            ).distinct()

