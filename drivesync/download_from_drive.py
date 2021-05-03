#!/usr/bin/python3

"""Initial comment."""

import datetime
import io
import os
import shutil
import time
import hashlib
from googleapiclient.http import MediaIoBaseDownload
from drivesync.common import SyncFiles
from drivesync.settings import  SCAN_INTERVAL_DAYS
APPLICATION_NAME = 'Drive Sync'

GOOGLE_MIME_TYPES = {
    'application/vnd.google-apps.document':
    ['application/vnd.openxmlformats-officedocument.wordprocessingml.document',
     '.docx'],
    # 'application/vnd.google-apps.document':
    # 'application/vnd.oasis.opendocument.text',
    'application/vnd.google-apps.spreadsheet':
    ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
     '.xlsx'],
    # 'application/vnd.oasis.opendocument.spreadsheet',
    'application/vnd.google-apps.presentation':
    ['application/vnd.openxmlformats-officedocument.presentationml.presentation',
     '.pptx']
}

class DownloadFiles(SyncFiles):
    def __init__(self,**kwargs):
        super(DownloadFiles,self).__init__(**kwargs)


    def download_file_from_gdrive(self,file_path, drive_file):
        """Downloads file from Google Drive.

        If file is Google Doc's type, then it will be downloaded
        with the corresponding non-Google mimetype.

        Args:
            path: Directory string, where file will be saved.
            file: File information object (dictionary), including it's name, ID
            and mimeType.
        """
        file_id = drive_file['id']
        file_name = drive_file['name']
        if drive_file['mimeType'] in GOOGLE_MIME_TYPES.keys():
            if file_name.endswith(GOOGLE_MIME_TYPES[drive_file['mimeType']][1]):
                file_name = drive_file['name']
            else:
                file_name = '{}{}'.format(
                    drive_file['name'],
                    GOOGLE_MIME_TYPES[drive_file['mimeType']][1])
                self.service.files().update(fileId=file_id,
                                       body={'name': file_name}).execute()


            request = self.service.files().export(
                fileId=file_id,
                mimeType=(GOOGLE_MIME_TYPES[drive_file['mimeType']])[0]).execute()
            with io.FileIO(os.path.join(file_path, file_name), 'wb') as file_write:
                file_write.write(request)

        else:
            request = self.service.files().get_media(fileId=file_id)
            file_io = io.FileIO(os.path.join(file_path, drive_file['name']), 'wb')
            downloader = MediaIoBaseDownload(file_io, request)
            done = False
            while done is False:
                _, done = downloader.next_chunk()

    def download_same_check(self,drive_file,abs_dir_path):
        """
        Args:
            drive_file: google drive file
            file: file name
            abs_dir_path: absoluye local dir path
        Returns: None
        """

        file = os.path.join(abs_dir_path, drive_file['name'])
        file_time = os.path.getmtime(file)
        mtime = datetime.datetime.strptime(drive_file['modifiedTime'][:-2],
                                           "%Y-%m-%dT%H:%M:%S.%f")
        drive_time = time.mktime(mtime.timetuple())
        file_dir = os.path.join(abs_dir_path, drive_file['name'])
        # flag
        is_same_md5 = True
        if self.check_md5:
            os_file_md5 = hashlib.md5(open(file_dir, 'rb').read()).hexdigest()
            if 'md5Checksum' in drive_file.keys():
                drive_md5 = drive_file['md5Checksum']
            else:
                drive_md5 = None
            if drive_md5 != os_file_md5:
                is_same_md5 = False

        if (file_time < drive_time) or (not is_same_md5):
            os.remove(os.path.join(abs_dir_path, drive_file['name']))
            self.download_file_from_gdrive(abs_dir_path, drive_file)


    def all(self):
        folder_id = self.check_upload()

        self.driver_folder_ids[self.driver_path] = folder_id

        self.get_dirver_tree(self.driver_path)
        tree_list=self.driver_folder_ids.keys()

        os_tree_list = self.get_local_modifed_folder()
        os_tree_list=set(os_tree_list)

        # folders that exitst on driver but not on local
        download_folders = list(tree_list.difference(os_tree_list))

        # new folders on computer, which you dont have(i suppose heh)
        remove_folders = list(os_tree_list.difference(tree_list))

        # foldes that match
        exact_folders = list(os_tree_list.intersection(tree_list))

        exact_folders.append(self.driver_path)


        # Download folders from Drive
        download_folders = sorted(download_folders, key=self.by_lines)

        for folder_dir in download_folders:
            abs_dir_path =self.os_relative_path_to_abs_path(folder_dir)
            last_dir = folder_dir.split(os.path.sep)[-1]
            folder_id = self.driver_folder_ids[last_dir]
            results = self.service.files().list(
                pageSize=20, q=('%r in parents' % folder_id)).execute()

            items = results.get('files', [])
            os.makedirs(abs_dir_path)
            files = [f for f in items
                     if f['mimeType'] != 'application/vnd.google-apps.folder']

            self.do_concurrently(self.download_file_from_gdrive,[(abs_dir_path,f)for f in files])

        # Check and refresh files in existing folders
        for folder_dir in exact_folders:
            # var = '/'.join(full_path.split('/')[0:-1]) + '/'
            abs_dir_path = self.os_relative_path_to_abs_path(folder_dir)
            last_dir = folder_dir.split(os.path.sep)[-1]
            os_files = [f for f in os.listdir(abs_dir_path)
                        if os.path.isfile(os.path.join(abs_dir_path,f))]
            folder_id = self.driver_folder_ids[last_dir]

            results=self.retrieve_all_files(
                q=('%r in parents and \
                mimeType!="application/vnd.google-apps.folder"' % folder_id),
                fields="nextPageToken,files(id, name, mimeType, \
                    modifiedTime, md5Checksum)")

            items = [i for i in results]

            refresh_files = [f for f in items if f['name'] in os_files]
            upload_files = [f for f in items if f['name'] not in os_files]
            remove_files = [f for f in os_files
                            if f not in [j['name']for j in items]]

            #更新文件
            self.do_concurrently(self.download_same_check,[(f,abs_dir_path) for f in refresh_files])

            for os_file in remove_files:
                if self.do_not_delete_files:
                    self.info("delete file {}".format(os_file))
                os.remove(os.path.join(abs_dir_path, os_file))
            self.do_concurrently(self.download_file_from_gdrive, [(abs_dir_path,f) for f in upload_files])

        # Delete old and unwanted folders from computer
        remove_folders = sorted(remove_folders, key=self.by_lines, reverse=True)
        for folder_dir in remove_folders:
            variable =self.os_relative_path_to_abs_path(folder_dir)
            shutil.rmtree(variable)

    def additional(self):
        """only down load recently modify files"""
        folder_id = self.check_upload()

        self.driver_folder_ids[self.driver_path] = folder_id

        self.get_dirver_tree(self.driver_path)
        compare_base= time.time() - SCAN_INTERVAL_DAYS * 24 * 60 * 60
        #tree that after filter
        tree_list=[k for k,v  in self.driver_folder_modifidtime.items() if v >compare_base ]

        os_tree_list = self.get_local_modifed_folder()
        os_tree_list=set(os_tree_list)

        # folders that exitst on driver but not on local
        download_folders = list(tree_list.difference(os_tree_list))

        # new folders on computer, which you dont have(i suppose heh)
        remove_folders = list(os_tree_list.difference(tree_list))

        # foldes that match
        exact_folders = list(os_tree_list.intersection(tree_list))

        exact_folders.append(self.driver_path)


        # Download folders from Drive
        download_folders = sorted(download_folders, key=self.by_lines)

        for folder_dir in download_folders:
            abs_dir_path =self.os_relative_path_to_abs_path(folder_dir)
            last_dir = folder_dir.split(os.path.sep)[-1]
            folder_id = self.driver_folder_ids[last_dir]
            results = self.service.files().list(
                pageSize=20, q=('%r in parents' % folder_id)).execute()

            items = results.get('files', [])
            os.makedirs(abs_dir_path)
            files = [f for f in items
                     if f['mimeType'] != 'application/vnd.google-apps.folder']

            self.do_concurrently(self.download_file_from_gdrive,[(abs_dir_path,f)for f in files])

        # Check and refresh files in existing folders
        for folder_dir in exact_folders:
            # var = '/'.join(full_path.split('/')[0:-1]) + '/'
            abs_dir_path = self.os_relative_path_to_abs_path(folder_dir)
            last_dir = folder_dir.split(os.path.sep)[-1]
            os_files = [f for f in os.listdir(abs_dir_path)
                        if os.path.isfile(os.path.join(abs_dir_path,f))]
            folder_id = self.driver_folder_ids[last_dir]
            results=self.retrieve_all_files(
                q=('%r in parents and \
                mimeType!="application/vnd.google-apps.folder"' % folder_id),
                fields="nextPageToken,files(id, name, mimeType, \
                    modifiedTime, md5Checksum)")

            items = [i for i in results]

            refresh_files = [f for f in items if f['name'] in os_files]
            upload_files = [f for f in items if f['name'] not in os_files]
            remove_files = [f for f in os_files
                            if f not in [j['name']for j in items]]

            #更新文件
            self.do_concurrently(self.download_same_check,[(f,abs_dir_path) for f in refresh_files])

            for os_file in remove_files:
                if self.do_not_delete_files:
                    self.info("delete file {}".format(os_file))
                os.remove(os.path.join(abs_dir_path, os_file))
            self.do_concurrently(self.download_file_from_gdrive, [(abs_dir_path,f) for f in upload_files])

        # Delete old and unwanted folders from computer
        remove_folders = sorted(remove_folders, key=self.by_lines, reverse=True)
        for folder_dir in remove_folders:
            variable =self.os_relative_path_to_abs_path(folder_dir)
            shutil.rmtree(variable)


if __name__ == '__main__':
    download = DownloadFiles()
    download.all()
    download.additional()
