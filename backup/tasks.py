from celery import shared_task
from .models import Backup
from . import utils
import logging
import tempfile
from pathlib import Path
from minio import Minio

logger = logging.getLogger(__name__)

minio_client = Minio(
    "minio:9000",
    access_key="minio",
    secret_key="minio123",
    secure=False
)

ORIGINAL_BUCKET_NAME = "original-files"

@shared_task
def process_backup_task(backup_id: int):
    try:
        backup = Backup.objects.get(id=backup_id)

        if not backup.original_minio_path:
            raise ValueError("Uploaded backup file path is missing.")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".ab") as tmp_file:
            response = minio_client.get_object(ORIGINAL_BUCKET_NAME, backup.original_minio_path)
            tmp_file.write(response.read())
            tmp_file_path = Path(tmp_file.name)

        stats = utils.process_ab_file(str(tmp_file_path), backup.id)

        tmp_file_path.unlink(missing_ok=True)

        backup.processed = True
        backup.error_message = None
        backup.save(update_fields=["processed", "error_message"])

        logger.info("Backup %s processed successfully", backup.id)
        return {"status": "success", "stats": stats}

    except Exception as exc:
        logger.exception("Error processing backup %s", backup_id)
        try:
            backup = Backup.objects.get(id=backup_id)
            backup.error_message = str(exc)
            backup.save(update_fields=["error_message"])
        except Exception:
            pass
        return {"status": "error", "error": str(exc)}
