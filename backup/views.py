# backup/views.py
from rest_framework import status, views
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.conf import settings
from pathlib import Path
import shutil
import logging
from .models import Backup
from .serializers import BackupUploadSerializer
from .utils import ab_to_tar_with_abe, extract_tar

logger = logging.getLogger(__name__)

class BackupUploadView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = BackupUploadSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        backup = serializer.save()
        backup_folder = Path(settings.BACKUP_STORAGE_DIR) / f"backup_{backup.id}"
        backup_folder.mkdir(parents=True, exist_ok=True)

        try:
            original_ab_src = Path(backup.original_file.path)
            if not original_ab_src.exists() or original_ab_src.stat().st_size == 0:
                raise ValueError("Uploaded backup file is missing or empty.")

            original_ab_dst = backup_folder / original_ab_src.name
            if not original_ab_dst.exists():
                shutil.copy(original_ab_src, original_ab_dst)

            tar_path = backup_folder / f"temp_{backup.id}.tar"
            output_dir = backup_folder / "extracted"
            abe_jar_path = Path(settings.ABE_JAR_PATH)

            ab_to_tar_with_abe(original_ab_dst, tar_path, abe_jar_path)
            extract_tar(tar_path, output_dir)

            if not any(output_dir.iterdir()):
                raise ValueError("Extraction completed but no files found in output directory.")


            return Response({
                "message": "Backup uploaded and extracted successfully",
                "backup_id": backup.id,
                "extracted_files_count": len(list(output_dir.rglob('*'))),
                "backup_folder": str(backup_folder)
            }, status=status.HTTP_201_CREATED)

        except Exception as exc:
            logger.exception("Error processing backup %s", backup.id)
            backup.error_message = str(exc)
            backup.save(update_fields=['error_message'])
            return Response({"error": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
