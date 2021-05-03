# encoding=utf-8

import hashlib
import os
from googleapiclient.discovery import build
from  googleapiclient.http import MediaFileUpload
import mimetypes
from oauth2client.client import  OAuth2Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle
from google.auth.transport.requests import Request
from pprint import PrettyPrinter
from multiprocessing import Pool
pp = PrettyPrinter(width=4)
import time
from drivesync.settings import *

#sync file between local and google driver
class SyncFiles():
    def __init__(self, local_full_path: str = OS_FULL_PATH,
                 driver_path: str = DRIVE_FOLDER_NAME,
                 do_not_delete_files=True,
                 concurrency=CONCURRENCY,
                 log_level=logging.INFO,
                 check_md5=False,
                 do_not_check_same_file=True):
        assert isinstance(local_full_path, str) and len(local_full_path) > 0
        assert isinstance(driver_path, str) and len(driver_path) > 0
        self.local_full_path = local_full_path
        self.driver_path = driver_path
        self.do_not_check_same_file=do_not_check_same_file

        #modified time
        self.driver_folder_modifidtime={}

        # the depth of parent of os full path
        self.local_parent_full_path_depth = len(os.path.sep.join(OS_FULL_PATH.split("/")[:-1]))
        # the count of files that uploaded
        self.upload_files_count = 0
        self.download_files_count=0
        self.service = None
        # a flag hint that do not delete any files
        self.do_not_delete_files = do_not_delete_files
        self.check_md5 = check_md5
        self.concurrency = concurrency
        # driver name to folder id
        self.driver_folder_ids = {}
        # logger
        self.log = logging.getLogger("sync")
        self.log.setLevel(log_level)

    def info(self,message):
        self.log.info(message)

    def debug(self,message):
        self.log.info(message)

    def warn(self,message):
        self.log.warning(message)


    def _get_credentials(self) -> OAuth2Credentials:
        """
        Gets valid user credentials from storage.

        If nothing has been stored, or if the stored credentials are invalid,
        the OAuth2 flow is completed to obtain the new credentials.

        Returns:
            Credentials, the obtained credential.
        """
        creds = None
        # The file token.pickle stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    CLIENT_SECRET_FILE,SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        return creds

    def prepare_driver_service(self):
        credentials = self._get_credentials()
        self.service = build('drive', 'v3', credentials=credentials,cache_discovery=False)


    def get_folder_id(self,relative_path:str):
        """
        Args:
            relative_path: the relative path to google drive root
        Returns: google drive folder id
        """
        if relative_path in self.driver_folder_ids:
            return self.driver_folder_ids[relative_path]
        #抵达跟路径
        elif relative_path =="":
            return "root"
        else:
            parent_folder=os.sep.join(relative_path.split(os.sep)[:-1])
            folder_name= relative_path.split(os.sep)[-1]
            # recursively to get parent folder id
            parent_id = self.get_folder_id(parent_folder)
            results = self.service.files().list(
                q="'{}' in parents and trashed != True and name='{}' \
                        and mimeType='application/vnd.google-apps.folder'".format(parent_id,folder_name)).execute()
            items=results.get("files",[])
            if items:
                folder_id=items[0]["id"]
                self.driver_folder_ids[relative_path]=folder_id
                return folder_id
            else:
                #create  folder
                self.log.info("=======make dir {}=========".format(relative_path))
                folder_metadata = {'name': folder_name,
                                   'parents': [parent_id],
                                   'mimeType': 'application/vnd.google-apps.folder'}
                create_folder = self.service.files().create(body=folder_metadata,
                                                            fields='id').execute()
                folder_id = create_folder.get('id')
                self.driver_folder_ids[relative_path] = folder_id
                return folder_id


    def os_abs_path_to_relative_path(self,path:str):
        """convert absolute path to relative path"""
        return path[self.local_parent_full_path_depth+1:]

    def os_relative_path_to_abs_path(self,path:str):
        """convert relative path to relative path"""
        return os.path.join(self.local_full_path[:self.local_parent_full_path_depth],path)

    def by_lines(self,input_str):
        """
        Helps Sort items by the number of slashes in it.
        Returns:
            Number of slashes in string.

        """
        return input_str.count(os.path.sep)

    def get_dirver_tree(self, folder_name):
        """
        Gets folder tree relative paths.
        Recursively gets through subfolders, remembers their names and ID's.
        Args:
            folder_name:Name of folder, initially name of parent folder string 相对路径.
            folder_id: ID of folder, initially ID of parent folder.
            tree_list: List of relative folder paths, initially empty list.
            root: Current relative folder path, initially empty string.
            parents_id: Dictionary with pairs of {key:value} like
            {folder's name: folder's Drive ID}, initially empty dict.

        Returns:
            List of folder tree relative folder paths.

        """
        folder_id = self.driver_folder_ids[folder_name]
        items = self.retrieve_all_files(
            query=("%r in parents and \
               mimeType = 'application/vnd.google-apps.folder'and \
               trashed != True" % folder_id))

        for item in items:
            driver_relative_path = os.path.join(folder_name, item['name'])
            self.driver_folder_modifidtime[driver_relative_path]=item["modifiedTime"]
            self.driver_folder_ids[driver_relative_path] = item['id']
            self.get_dirver_tree(driver_relative_path)

    def folder_upload(self):
        '''
        Uploads folder and all it's content ()
        in root folder.
        Args:
            items: List of folders in root path on Google Drive.
            service: Google Drive service instance.
        '''


        for root, _, files in os.walk(OS_FULL_PATH, topdown=True):
            last_dir =os.path.dirname(root)
            pre_last_dir = os.path.dirname(last_dir)
            if pre_last_dir not in self.driver_folder_ids:
                pre_last_dir_id =None
            else:
                pre_last_dir_id = self.driver_folder_ids[pre_last_dir]

            folder_metadata = {'name': last_dir.split(os.path.sep)[-1],
                               'parents': [pre_last_dir_id ] if bool(pre_last_dir_id) else [],
                               'mimeType': 'application/vnd.google-apps.folder'}
            create_folder = self.service.files().create(body=folder_metadata,
                                                   fields='id').execute()
            folder_id = create_folder.get('id')
            for name in files:
                file_metadata = {'name': name, 'parents': [folder_id]}
                media = MediaFileUpload(
                    os.path.join(root, name),
                    mimetype=mimetypes.MimeTypes().guess_type(name)[0])
                self.service.files().create(body=file_metadata,
                                       media_body=media,
                                       fields='id').execute()

            self.driver_folder_ids[last_dir] = folder_id

    def retrieve_all_files(self,query="",**param):
        """Retrieve a list of File resources on google driver by the query.
        Args:
        service: Drive API service instance.
        Returns:
        List of File resources.
        """
        page_token = None
        while True:
            try:
                if page_token:
                    param['pageToken'] = page_token
                param["q"]=query
                param["pageSize"] = 1000
                files = self.service.files().list(**param).execute()
                self.log.debug(files)
                yield from files.get('files', [])
                page_token = files.get('nextPageToken')
                if not page_token:
                    break
            except Exception as e:
                self.log.error('An error occurred: %s' %e)
                break


    def check_upload(self):
        """Checks if folder is already uploaded,
        and if it's not, uploads it.

        Args:
            service: Google Drive service instance.

        Returns:
            ID of uploaded folder
        """
        results = self.service.files().list(
            q="'{}' in parents and trashed != True and \
               mimeType='application/vnd.google-apps.folder'".format(PARENT_DRIVE_FOLDER_ID)).execute()

        items = results.get('files', [])

        # Check if folder exists, and then create it or get this folder's id.
        if DRIVE_FOLDER_NAME in [item['name'] for item in items]:
            folder_id = [item['id'] for item in items
                         if item['name'] == DRIVE_FOLDER_NAME][0]

        else:
            folder_metadata = {'name': DRIVE_FOLDER_NAME,
                               'parents': [PARENT_DRIVE_FOLDER_ID],
                               'mimeType': 'application/vnd.google-apps.folder'}
            create_folder = self.service.files().create(body=folder_metadata,
                                                        fields='id').execute()
            folder_id = create_folder.get('id')

        assert os.path.exists(self.local_full_path)

        return folder_id

    def log_upload_count(self):
        self.log.info(  "count of files: {}".format(self.upload_files_count))

    def log_download_count(self):
        self.log.info(  "count of files: {}".format(self.download_files_count))


    def get_local_modifed_folder(self,filter=False):
        """obtain recently modified folder"""
        os_tree_list = []
        # Get list of folders three paths on computer
        for root, dirs, files in os.walk(self.local_full_path, topdown=True):
            for name in dirs:
                abs_path = os.path.join(root, name)
                if filter:
                    modify_time = os.stat(abs_path).st_mtime
                    if modify_time > time.time() - SCAN_INTERVAL_DAYS * 24 * 60 * 60:
                        os_tree_list.append(self.os_abs_path_to_relative_path(os.path.join(root, name)))
                else:
                    os_tree_list.append(self.os_abs_path_to_relative_path(os.path.join(root, name)))

        return os_tree_list


    def get_driver_modifed_folder(self,filter=False):
        """obtain  modified folder in google driver"""
        dirver_tree_list=[]
        if filter:
            for k,v in self.driver_folder_modifidtime.items():
                if v > time.time() - SCAN_INTERVAL_DAYS * 24 * 60 * 60:
                    dirver_tree_list.append(k)
            return dirver_tree_list
        else:
            return list(self.driver_folder_modifidtime.keys())

    def all(self):
        """deal with all files"""
        raise NotImplemented()
    def additional(self):
        """deal with recently modified files"""
        raise NotImplemented()

    def do_concurrently(self,f,args):
        """do the job concurrently"""
        pool = Pool(processes=self.concurrency)
        pool.starmap(f, args)
        pool.close()
        pool.join()