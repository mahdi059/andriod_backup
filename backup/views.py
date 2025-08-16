# backup/views.py
from rest_framework import status, views, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from pathlib import Path
import shutil
import logging
from .models import Backup, MediaFile, Message
from .serializers import BackupUploadSerializer, MediaFileSerializer, MessageSerializer
from .utils import ab_to_tar_with_abe, extract_tar, organize_extracted_files
from .parser import parse_media_type, parse_and_save_sms, parse_apks_from_dir, scan_and_store_databases, parse_sqlite_db, parse_json_folder
from django.shortcuts import get_object_or_404
from .pagination import StandardResultsSetPagination 



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


class OrganizeMediaView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        try: 
            backup = Backup.objects.get(pk=pk, user=request.user)
        except Backup.DoesNotExist:
            return Response({"error": "Backup not found"}, status=status.HTTP_404_NOT_FOUND)
 
        extracted_dir = Path(settings.BACKUP_STORAGE_DIR) / f"backup_{backup.id}" / "extracted"

        if not extracted_dir.exists():
            return Response({"error": "Extracted files directory not found"}, status=status.HTTP_400_BAD_REQUEST)
        
        try :
            stats = organize_extracted_files(extracted_dir)
            return Response({
                "message": "Files organized successfully.",
                "backup_id": backup.id,
                "stats": stats
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        


class ParsePhotosView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        return self._parse(pk, "photos", "photo", request.user)
    
    def _parse(self, pk, folder_name, media_type, user):
        try:
            backup = Backup.objects.get(pk=pk, user=user)

        except Backup.DoesNotExist:
            return Response({"error": "Backup not found"}, status=status.HTTP_404_NOT_FOUND)
        
        media_dir = Path(settings.BACKUP_STORAGE_DIR) / f"backup_{backup.id}" / "extracted" / folder_name

        try:
            count = parse_media_type(media_dir, backup, media_type)
            return Response({"message": f"{media_type.capitalize()}s parsed successfully", "count": count})
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        

class ParseVideosView(ParsePhotosView):
    def post(self, request, pk):
        return self._parse(pk, "videos", "video", request.user)
    

class ParseAudiosView(ParsePhotosView):
    def post(self, request, pk):
        return self._parse(pk, "audios", "audio", request.user)
    

class ParseDocumentsView(ParsePhotosView):
    def post(self, request, pk):
        return self._parse(pk, "documents", "document", request.user)



class ParseSMSBackupView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            backup = Backup.objects.get(pk=pk, user=request.user)
        
        except Backup.DoesNotExist:
            return Response({"error": "Backup not found"}, status=status.HTTP_404_NOT_FOUND)
        
        others_dir = Path(settings.BACKUP_STORAGE_DIR) / f"backup_{backup.id}" / "extracted" / "others"
        
        if not others_dir.exists():
            return Response({"error": "others directory not found"}, status=status.HTTP_400_BAD_REQUEST)
        
        sms_files = list(others_dir.glob("*sms*"))

        if not sms_files:
            return Response({"error": "no sms backup file found"}, status=status.HTTP_404_NOT_FOUND)
        
        total_count = 0
        errors = []
        for sms_file in sms_files:
            try:
                count = parse_and_save_sms(sms_file, backup)
                total_count += count
            except Exception as e:
                errors.append(str(e))
            
        if errors:
            return Response({
                "message": f"Parsed SMS files with partial errors.",
                "total_sms_saved": total_count,
                "errors": errors
            }, status=status.HTTP_207_MULTI_STATUS)
        return Response({
            "message": "all sms files parsed successfully.",
            "total_sms_saved": total_count
        }, status=status.HTTP_200_OK)
    


class ParseApksView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            backup = Backup.objects.get(pk=pk, user=request.user)
        except Backup.DoesNotExist:
            return Response({"error": "backup not found"}, status=status.HTTP_404_NOT_FOUND)
        
        others_dir = Path(settings.BACKUP_STORAGE_DIR) / f"backup_{backup.id}" / "extracted" / "others"

        try:
            count = parse_apks_from_dir(others_dir, backup)
            return Response({
                "message" : f"{count} apks parsed successfully."}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class ScanDatabasesView(views.APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request, pk):
        try:
            backup = Backup.objects.get(pk=pk, user=request.user)
        except Backup.DoesNotExist:
            return Response({"error": "backup not found"}, status=status.HTTP_404_NOT_FOUND)
        
        database_dir = Path(settings.BACKUP_STORAGE_DIR) / f"backup_{backup.id}" / "extracted" / "databases"

        try:
            counts = scan_and_store_databases(database_dir, backup)
            return Response({
                "message": "databases scanned and stord successfully.",
                "count" : f"number od databases: {counts}"
            }, status=status.HTTP_200_OK)
        
        except FileNotFoundError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            return Response({"error" : str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        


class ParseDatabaseAPIView(views.APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, pk):
        backup = get_object_or_404(Backup, pk=pk, user=request.user)
        db_folder = Path(settings.BACKUP_STORAGE_DIR) / f"backup_{backup.id}" / "extracted" / "databases"

        if not db_folder.exists():
            return Response({"error": "Backup folder not found"}, status=status.HTTP_400_BAD_REQUEST)

        result = {"message": "Parsing complete", "details": []}

        for file_path in db_folder.iterdir():
            if file_path.suffix.lower() not in [".db", ".sqlite"]:
                continue

            stats = parse_sqlite_db(file_path, backup)
            file_info = {"file": file_path.name}
            file_info.update(stats)
            result["details"].append(file_info)

        return Response(result, status=status.HTTP_200_OK)
    



class ParseJSONBackupAPIView(views.APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        
        backup = get_object_or_404(Backup, pk=pk, user=request.user)
        json_dir = Path(settings.BACKUP_STORAGE_DIR) / f"backup_{backup.id}" / "extracted" / "configs"


        if not json_dir.exists():
            return Response({"error": "configs dir not found."}, status=status.HTTP_404_NOT_FOUND)
        
        result = parse_json_folder(json_dir, backup)
        return Response({
            "message": "json files parsed successfuly.",
            "result": result

        },status=status.HTTP_200_OK)



#  ...


class MediaListAPIView(generics.ListAPIView):
    serializer_class = MediaFileSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        pk = self.kwargs.get("pk")
        media_type = self.request.query_params.get("type")

        backup = get_object_or_404(Backup, pk=pk, user=user)

        queryset = MediaFile.objects.filter(backup=backup)

        if media_type in ["photo", "video", "audio", "document"]:
            queryset = queryset.filter(media_type=media_type)

        return queryset.order_by('-added_at')



class MessageListAPIView(generics.ListAPIView):
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        pk = self.kwargs.get("pk")

        backup = get_object_or_404(Backup, pk=pk, user=user)

        queryset = Message.objects.filter(backup=backup)

        return queryset.order_by('created_at')
