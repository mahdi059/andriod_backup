from rest_framework import serializers
from .models import Backup, MediaFile, Message, Contact, CallLog, App
from pathlib import Path
from datetime import datetime, timezone
import re
from minio import Minio
import logging
from datetime import timedelta
import uuid


minio_client = Minio(
    "minio:9000",
    access_key="minio",
    secret_key="minio123",
    secure=False
)


ORIGINAL_BUCKET_NAME = "original-files"

def ensure_original_bucket():
    if not minio_client.bucket_exists(ORIGINAL_BUCKET_NAME):
        minio_client.make_bucket(ORIGINAL_BUCKET_NAME)


class BackupUploadSerializer(serializers.ModelSerializer):
    original_file = serializers.FileField(write_only=True)

    class Meta:
        model = Backup
        fields = ['original_file']

    def create(self, validated_data):
        user = self.context['request'].user
        file_obj = validated_data['original_file']

        ensure_original_bucket() 

        backup = Backup.objects.create(
            user=user,
            original_file_name=file_obj.name
        )

        file_key = f"original_file/{backup.id}/{file_obj.name}"

        minio_client.put_object(
            ORIGINAL_BUCKET_NAME,
            file_key,
            file_obj,
            length=file_obj.size,
            content_type=file_obj.content_type
        )

        backup.original_minio_path = file_key
        backup.save(update_fields=['original_minio_path'])

        return backup





class MediaFileSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = MediaFile
        fields = [ "id", "file_name", "minio_path", "media_type", "mime_type", "size_bytes", "added_at", "file_url",  ]


    def get_file_url(self, obj):
        logger = logging.getLogger(__name__)

        if not obj.minio_path:
            return None
        try:
            url = minio_client.presigned_get_object(
                "backups",
                obj.minio_path,
                expires=timedelta(hours=1)
            )
            return url
        except Exception as e:
            logger.error(f"Error generating presigned URL for {obj.minio_path}: {e}")
            return None



class MessageSerializer(serializers.ModelSerializer):

    class Meta:
        model = Message
        fields = ['sender', 'receiver', 'content', 'sent_at', 'received_at', 'message_type', 'status', 'created_at']



MOBILE_REGEX = re.compile(r"^(?:\+98|0)?9\d{9}$")

class MessageParserSerializer(serializers.ModelSerializer):

    class Meta:
        model = Message
        fields = "__all__"

    def validate_sender(self, value):
        if value and not MOBILE_REGEX.match(value):
            raise serializers.ValidationError("Invalid sender phone number format.")
        return value
    

    def validate_receiver(self, value):
        if value and not MOBILE_REGEX.match(value):
            raise serializers.ValidationError("invalid receiver phone number format.")
        return value
    
    def validate_content(self, value):
        if not value:
            raise serializers.ValidationError("message content cannot be empty.")
        if len(value) > 10000:
            raise serializers.ValidationError("message content is too long.")
        
        return value
    
    def validate_sent_at(self, value):
        if value is None:
            raise serializers.ValidationError("Sent timestamp cannot be None.")
        return value
    
    def validate_received_at(self, value):
        if value is  None:
            raise serializers.ValidationError("Received timestamp cannot be None.")
        return value
    
    def validate_message_type(self, value):
        if value not in ("sms", "mms"):
            raise serializers.ValidationError("Message type must be 'sms' or 'mms'.")
        return value
    


class MediaParserSerializer(serializers.ModelSerializer):

    class Meta:
        model = MediaFile
        fields = "__all__"


    


class CallLogSerializer(serializers.ModelSerializer):

    class Meta:
        model = CallLog
        fields = "__all__"



class ContactSerializer(serializers.ModelSerializer):

    class Meta:
        model = Contact
        fields = "__all__"



MOBILE_REGEX = re.compile(r"^(?:\+98|0)?9\d{9}$")
GENERIC_PHONE_REGEX = re.compile(r"^\+?\d[\d\-\s\(\)]{4,}$")


def validate_phone_format(value: str) -> bool:
    if not value: return False

    return bool(MOBILE_REGEX.match(value) or GENERIC_PHONE_REGEX.match(value))


class ContactParserSerializer(serializers.ModelSerializer):

    class Meta:
        model = Contact
        fields = "__all__"


    def validate_name(self, value):
        if not value:
            raise serializers.ValidationError("Name cannot be empty.")
        if len(value) > 255:
            raise serializers.ValidationError("Name is too long.")
        return value
    

    def validate_phone_number(self, value):
        if not value:
            raise serializers.ValidationError("Phone number is required.")
        if not validate_phone_format(value):
            raise serializers.ValidationError("Invalid phone number format.")
        return value
    

    def validate_created_at(self, value):
        print("DEBUG created_at value:", value, type(value))
        if value is None or not isinstance(value, datetime):
            raise serializers.ValidationError("Created_at must be a valid datetime.")
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value
    


CALL_TYPES = {"incoming", "outgoing", "missed"}

    
class CallLogParserSerializer(serializers.ModelSerializer):

    class Meta:
        model = CallLog
        fields = "__all__"

    def validate_phone_number(self, value):
        if not value:
            raise serializers.ValidationError("Phone number is required.")
        if not validate_phone_format(value):
            raise serializers.ValidationError("Invalid phone number format.")
        return value
    

    def validate_call_type(self, value):
        value = value.lower()
        if value not in CALL_TYPES:
            raise serializers.ValidationError(f"Call type must be one of {CALL_TYPES}.")
        return value
    
    
    def validate_duration_seconds(self, value): 
        if not isinstance(value, int) or value < 0:
            raise serializers.ValidationError("Durations seconds must be a non-negative integer.")
        return value
    

    def validate_call_date(self, value):
        if value is None or not isinstance(value, datetime):
            raise serializers.ValidationError("Call_date must be a valid datetime.")
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value
    


class AppParserSerializer(serializers.ModelSerializer):
    backup = serializers.PrimaryKeyRelatedField(queryset=Backup.objects.all())
    
    class Meta:
        model = App
        fields = "__all__"

