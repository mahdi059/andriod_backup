from celery import shared_task
from pathlib import Path
from django.conf import settings
from .models import Backup
from . import utils 
import logging

logger = logging.getLogger(__name__)

@shared_task
def process_backup_task(backup_id: int):
    try:
        backup = Backup.objects.get(id=backup_id)

        backup_folder = Path(settings.BACKUP_STORAGE_DIR) / f"backup_{backup.id}"
        backup_folder.mkdir(parents=True, exist_ok=True)

  
        original_ab_src = Path(backup.original_file.path)
        if not original_ab_src.exists() or original_ab_src.stat().st_size == 0:
            raise ValueError("Uploaded backup file is missing or empty.")


        tar_path = backup_folder / f"temp_{backup.id}.tar"
        output_dir = backup_folder / "extracted"


        utils.ab_to_tar_with_hoardy(original_ab_src, tar_path)


        utils.extract_tar(tar_path, output_dir)

        if not any(output_dir.iterdir()):
            raise ValueError("Extraction completed but no files found in output directory.")


        stats = utils.organize_extracted_files_to_minio(output_dir, backup.id)


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
