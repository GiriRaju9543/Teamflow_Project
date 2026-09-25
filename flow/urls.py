from django.urls import path
from . import views

urlpatterns = [
    path('', views.board, name='board'),
    path('signup/', views.signup, name='signup'),
    path('teams/', views.teams, name='teams'),
    path('teams/<int:pk>/members/', views.members, name='members'),
    path('projects/new/<int:workspace_id>/', views.project_edit, name='project_new'),
    path('projects/<uuid:pk>/settings/', views.project_edit, name='project_edit'),
    path('projects/<uuid:pk>/tasks/new/', views.task_edit, name='task_new'),
    path('tasks/<int:pk>/', views.task_detail, name='task_detail'),
    path('tasks/<int:pk>/edit/', views.task_edit, name='task_edit'),
    path('tasks/<int:pk>/start/', views.start_task, name='start_task'),
    path('tasks/<int:pk>/request-changes/', views.request_changes, name='request_changes'),
    path('notifications/', views.notifications, name='notifications'),
    path('activity/', views.activity, name='activity'),
    path('reports/', views.reports, name='reports'),
    path('integrations/', views.integrations, name='integrations'),
    path('deliveries/', views.deliveries, name='deliveries'),
    path('deliveries/<int:pk>/retry/', views.retry_delivery, name='retry_delivery'),
    path('hooks/github/<uuid:pk>/', views.webhook, name='webhook'),
]
