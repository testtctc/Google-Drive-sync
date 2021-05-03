# encoding=utf-8
import logging
#log  format
logging.basicConfig(level=logging.DEBUG,
                    format="%(asctime)s %(levelname)s %(process)d %(message)s",
                    datefmt="%Y%b%d-%H:%M:%S",
                    style="%")

SCOPES=[
"https://www.googleapis.com/auth/drive",
"https://www.googleapis.com/auth/drive.file",
"https://www.googleapis.com/auth/drive.readonly"
"https://www.googleapis.com/auth/drive.metadata.readonly",
"https://www.googleapis.com/auth/drive.appdata",
"https://www.googleapis.com/auth/drive.apps.readonly",
"https://www.googleapis.com/auth/drive.metadata",
"https://www.googleapis.com/auth/drive.photos.readonly"
]

# the location of credentials file
CLIENT_SECRET_FILE = 'credentials.json'

# google driver folder id of  parent folder -- namely the the folder that contains the DRIVE_FOLDER_NAME
PARENT_DRIVE_FOLDER_ID="root"

#google driver path to sync
DRIVE_FOLDER_NAME = 'files'

#local dir to sync
OS_FULL_PATH = r'/raid/tmp/files'

#the number of process to process file
CONCURRENCY=3

# only scan upload recently modify files
SCAN_INTERVAL_DAYS=3