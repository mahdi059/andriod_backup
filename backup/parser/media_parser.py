import mimetypes
import re
from django.utils import timezone
from django.core.files.base import ContentFile
from minio import Minio
from ..models import Backup
from ..serializers import MediaParserSerializer
import logging

INVALID_CHARS = r'[<>:"/\\|?*]'
DOCUMENT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"}


minio_client = Minio(
    "minio:9000",         
    access_key="minio",
    secret_key="minio123",
    secure=False
)

BUCKET_NAME = "backups"   


logger = logging.getLogger(__name__)

def sanitize_and_truncate_filename(file_name: str, max_length: int = 100) -> str:
    name, dot, ext = file_name.rpartition(".")
    safe_name = re.sub(INVALID_CHARS, "_", name)
    allowed_length = max_length - len(ext) - 1
    if len(safe_name) > allowed_length:
        safe_name = safe_name[:allowed_length]
    return safe_name + dot + ext if ext else safe_name


def parse_media_type_minio(backup_instance: Backup, media_type_filter: str) -> int:
    parsed_count = 0

    prefix = f"{backup_instance.id}/{media_type_filter}s/"
    objects = minio_client.list_objects(BUCKET_NAME, prefix=prefix, recursive=True)

    for obj in objects:
        try:
            file_name = obj.object_name.split("/")[-1]
            if not file_name:
                continue

            mime_type, _ = mimetypes.guess_type(file_name)
            mime_type = mime_type or "application/octet-stream"

            if media_type_filter == "photo" and not mime_type.startswith("image/"):
                continue
            if media_type_filter == "video" and not mime_type.startswith("video/"):
                continue
            if media_type_filter == "audio" and not mime_type.startswith("audio/"):
                continue
            if media_type_filter == "document":
                ext = "." + file_name.split(".")[-1].lower()
                if ext not in DOCUMENT_EXTENSIONS:
                    continue

            safe_name = sanitize_and_truncate_filename(file_name)

            serializer = MediaParserSerializer(
                data={
                    "backup": backup_instance.id,
                    "file_name": safe_name,
                    "media_type": media_type_filter,
                    "mime_type": mime_type,
                    "size_bytes": obj.size,
                    "added_at": timezone.now(),
                    "minio_path": obj.object_name,  
                }
            )

            if serializer.is_valid():
                serializer.save()
                parsed_count += 1
            else:
                logger.error("Validation failed for %s : %s", file_name, serializer.errors)

        except Exception as e:
            logger.error("Error processing %s : %s", obj.object_name, e)
    return parsed_count

