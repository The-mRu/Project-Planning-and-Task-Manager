import django_filters
from apps.projects.models import Project

class ProjectFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(lookup_expr='icontains')
    status = django_filters.ChoiceFilter(choices=Project.PROJECT_STATUS_CHOICES)
    due_date = django_filters.DateFromToRangeFilter()

    class Meta:
        model = Project
        fields = ['name', 'status', 'due_date']

