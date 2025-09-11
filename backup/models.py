from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import os

class Backup(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    original_file = models.FileField(upload_to='backups/')
    original_file_name = models.CharField(max_length=255, blank=True)  
    uploaded_at = models.DateTimeField(auto_now_add=True)
    error_message = models.TextField(blank=True, null=True)
    processed = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.original_file and not self.original_file_name:
            self.original_file_name = self.original_file.name
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Backup {self.id} by {self.user.username}"


class Contact(models.Model):
    backup = models.ForeignKey(Backup, on_delete=models.CASCADE, related_name='contacts')
    name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=50)
    email = models.EmailField(blank=True, null=True)
    group = models.CharField(max_length=255, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)


class Message(models.Model):
    backup = models.ForeignKey(Backup, on_delete=models.CASCADE, related_name='messages')
    external_id = models.CharField(max_length=255, blank=True, null=True)
    sender = models.CharField(max_length=255, blank=True, null=True)
    receiver = models.CharField(max_length=255, blank=True, null=True)
    content = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    received_at = models.DateTimeField(blank=True, null=True)
    message_type = models.CharField(max_length=20, choices=[('sms', 'SMS'), ('mms', 'MMS')], blank=True, null=True)
    status = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class CallLog(models.Model):
    backup = models.ForeignKey(Backup, on_delete=models.CASCADE, related_name='call_logs')
    phone_number = models.CharField(max_length=50)
    call_type = models.CharField(max_length=20, choices=[('incoming', 'Incoming'), ('outgoing', 'Outgoing'), ('missed', 'Missed')])
    call_date = models.DateTimeField(blank=True, null=True)
    duration_seconds = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class App(models.Model):
    backup = models.ForeignKey(Backup, on_delete=models.CASCADE, related_name='apps')
    package_name = models.CharField(max_length=500) 
    app_name = models.CharField(max_length=255, blank=True, null=True)
    version_code = models.CharField(max_length=50, blank=True, null=True)
    version_name = models.CharField(max_length=50, blank=True, null=True)
    apk_file = models.BinaryField(blank=True, null=True) 
    apk_file_name = models.CharField(max_length=255, blank=True, null=True)
    permissions = models.JSONField(blank=True, null=True, default=list)
    installed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    
    def __str__(self):
        return f"{self.app_name or self.package_name} ({self.version_name})"



class MediaFile(models.Model):
    backup = models.ForeignKey(Backup, on_delete=models.CASCADE, related_name='media_files')
    file_name = models.CharField(max_length=255)
    media_type = models.CharField(
        max_length=20,
        choices=[('photo', 'Photo'), ('video', 'Video'), ('audio', 'Audio'), ('document', 'Document'), ('other', 'Other')]
    )
    mime_type = models.CharField(max_length=100, blank=True, null=True)
    size_bytes = models.BigIntegerField(blank=True, null=True)
    added_at = models.DateTimeField(default=timezone.now)
    minio_path = models.CharField(max_length=500, blank=True, null=True)  # مسیر فایل در MinIO



class SystemSetting(models.Model):
    backup = models.ForeignKey(Backup, on_delete=models.CASCADE, related_name='system_settings')
    key = models.CharField(max_length=255)
    value = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Note(models.Model):
    backup = models.ForeignKey(Backup, on_delete=models.CASCADE, related_name='notes')
    title = models.CharField(max_length=255, blank=True, null=True)
    content = models.TextField()
    created_at = models.DateTimeField(blank=True, null=True)


class Bookmark(models.Model):
    backup = models.ForeignKey(Backup, on_delete=models.CASCADE, related_name='bookmarks')
    title = models.CharField(max_length=255)
    url = models.URLField()
    added_at = models.DateTimeField(blank=True, null=True)


class ChatMessage(models.Model):
    backup = models.ForeignKey(Backup, on_delete=models.CASCADE, related_name='chat_messages')
    chat_id = models.CharField(max_length=255, blank=True, null=True)
    sender = models.CharField(max_length=255, blank=True, null=True)
    message = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class RawBackupFile(models.Model):
    backup = models.ForeignKey(Backup, on_delete=models.CASCADE, related_name='raw_files')
    relative_path = models.CharField(max_length=500)
    file_data = models.BinaryField(blank=True, null=True) 
    size_bytes = models.BigIntegerField(blank=True, null=True)
    file_type = models.CharField(max_length=100, blank=True, null=True)
    added_at = models.DateTimeField(auto_now_add=True)
