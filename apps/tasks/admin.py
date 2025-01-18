from django.contrib import admin
from apps.tasks.models import Task, TaskAssignment, Comment

admin.site.register(Task)
admin.site.register(TaskAssignment)
admin.site.register(Comment)
