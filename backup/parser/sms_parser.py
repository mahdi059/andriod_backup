from pathlib import Path
from datetime import datetime
import json
import zlib
from ..serializers import MessageParserSerializer
from django.utils.timezone import make_aware, get_default_timezone
from ..models import Backup



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


def parse_and_save_sms(file_path: Path, backup_instance: Backup):
    with open(file_path, "rb") as f:
        compressed_data = f.read()

    decompressed_data = zlib.decompress(compressed_data)
    json_text = decompressed_data.decode("utf-8", errors="ignore")

    try:
        sms_list = json.loads(json_text)
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return 0

    count = 0
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
                    'backup' : backup_instance.id,
                    'sender':sender,
                    'receiver' : receiver,
                    'content' : sms.get("body"),
                    'sent_at' : convert_timestamp(sms.get("date_sent")),
                    'received_at' : convert_timestamp(sms.get("date")),
                    'status' : int(sms.get("status") or 0),
                    'message_type' : msg_type,
            })
            
            if serializer.is_valid():
                serializer.save()
                count += 1
        except Exception as e:
            print(f"Error saving SMS: {e}")

    return count