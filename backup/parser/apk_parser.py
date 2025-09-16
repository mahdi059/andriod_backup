from ..serializers import AppParserSerializer
from ..models import Backup
from minio import Minio
import logging
import tempfile
from androguard.core.apk import APK

minio_client = Minio(
    "minio:9000",
    access_key="minio",
    secret_key="minio123",
    secure=False
)

BUCKET_NAME = "backups"


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


logging.getLogger("androguard").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("minio").setLevel(logging.WARNING)


console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

formatter = logging.Formatter("%(levelname)s - %(message)s")
console_handler.setFormatter(formatter)

if not logger.handlers:
    logger.addHandler(console_handler)


def parse_apks_with_minio(backup_instance: Backup):
    parsed_count = 0
    processed_count = 0
    failed_count = 0

    prefix = f"{backup_instance.id}/others/"
    objects = minio_client.list_objects(BUCKET_NAME, prefix=prefix, recursive=True)

    for obj in objects:
        file_name = obj.object_name.split("/")[-1]
        if not file_name.lower().endswith(".apk"):
            continue

        processed_count += 1

        try:
            response = minio_client.get_object(BUCKET_NAME, obj.object_name)
            apk_binary = response.read()
            response.close()
            response.release_conn()
        except Exception as e:
            logger.error(f"[DOWNLOAD FAILED] {obj.object_name}: {e}")
            failed_count += 1
            continue

        with tempfile.NamedTemporaryFile(suffix=".apk", delete=True) as tmp_file:
            tmp_file.write(apk_binary)
            tmp_file.flush()
            try:
                apk = APK(tmp_file.name)
                package_name = apk.get_package()
                if not package_name:
                    logger.warning(f"[SKIP] {file_name}: package_name is blank")
                    failed_count += 1
                    continue

                app_name = apk.get_app_name()
                version_code = apk.get_androidversion_code()
                version_name = apk.get_androidversion_name()
                permissions = apk.get_permissions()

                serializer = AppParserSerializer(
                    data={
                        "backup": backup_instance.id,
                        "package_name": package_name,
                        "app_name": app_name,
                        "version_code": version_code,
                        "version_name": version_name,
                        "minio_path": obj.object_name,
                        "permissions": permissions
                    }
                )

                if serializer.is_valid():
                    serializer.save()
                    parsed_count += 1
                else:
                    logger.warning(f"[SERIALIZER INVALID] {file_name}: {serializer.errors}")
                    failed_count += 1

            except Exception as e:
                logger.error(f"[APK PARSE FAILED] {file_name}: {e}")
                failed_count += 1

    logger.info(
        f"Processed APKs: {processed_count}, "
        f"Successfully Parsed: {parsed_count}, "
        f"Failed: {failed_count}"
    )
    return parsed_count
