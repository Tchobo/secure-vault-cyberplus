from django.urls import path
from documents import views

urlpatterns = [
    path('', views.DocumentListView.as_view(), name='document-list'),
    path('<uuid:pk>/', views.DocumentDetailView.as_view(), name='document-detail'),
    path('<uuid:pk>/download/', views.DocumentDownloadView.as_view(), name='document-download'),
    path('<uuid:pk>/deactivate/', views.DocumentDeactivateView.as_view(), name='document-deactivate'),
    path('<uuid:pk>/activate/', views.DocumentActivateView.as_view(), name='document-activate'),
    path('<uuid:pk>/audit/', views.DocumentAuditLogView.as_view(), name='document-audit'),
    path('<uuid:pk>/share/', views.DocumentShareView.as_view(), name='document-share'),
    path('<uuid:pk>/unshare/', views.DocumentUnshareView.as_view(), name='document-unshare'),
]