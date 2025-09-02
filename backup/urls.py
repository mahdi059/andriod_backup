from django.urls import path 
from . import views


urlpatterns = [
    path('upload/', views.BackupUploadView.as_view(), name='upload-backup'),
    path('<int:pk>/organize_media/', views.OrganizeMediaView.as_view(), name='organize-media'),
    path('<int:pk>/parse-photos/', views.ParsePhotosView.as_view(), name='parse_photo'),
    path('<int:pk>/parse-videos/', views.ParseVideosView.as_view(), name='parse_videos'),
    path('<int:pk>/parse-audios/', views.ParseAudiosView.as_view(), name='parse_audios'),
    path('<int:pk>/parse-sms/', views.ParseSMSBackupView.as_view(), name='parse_sms'),
    path('<int:pk>/parse-apk/', views.ParseApksView.as_view(), name='parse_apk'),
    path('<int:pk>/parse-documents/', views.ParseDocumentsView.as_view(),name='parse_documents' ),
    path('<int:pk>/parse-json/', views.ParseJSONBackupAPIView.as_view(), name='parse_json'),
    path('<int:pk>/media/',  views.MediaListAPIView.as_view(), name='media-list'),
    path('<int:pk>/sms-list/', views.MessageListAPIView.as_view(), name='sms-list'),
    path('<int:pk>/parse-contact/', views.ParseContactsAPIView.as_view(), name='parse-contact'),
    path('<int:pk>/parse-calllog/', views.ParseCallLogsAPIView.as_view(), name='parse-calllog'),
    path('<int:pk>/contact-list/', views.ContactListAPIView.as_view(), name='contact-list'),
    path('<int:pk>/calllog-list/', views.CallLogListAPIView.as_view(), name='calllog-list'),

]
