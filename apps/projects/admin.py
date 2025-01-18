from django.contrib import admin
from apps.projects.models import Project, ProjectMembership
# Register your models here.

admin.site.register(Project)
admin.site.register(ProjectMembership)