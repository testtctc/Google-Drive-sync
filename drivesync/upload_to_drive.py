#encoding=utf-8

"""upload local files to google driver"""
import hashlib
import os
from  googleapiclient.http import MediaFileUpload
import mimetypes
from multiprocessing import Pool
from socket import timeout
import traceback
import time
from drivesync.settings import *
from drivesync.common import SyncFiles

class UploadFiles(SyncFiles):

    def __init__(self,**kwargs):
        super(UploadFiles,self).__init__(**kwargs)
        # logger
        self.log = logging.getLogger("upload")

    def _upload_file(self,abs_file:str,file_name,folder_id:int):
        """upload file"""

        try:
            some_metadata = {'name': file_name, 'parents': [folder_id]}
            os_file_mimetype = mimetypes.MimeTypes().guess_type(abs_file)[0]
            media = MediaFileUpload(abs_file, mimetype=os_file_mimetype)
            self.service.files().create(body=some_metadata, media_body=media, fields='id').execute()
            self.debug("upload new file {}".format(abs_file))
        except timeout as e:
            self.log.error("upload timeout")
        except Exception as e:
            traceback.print_stack()
            time.sleep(5)


    def _modify_file(self,file_abs_path,drive_file,file_id,drive_time):
        '''modify file'''
        try:
            # Check files that exist both on Drive and on PC
            file_time = os.path.getmtime(file_abs_path)
            # check md5
            drive_md5 = None
            os_file_md5 = None
            if self.check_md5:
                os_file_md5 = hashlib.md5(open(file_abs_path, 'rb').read()).hexdigest()
                if 'md5Checksum' in drive_file.keys():
                    self.debug(drive_file['md5Checksum'])
                    drive_md5 = drive_file['md5Checksum']

            if (file_time > drive_time) or (self.check_md5 and drive_md5 != os_file_md5):
                file_mimetype = mimetypes.MimeTypes().guess_type(file_abs_path)[0]
                media_body = MediaFileUpload(file_abs_path, mimetype=file_mimetype)
                self.service.files().update(fileId=file_id,
                                            media_body=media_body,
                                            fields='id').execute()
                self.debug("upload file {} for it changes".format(file_abs_path))
        except Exception as e:
            self.log.error(str(e))

    # to sync additionally
    def additional(self):

        self.prepare_driver_service()
        folder_id = self.check_upload()
        folder_name = DRIVE_FOLDER_NAME

        self.driver_folder_ids[folder_name] = folder_id

        os_tree_list = self.get_local_modifed_folder(filter=True)

        self.debug(os_tree_list)

        for folder_dir in os_tree_list:
            folder_id = self.get_folder_id(folder_dir)
            if folder_id:
                pool = Pool(processes=self.concurrency)
                self.info("check folder {} ".format(folder_dir))
                current_dir_abs = self.os_relative_path_to_abs_path(folder_dir)
                os_files = [f for f in os.listdir(current_dir_abs)
                            if os.path.isfile(os.path.join(current_dir_abs, f))]

                items = self.retrieve_all_files(
                    query=('%r in parents and \
                                mimeType!="application/vnd.google-apps.folder" and \
                                trashed != True' % self.driver_folder_ids[folder_dir]),
                    fields="files(id, name, mimeType, \
                                modifiedTime, md5Checksum),nextPageToken")

                # files that need to be refresh
                refresh_files = [f for f in items if f['name'] in os_files]
                # files that need to be remove
                remove_files = [f for f in items if f['name'] not in os_files]
                # new files that should be upload
                upload_files = [f for f in os_files
                                if f not in [j['name'] for j in items]]

                # deal with refresh_files
                # args = [(os.path.join(current_dir_abs, drive_file['name']), drive_file['name'], drive_file['id'],
                #          drive_file["modifiedTime"]) for drive_file in refresh_files]
                # pool.starmap(self._modify_file,args)

                # Upload new files on Drive
                args = [(os.path.join(current_dir_abs, os_file), os_file, self.driver_folder_ids[folder_dir]) for
                        os_file in upload_files]
                pool.starmap(self._upload_file, args)

                # Remove old files from Drive
                if self.do_not_delete_files:
                    self.info("============old files that could be remove from driver==========")
                    self.info(remove_files)
                else:
                    for drive_file in remove_files:
                        file_id = [f['id'] for f in items
                                   if f['name'] == drive_file['name']][0]
                        self.service.files().delete(fileId=file_id).execute()
                        self.debug("remove %s" % drive_file)

                pool.close()
                pool.join()


    def all(self):
        """
        Syncronizes computer folder with Google Drive folder.

        Checks files if they exist, uploads new files and subfolders,
        deletes old files from Google Drive and refreshes existing stuff.
        """
        self.prepare_driver_service()
        # Get id of Google Drive folder and it's path (from other script)
        folder_id = self.check_upload()
        folder_name = self.local_full_path.split(os.path.sep)[-1]
        self.driver_folder_ids[folder_name] = folder_id
        self.get_dirver_tree(folder_name)

        tree_list=set(self.driver_folder_ids.keys())

        os_tree_list   =  set(self.get_local_modifed_folder(filter=False))

        # old folders on drive
        remove_folders = list(tree_list.difference(os_tree_list))
        # new folders on drive, which you dont have(i suppose hehe)
        upload_folders = list(os_tree_list.difference(tree_list))
        # foldes that match
        exact_folders = list(os_tree_list.intersection(tree_list))

        # Add starting directory
        exact_folders.append(folder_name)

        # so now in can be upload from top to down of tree
        upload_folders = sorted(upload_folders, key=self.by_lines)
        self.debug("==========folders that will be removed===========")
        self.debug(remove_folders)
        self.debug("===========folders that will be uploaded===========")
        self.debug(upload_folders)
        self.debug("===========folders that local computer and driver both have===========")
        self.debug(exact_folders)
        self.debug("===========dict of folder path to id===========")
        self.info(self.driver_folder_ids)

        # Here we upload new (abcent on Drive) folders

        for folder_dir in upload_folders:
            self.info("upload folder {} ".format(folder_dir))
            current_dir_abs = self.os_relative_path_to_abs_path(folder_dir)

            last_dir = folder_dir.split(os.path.sep)[-1]

            pre_last_dir =os.path.dirname(folder_dir)

            files = [f for f in os.listdir(current_dir_abs)
                     if os.path.isfile(os.path.join(current_dir_abs, f))]

            folder_metadata = {'name': last_dir,
                               'parents': [self.driver_folder_ids[pre_last_dir]],
                               'mimeType': 'application/vnd.google-apps.folder'}
            create_folder = self.service.files().create(
                body=folder_metadata, fields='id').execute()
            folder_id = create_folder.get('id', [])
            self.driver_folder_ids[folder_dir] = folder_id
            args=[(os.path.join(current_dir_abs, os_file),os_file,folder_id ) for os_file in files]
            pool = Pool(processes=self.concurrency)
            pool.starmap(self._upload_file,args)
            pool.close()
            pool.join()


        self.info("==============finish upload new folder================")

        # start new pool

        for folder_dir in exact_folders:

            pool = Pool(processes=self.concurrency)
            self.info("check folder {} ".format(folder_dir))
            current_dir_abs = self.os_relative_path_to_abs_path(folder_dir)
            os_files = [f for f in os.listdir(current_dir_abs)
                        if os.path.isfile(os.path.join(current_dir_abs, f))]

            items = self.retrieve_all_files(
                query=('%r in parents and \
                mimeType!="application/vnd.google-apps.folder" and \
                trashed != True' % self.driver_folder_ids[folder_dir]),
                fields="nextPageToken,files(id, name, mimeType, \
                modifiedTime, md5Checksum)")
            self.debug([j['name']for j in items])
            #files that need to be refresh
            refresh_files = [f for f in items if f['name'] in os_files]
            #files that need to be remove
            remove_files = [f for f in items if f['name'] not in os_files]
            # new files that should be upload
            upload_files = [f for f in os_files if f not in [j['name']for j in items]]

            # deal with refresh_files
            args =[(os.path.join(current_dir_abs, drive_file['name']),drive_file['name'],drive_file['id'],drive_file["modifiedTime"]) for drive_file in refresh_files]
            #pool.starmap(self._modify_file,args)

            # Upload new files on Drive
            self.info("=============={}  files  will be upload ===================".format(len(upload_files)))
            args = [(os.path.join(current_dir_abs, os_file), os_file, self.driver_folder_ids[folder_dir]) for os_file in upload_files]
            pool.starmap(self._upload_file, args)


            # Remove old files from Drive
            if self.do_not_delete_files:
                self.info("============old files that could be remove from driver==========")
                self.info(remove_files)
            else:
                for drive_file in remove_files:
                    file_id = [f['id'] for f in items
                               if f['name'] == drive_file['name']][0]
                    self.service.files().delete(fileId=file_id).execute()
                    self.debug("remove %s"%drive_file)

            pool.close()
            pool.join()

        self.info("==============finish check exact folders===============")

        #delete deepest folder first
        remove_folders = sorted(remove_folders, key=self.by_lines, reverse=True)
        # Delete old folders from Drive
        if self.do_not_delete_files:
            self.info("============old folders that local computer has deleted ==========")
            self.info(remove_folders)
        else:
            for folder_dir in remove_folders:
                folder_id = self.driver_folder_ids[folder_dir]
                self.service.files().delete(fileId=folder_id).execute()

        self.info("============the total count of uploaded files===============")
        self.info(self.upload_files_count)


if __name__ == '__main__':
    program = UploadFiles()
    #program.all()
    program.additional()
