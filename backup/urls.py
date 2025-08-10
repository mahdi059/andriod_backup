from django.urls import path 
from . import views


urlpatterns = [
    path('upload/', views.BackupUploadView.as_view(), name='upload-backup'),
]
