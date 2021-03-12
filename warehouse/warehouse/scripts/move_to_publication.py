import sys
import os
import argparse
from pathlib import Path
from subprocess import Popen, PIPE

def parse_args():
    parser = argparse.ArgumentParser(
        description="Move all files from given source directory to given destination directory.  Move parent source directory \".mapfile\", if it exists, to the parent destination directory, along with the corresponding \".status\" file.")
    parser.add_argument('--src-path', type=str, dest='src', required=True, help="source directory of netCDF files to be moved")
    parser.add_argument('--dst-path', type=str, dest='dst', required=True, help="destination directory for netCDF files to be moved")
    return parser.parse_args()

def validate_args(args):
    ''' Ensure the src path exists and is not empty.
        Ensure the dst path exists and is empty.
    '''
    src_path = Path(args.src)
    dst_path = Path(args.dst)
    if not src_path.exists() or not src_path.is_dir():
        # raise ValueError("Source directory does not exist or is not a directory")
        print("Source directory does not exist or is not a directory")
        return False
    if not any(src_path.iterdir()):
        # raise ValueError("Source directory is empty")
        print("Source directory is empty")
        return False

    if not dst_path.exists() or not dst_path.is_dir():
        # raise ValueError("Destination directory does not exist or is not a directory")
        print("Destination directory does not exist or is not a directory")
        return False
    if any(dst_path.iterdir()):
        # raise ValueError("Destination directory is not empty")
        print("Destination directory is not empty")
        return False

    return True

def conduct_move(args):
    src_path = Path(args.src)
    dst_path = Path(args.dst)
    
    for afile in src_path.glob('*.nc'): # all .nc files
        result = afile.replace(dst_path / afile.name)

    return 0

def main():
    parsed_args = parse_args()

    if not validate_args(parsed_args):
        sys.exit(1)

    retcode = conduct_move(parsed_args)
    sys.exit(retcode)


    return True

if __name__ == "__main__":
    sys.exit(main())
