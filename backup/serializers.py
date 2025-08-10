from rest_framework import serializers
from .models import Backup


class BackupUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Backup
        fields = ['original_file']

    def create(self, validated_data):
        user = self.context['request'].user
        return Backup.objects.create(user=user, **validated_data)
