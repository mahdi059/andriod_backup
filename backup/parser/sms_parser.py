from pathlib import Path
from datetime import datetime
import json
import zlib
from ..serializers import MessageParserSerializer
from django.utils.timezone import make_aware, get_default_timezone
from ..models import Backup
from minio import Minio
import logging 


minio_client = Minio(
    "minio:9000",
    access_key="minio",
    secret_key="minio123",
    secure=False
)


BUCKET_NAME = "backups"


logger = logging.getLogger(__name__)

def convert_timestamp(ts):
    try:
        ts_int = int(ts)
        if ts_int > 1e12: 
            ts_int = ts_int // 1000
        dt = datetime.utcfromtimestamp(ts_int)
        dt_aware = make_aware(dt, timezone=get_default_timezone())
        return dt_aware
    except Exception:
        return None


def parse_and_save_sms_minio(backup_instance: Backup):
    prefix = f"{backup_instance.id}/others/"
    objects = minio_client.list_objects(BUCKET_NAME, prefix=prefix, recursive=True)
    
    count = 0
    for obj in objects:
        
        if "sms" not in obj.object_name.lower():
            continue
        
        try:
            response = minio_client.get_object(BUCKET_NAME, obj.object_name)
            compressed_data = response.read()
            response.close()
            response.release_conn()
            
            decompressed_data = zlib.decompress(compressed_data)
            json_text = decompressed_data.decode("utf-8", errors="ignore")
            sms_list = json.loads(json_text)
        
        except Exception as e:
            logger.error("Error reading/parsing object %s from Minio: %s", obj.object_name, e)

            continue  

        for sms in sms_list:
            try:
                if sms.get("type") == "1":
                    sender = sms.get("address")
                    receiver = None
                else:
                    sender = None
                    receiver = sms.get("address")
                msg_type = "sms" if sms.get("type") == "1" else "mms"

                serializer = MessageParserSerializer(
                    data={
                        'backup': backup_instance.id,
                        'sender': sender,
                        'receiver': receiver,
                        'content': sms.get("body"),
                        'sent_at': convert_timestamp(sms.get("date_sent")),
                        'received_at': convert_timestamp(sms.get("date")),
                        'status': int(sms.get("status") or 0),
                        'message_type': msg_type,
                    }
                )

                if serializer.is_valid():
                    serializer.save()
                    count += 1
                else:
                    logger.error("Validation failed for SMS in %s : %s", obj.bucket_name, serializer.errors)

            except Exception as e:
                logger.error("Error saving SMS from %s : %s", obj.object_name, e)

    return count
