# <Android_Backup>


# Table of Contents

- [Introduction](#introduction)
- [Features](#features)
- [Installation](#installation)
  - [Configuration](#configuration)
  - [Authentication](#authentication)
- [Data Processing APIs](#data-processing-apis)
- [Data Access APIs](#data-access-apis)


## Introduction
This project is a backup and data extraction system for Android devices. It extracts and stores data from  `.ab` backup files.

## Features
- Extract contacts from backup files
- Extract call logs from backup files
- Parse various media files such as images, videos, and audio
- Parse documents and APK files

## Installation
1. Clone the repository
```bash
git clone https://github.com/mahdi059/andriod_backup.git
```
2. Create a virtual environment
```bash 
python -m venv venv
source venv/bin/activate # for Linux/macOS
venv\Scripts\activate # for Windows
```

### Configuration

The uploaded backup files are stored in the directory specified by `BACKUP_STORAGE_DIR` in the Django settings. By default, this is set to: media/backups
If you want to use a different directory, update the `BACKUP_STORAGE_DIR` value in `settings.py`.

3.Install dependencies
```bash
pip install -r requirements.txt
```

### Authentication

All API endpoints require JWT authentication. You need to obtain a token before using the APIs.

1. Obtain a JWT token:
```bash
POST /api/token/
```
Content-Type: application/json

{
  "username": "<your_username>",
  "password": "<your_password>"
}

# Use the access token in the Authorization header for subsequent requests
Authorization: Bearer <access_token>


## Data Processing APIs


1. Upload your `.ab` backup file to the server:
```bash
POST /backup/upload/
```
Authorization: Bearer <access_token>
Content-Type: multipart/form-data
file: <your_backup.ab>


2. Organize uploaded backup file:
```bash
Post /backup/<int:pk>/organize_media/
```
Authorization: Bearer <access_token>


3. Parse media files from the organized backup:

- **Photos** – Store all photo files from the backup
```bash
POST /backup/<int:pk>/parse-photos/
```

-**Videos** – Store all videos files from the backup
```bash
POST /backup/<int:pk>/parse-videos/
```

- **Audios** – Store all audios files from the backup
```bash
POST /backup/<int:pk>/parse-audios/
```

- **Documents** – Store all document files (PDF, DOCX, txt,...) from the backup
```bash
POST /backup/<int:pk>/parse-documents/
```

Authorization: Bearer <access_token>


4. Parse SMS files to extract and store SMS from the organized backup:

```bash
POST /backup/<int:pk>/parse-sms/
```
 Authorization: Bearer <access_token>


 5. Parse APK files to store APKs information from the organized backup:

 ```bash
 POST /backup/<int:pk>/parse-apk/
 ```


 6. Parse database files to extract and store CallLogs and Contacts from the organized backup:

 - **CallLogs** – store all calllogs from databases
 ```bash
 POST /backup/<int:pk>/parse-calllog/
 ```

 - **Contacts** – store all contacts from databases
 ```bash
 POST /backup/<int:pk>/parse-contact/
 ```


 ## Data Access APIs


1. Retrieve media files from the backup with optional filtering by type (photo, video, audio, document):

```bash
GET /backup/<int:pk>/media-list/
```

Authorization: Bearer <access_token>

### Query Parameters

- **type** (optional) – filter media files by type  
  Accepted values: `photo`, `video`, `audio`, `document`

### Examples

- Get all media files:
```bash
GET /backup/12/media-list/
```

- Get only photos:
```bash
GET /backup/12/media-list/?type=photo
```


2. Retrieve and list SMS messages extracted from the backup file:

```bash
GET /backup/<int:pk>/sms-list/:
```

Authorization: Bearer <access_token>


3. Retrieve and list calllogs and contacts data extracted from the backup file:

- **Contacts** – listing all extracted contacts data from the backup
```bash
GET /backup/<int:pk>/contact-list/
```

- **CallLogs** – listing all extracted calllogs data from the backup
```bash
GET /backup/<int:pk>/calllog-list/
```

Authorization: Bearer <access_token>