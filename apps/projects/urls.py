from django.urls import path
from apps.projects.views import (
    ProjectListCreateView, 
    ProjectRetrieveUpdateDestroyView,
    ProjectMembershipView,
    ProjectInvitationListCreateView,
    ProjectInvitationAcceptView
)

urlpatterns = [
    # Base URL: api/v1/projects/
    # Endpoint for listing projects and creating a new project
    path('', ProjectListCreateView.as_view(), name='project-list-create'),

    # Endpoint for retrieving, updating, or deleting a specific project also manage members by its primary key (pk)
    path('<int:pk>/', ProjectRetrieveUpdateDestroyView.as_view(), name='project-retrieve-update-destroy'),
    
    # Endpoint for showing detail info of members of a project
    path('memberships/<int:id>/', ProjectMembershipView.as_view(), name='project-membership-detail'),
    
    path('invite/', ProjectInvitationListCreateView.as_view(), name='project-invitation-list-create'),
    path('invite/accept/', ProjectInvitationAcceptView.as_view(), name='project-invitation-accept'),
]
