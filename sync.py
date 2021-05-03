# encoding=utf-8
import argparse
from drivesync.upload_to_drive import UploadFiles
from drivesync.download_from_drive import DownloadFiles
import drivesync.settings as config

def main():
    parser = argparse.ArgumentParser(description='sync local withe google drive')

    parser.add_argument('--log_level',type=str, choices=['debug','warn','info'],default="info")

    parser.add_argument('--check_md5',action="store_true",default=False)

    parser.add_argument('--do_not_delete',
                        help='do not delete files',action="store_false",default=True)

    parser.add_argument('--not_check_same',
                        help='do not check modified file',action="store_false",default=True)

    parser.add_argument('--parent_folder_id',dest='folder_id',default='',
                        help=' the folder id of  the parent  of the folder you want sync in google driver ')

    parser.add_argument('--local_abs_path',dest='local_path',default='',
                        help='local absolute path')

    parser.add_argument('--folder_name',default='',
                        help='the folder name in google driver')


    subparsers = parser.add_subparsers(help='upload or download',dest='command')

    upload_cmd= subparsers.add_parser("upload")
    download_cmd=subparsers.add_parser("download")


    upload_cmd.add_argument('--all',
                        help='upload all file',action="store_true",default=False)

    upload_cmd.add_argument('--days',type=int,
                        help='upload recently updated files')


    download_cmd.add_argument('--all',
                        help='download all file',action="store_true")

    download_cmd.add_argument('--days',type=int,
                        help='download recently updated files')



    args = parser.parse_args()

    if args.folder_id:
        config.PARENT_DRIVE_FOLDER_ID = args.folder_id
    if args.local_path:
        config.OS_FULL_PATH = args.local_path
    if args.folder_name:
        config.DRIVE_FOLDER_NAME = args.folder_name

    if args.command =="upload":
        upload =  UploadFiles(do_not_delete_files=args.do_not_delete,
                              log_level=args.log_level.upper(),
                              check_md5=args.check_md5,
                              do_not_check_same_file=args.not_check_same)
        if args.all:
            upload.all()
        else:
            upload.additional()


    elif args.command =="download":
        download=DownloadFiles(do_not_delete_files=args.do_not_delete,
                              log_level=args.log_level.upper(),
                              check_md5=args.check_md5,
                              do_not_check_same_file=args.not_check_same)
        if args.all:
            download.all()
        else:
            download.additional()
    else:
        print("please use subcommand")

if __name__ == "__main__":
    main()