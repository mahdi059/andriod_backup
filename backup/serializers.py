from rest_framework import serializers
from .models import Backup, MediaFile


class BackupUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Backup
        fields = ['original_file']

    def create(self, validated_data):
        user = self.context['request'].user
        return Backup.objects.create(user=user, **validated_data)



class MediaFileSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = MediaFile
        fields = ['id', 'file_name', 'file_url', 'mime_type', 'size_bytes', 'added_at']

    def get_file_url(self, obj):
        request = self.context.get('request')
        if obj.file:

            return request.build_absolute_uri(obj.file.url)
        return None
