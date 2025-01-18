from django.urls import path
from apps.tasks import views
from apps.tasks.views import (TaskListCreateView, TaskRetrieveUpdateDestroyView,
    CommentListCreateView, CommentDetailView, CommentRepliesView, TaskStatusChangeView,
    StatusChangeRequestListCreateView, StatusChangeRequestRetrieveUpdateDestroyView,
    StatusChangeRequestAcceptRejectView
)

urlpatterns = [
    # Task URLs
    path('', TaskListCreateView.as_view(), name='task-list-create'),
    path('<int:pk>/', TaskRetrieveUpdateDestroyView.as_view(), name='task-retrieve-update-destroy'),
    path('status/change/<int:pk>/', TaskStatusChangeView.as_view(), name='task-status-change'),
    # Comment URLs
    path('comments/', CommentListCreateView.as_view(), name='comment-list-create'),
    path('comments/<int:pk>/', CommentDetailView.as_view(), name='comment-detail'),
    path('comments/<int:pk>/replies/', CommentRepliesView.as_view(), name='comment-reply-list'),
    
    # Status Change Request URLs
    path('status/change/requests/', StatusChangeRequestListCreateView.as_view(), name='status-change-request-list-create'),
    path('status/change/requests/<int:pk>/', StatusChangeRequestRetrieveUpdateDestroyView.as_view(), name='status-change-request-retrieve-update-destroy'),
    path('status/change/requests/<int:pk>/action/', StatusChangeRequestAcceptRejectView.as_view(), name='accept-reject-status-change-request'),
    
]
