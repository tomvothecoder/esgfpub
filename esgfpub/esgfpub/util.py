"""
Utility functions for esgfpub
"""

import os
import sys
import stat
import argparse
import json
from subprocess import call, Popen, PIPE
from datetime import datetime
from shutil import move, copy
from time import sleep
from tqdm import tqdm
from esgfpub import resources
from esgfpub.version import __version__
from tempfile import NamedTemporaryFile


def parse_args():
    parser = argparse.ArgumentParser(prog='esgfpub')
    subparsers = parser.add_subparsers(
        title='subcommands',
        description='valid subcommands',
        dest='subparser_name')

    parser_publish = subparsers.add_parser(
        'stage', help='Move data and generate mapfiles')
    parser_publish.add_argument(
        "config",
        help="Path to configuration file")
    parser_publish.add_argument(
        "--mapfile-env",
        required=True,
        help="The name of the conda env with the esgmapfile utility installed")
    parser_publish.add_argument(
        "-t",
        "--transfer-mode",
        default='link',
        help="the file transfer mode, allowed values are link, move, or copy")
    parser_publish.add_argument(
        '--over-write',
        help="Over write any existing files",
        action='store_true')
    parser_publish.add_argument(
        '-o',
        '--output-mapfiles',
        dest='mapout',
        help='The output location for mapfiles, defaults to ./mapfiles/',
        default='./mapfiles')
    parser_publish.add_argument(
        '--debug',
        action="store_true")

    parser_esgf_check = subparsers.add_parser(
        'check', help='Check the file structure and ESGF database for missing datasets')
    resource_path, _ = os.path.split(resources.__file__)
    parser_esgf_check.add_argument(
        '-p',
        '--projects',
        default=['CMIP6', 'E3SM'],
        help='Which projects to check for, valid arguments are cmip6 or e3sm. Default is both CMIP6 and E3SM')
    parser_esgf_check.add_argument(
        '-e',
        '--experiments',
        nargs="+",
        default=['all'],
        help="Which case to check the data for, default is all")
    parser_esgf_check.add_argument(
        '-v',
        '--variables',
        nargs="+",
        default=['all'],
        help="Which variables to check for, default is all")
    parser_esgf_check.add_argument(
        '-t',
        '--tables',
        nargs="+",
        default=['all'],
        help="List of CMIP6 tables or E3SM components to search for, default is all")
    parser_esgf_check.add_argument(
        '--ens',
        '--ensembles',
        nargs="+",
        default=['all'],
        help="List of ensemble members to check, default all")
    parser_esgf_check.add_argument(
        '-d',
        '--dataset-ids',
        nargs='+',
        help='One or more dataset IDs to check, if this option is turned on only these datasets will be checked')
    parser_esgf_check.add_argument(
        '--published',
        action="store_true",
        help="Check the LLNL ESGF node to see if the variables have been published")
    parser_esgf_check.add_argument(
        '-m',
        '--num-workers',
        type=int,
        default=4,
        help="The number of dask workers used in the localCluster, default: 4")
    parser_esgf_check.add_argument(
        '--sproket',
        default='sproket',
        help='Path to custom sproket binary, only needed if --published is turned on.')
    parser_esgf_check.add_argument(
        '--file-system',
        action="store_true",
        help="Check the data is present on the filesystem under the --data-path directory")
    parser_esgf_check.add_argument(
        '--data-path',
        help="path to the root directory containing the local data")
    parser_esgf_check.add_argument(
        '--model-versions',
        dest='model_versions',
        nargs='+',
        default='all',
        help="versions of the model to add to the search, default is all")
    parser_esgf_check.add_argument(
        '--data-types',
        dest='data_types',
        nargs='+',
        default=['all'],
        help="which data-types to search for, default is all")
    parser_esgf_check.add_argument(
        '--data-version',
        dest='data_version',
        default='latest',
        help="version of the data to search for, default is the latest")
    parser_esgf_check.add_argument(
        '--exclude',
        nargs='+',
        default=['none'],
        help="A list of any variables, tables, model_versions, or projects to skip")
    parser_esgf_check.add_argument(
        '--verify',
        action="store_true",
        help="Run a std deviation test on global mean for each variable")
    parser_esgf_check.add_argument(
        '--plot-path',
        help="Where to store verification plots")
    parser_esgf_check.add_argument(
        '--spec-path',
        default=os.path.join(resource_path, 'dataset_spec.yaml'),
        help="Path to custom dataset specification file")
    parser_esgf_check.add_argument(
        '--to-json',
        help='The output will be stored in the given file, json format')
    parser_esgf_check.add_argument(
        '--report-plot',
        help="path to where the plot report should be saved, requires json output and digest")
    parser_esgf_check.add_argument(
        '--digest',
        action="store_true",
        help='Only report one line per dataset with missing files')
    parser_esgf_check.add_argument(
        '-s',
        '--serial',
        action='store_true',
        help='Should this be run in serial, default is parallel.')
    parser_esgf_check.add_argument(
        '--local-cluster',
        help='The port number for the local cluster to connect to, if not given a new cluster is created')
    parser_esgf_check.add_argument(
        '--debug',
        action="store_true")

    parser_publish = subparsers.add_parser(
        'publish', help='Publish a directory of mapfiles to ESGF')
    parser_publish.add_argument(
        '--maps-in',
        help="Path to input mapfile directory")
    parser_publish.add_argument(
        '--maps-done',
        help="Path to where complete mapfiles should be moved to")
    parser_publish.add_argument(
        '--maps-err',
        help="Path to where errored mapfiles should be moved to")
    parser_publish.add_argument(
        '--logs',
        default=os.path.join(os.environ['PWD'], 'logs'),
        help=f"Path to where publication logs should be stored, default is {os.environ['PWD']}/logs")
    parser_publish.add_argument(
        '--loop',
        action="store_true",
        help="If set, this will cause the publisher to loop continuously and publish any mapfiles placed in the input directory")
    parser_publish.add_argument(
        '--sproket',
        default='sproket',
        help="path to sproket binary if its not in your PATH")
    parser_publish.add_argument(
        '--no-custom',
        action="store_true",
        help="dont do the custom facet update")
    parser_publish.add_argument(
        '--debug',
        action="store_true")

    parser_custom = subparsers.add_parser(
        'custom', help='Update the custom facets for a list of datasets')
    parser_custom.add_argument(
        '-d', '--data-dir',
        dest='datadir',
        nargs="+",
        help="root of data directory")
    parser_custom.add_argument(
        '-i',
        '--dataset-ids',
        nargs='+',
        help='One or more dataset IDs to update, if this option is turned on only these datasets will be checked')
    parser_custom.add_argument(
        '--facets',
        nargs='+',
        required=True,
        help="sequence of var=value pairs")
    parser_custom.add_argument(
        '--debug',
        action="store_true",
        help="turn on debug prints")
    parser_custom.add_argument(
        "--version",
        action="version",
        version='%(prog)s' + f'{__version__}',
        help="show program version and exit")
    return parser.parse_args(sys.argv[1:])


class colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_message(message, status='error'):
    """
    Prints a message with either a green + or a red -

    Parameters:
        message (str): the message to print
        status (str): the status class of the message, should be "error", "ok", or "info"
    """
    now = datetime.now()

    hour = now.strftime('%H')
    minutes = now.strftime('%M')
    sec = now.strftime('%S')

    if status == 'error':
        start_icon = '[-]'
        start_color = colors.FAIL

    elif status == 'info':
        start_icon = '[=]'
        start_color = colors.OKBLUE

    else:
        start_icon = '[+]'
        start_color = colors.OKGREEN

    timestr = f'{start_color}{start_icon}{colors.ENDC} {now.year}/{now.month}/{now.day} - {hour}:{minutes}:{sec}'
    msg = f"{timestr}:  {message}"
    print(msg, flush=True)


def makedir(directory):
    """
    Make a directory if it doesn't already exist
    """
    if not os.path.exists(directory):
        os.makedirs(directory)


def get_atm_casename(filename):
    i = filename.index(".cam.h0")
    if i == -1:
        return -1
    return filename[:i]


def get_lnd_casename(filename):
    i = filename.index(".clm2.h0")
    if i == -1:
        return -1
    return filename[:i]


def validate_raw(data_paths, start, end):
    """
    Checks that the atmos, land, sea-ice, and ocean raw files are present
    returns True if all files are found, False otherwise
    """
    missing = False
    if 'atmos' in data_paths:
        files = sorted(os.listdir(data_paths['atmos']))
        if not files:
            print("no atm files found")
        else:
            casename = get_atm_casename(files[0])
            if casename == -1:
                raise ValueError(
                    "Unable to find casename from {}".format(files[0]))
            for year in range(start, end + 1):
                for month in range(1, 13):
                    name = "{}.cam.h0.{:04d}-{:02d}.nc".format(
                        casename, year, month)
                    if name not in files:
                        print("{} is missing".format(name))
                        missing = True

    if "land" in data_paths:
        files = sorted(os.listdir(data_paths['land']))
        if not files:
            print("no land files found")
        else:
            casename = get_lnd_casename(files[0])
            if casename == -1:
                raise ValueError(
                    "Unable to find casename from {}".format(files[0]))
            for year in range(start, end + 1):
                for month in range(1, 13):
                    name = "{}.clm2.h0.{:04d}-{:02d}.nc".format(
                        casename, year, month)
                    if name not in files:
                        print("{} is missing".format(name))
                        missing = True

    if "sea-ice" in data_paths:
        files = sorted(os.listdir(data_paths['sea-ice']))
        if not files:
            print("no ice files found")
        else:
            for year in range(start, end + 1):
                for month in range(1, 13):
                    name = "mpascice.hist.am.timeSeriesStatsMonthly.{:04d}-{:02d}-01.nc".format(
                        year, month)
                    if name not in files:
                        print("{} is missing".format(name))
                        missing = True

    if "ocean" in data_paths:
        files = sorted(os.listdir(data_paths['ocean']))
        if not files:
            print("no ocn files found")
        else:
            for year in range(start, end + 1):
                for month in range(1, 13):
                    name = "mpaso.hist.am.timeSeriesStatsMonthly.{:04d}-{:02d}-01.nc".format(
                        year, month)
                    if name not in files:
                        print("{} is missing".format(name))
                        missing = True

    if missing:
        return False
    else:
        return True


def transfer_files(outpath, experiment, mode, grid, data_paths, ensemble, overwrite):
    """
    Move or copy data into the ESGF publication structure

    Parameters
    ----------
        outpath (str): the base of the ESGF publication structure
        mode (str): either 'move' or 'copy'
        experiment (str): the name of the experiment being published
        grid (str): the non-native grid name
        data_paths (dict): a dictionary with keys with the file type name, and values of the
            path to where those files are stored
    Returns
    -------
        number of files transfer if everything completed successfully
        -1 on error
    """
    if mode not in ['copy', 'move', 'link']:
        raise ValueError('{} is not a supported mode'.format(mode))
    if mode == 'move':
        transfer = move
    elif mode == 'link':
        transfer = os.symlink
    else:
        transfer = copy

    resolution_dir = os.listdir(os.path.join(outpath, experiment))[0]
    num_transfered = 0
    dataset_paths = list()

    for dtype, path in list(data_paths.items()):
        contents = os.listdir(path)

        for _, item in enumerate(tqdm(contents, desc="{}: ".format(dtype))):

            src = os.path.join(path, item)
            dst = setup_dst(
                experiment=experiment,
                basepath=outpath,
                res_dir=resolution_dir,
                grid=grid,
                datatype=dtype,
                filename=item,
                ensemble=ensemble)
            if os.path.exists(dst) and not overwrite:
                continue
            num_transfered += 1
            tail, _ = os.path.split(dst)
            if not os.path.exists(tail):
                os.makedirs(tail)
            if tail not in dataset_paths:
                dataset_paths.append(tail)

            if os.path.exists(dst) or os.path.lexists(dst):
                if overwrite:
                    os.remove(dst)
                else:
                    print("Skipping {}".format(dst))
                    continue

            if not os.path.exists(src):
                print_message('{} does not exist'.format(src))
                continue
            try:
                transfer(src, dst)
            except OSError as error:
                print(src, dst)
                print(repr(error))
                return -1

    return num_transfered, dataset_paths


def mapfile_gen(basepath, inipath, outpath, maxprocesses, pbar, env_name, event=None, debug=False):
    """
    Generate mapfiles for ESGF

    Parameters
    ----------
        basepath (str): the base of the data, the case directory should be below this
        inipath (str): path to directory with ini files
        experiment (str): the name of the experiment to generate mapfiles for
        outpath (str): the path to were the mapfiles should be stored after generation
        maxprocesses (str): the number of processes to use for hashing
        event (threading.Event): an event to terminate the process early
        pbar (tqdm): a tqdm progressbar
    """
    pbar.set_description("Hashing files for {}".format(
        path_to_dataset_id(basepath)))
    run_mapfile_string = """#!/bin/bash
source ~/anaconda3/etc/profile.d/conda.sh
conda activate {env} 
esgmapfile make --debug --outdir {out} -i {ini} --project e3sm --max-processes {procs} {data}
""".format(
        out=outpath,
        env=env_name,
        procs=maxprocesses,
        ini=inipath,
        data=basepath)
    if debug:
        print_message(run_mapfile_string, 'info')
    script = 'run_mapfiles.sh'
    if os.path.exists(script):
        os.remove(script)
    with open(script, 'w') as op:
        op.write(run_mapfile_string)
    st = os.stat(script)
    os.chmod(script, st.st_mode | stat.S_IEXEC)

    proc = Popen(['./' + script], stdout=PIPE, stderr=PIPE)

    # cmd = ['esgmapfile', 'make',
    #        '--outdir', outpath,
    #        '-i', inipath,
    #        '--project', 'e3sm',
    #        '--max-processes', str(maxprocesses),
    #        '--debug',
    #        datapath]
    # proc = Popen(cmd, stdout=PIPE, stderr=PIPE)
    while proc.poll() is None:
        if event is not None and event.is_set():
            proc.terminate()
        for line in proc.stdout:
            if "SUCCESS" in line.decode('utf-8'):
                pbar.update(1)
            if debug:
                print_message(line, 'info')
        for line in proc.stderr:
            print(line.decode('utf-8'))
    err = proc.stderr.readlines()
    if err:
        for line in err:
            print(line)
        return 1
    else:
        return 0


def setup_dst(experiment, basepath, res_dir, grid, datatype, filename, ensemble):
    """
    Find the destination path for a file
    """
    freq = 'mon'
    dstgrid = 'native'
    if datatype in ['atmos', 'atmos_regrid', 'atmos_ts', 'atmos_daily']:
        type_dir = 'atmos'
        if datatype == 'atmos':
            output_type = 'model-output'
        elif datatype == 'atmos_daily':
            freq = 'day'
            output_type = 'model-output'
        elif datatype == 'atmos_ts':
            output_type = 'time-series'
            dstgrid = grid
        elif datatype == 'atmos_regrid':
            output_type = 'model-output'
            dstgrid = grid
    elif datatype in ['land', 'land_regrid']:
        if datatype == 'land_regrid':
            dstgrid = grid
        type_dir = 'land'
        output_type = 'model-output'
    elif datatype == 'ocean':
        type_dir = 'ocean'
        output_type = 'model-output'
        grid = 'native'
    elif datatype == 'sea-ice':
        type_dir = 'sea-ice'
        output_type = 'model-output'
        grid = 'native'
    elif datatype == 'climo':
        type_dir = 'atmos'
        output_type = 'climo'
        dstgrid = grid
        freq = 'mon'
    elif datatype == 'timeseries_atm':
        type_dir = 'atmos'
        output_type = 'time-series'
        dstgrid = grid
        freq = 'mon'
    elif datatype == 'timeseries_lnd':
        type_dir = 'land'
        output_type = 'time-series'
        dstgrid = grid
        freq = 'mon'
    else:
        raise Exception('{} is an invalid data type'.format(datatype))

    new_path = os.path.join(
        basepath,
        experiment,
        res_dir,
        type_dir,
        dstgrid,
        output_type,
        freq,
        ensemble,
        'v1',
        filename)
    return new_path


def path_to_dataset_id(path):
    if 'CMIP6' in path:
        p = path.split(os.sep)
        dataset_id = '.'.join(p[p.index('CMIP6'):-2])
        return dataset_id
    else:
        p = path.split(os.sep)
        dataset_id = '.'.join(p[p.index('E3SM'):-2])
        return dataset_id


def check_ds_exists(dataset_id, debug=False, sproket='sproket', **kwargs):
    """
    Use sproket to lookup a dataset by its ID, if the dataset exists
    return True, else returns False
    """
    # create the path to the config, write it out
    tempfile = NamedTemporaryFile(suffix='.json')
    with open(tempfile.name, mode='w') as tmp:
        config_string = json.dumps({
            'search_api': "https://esgf-node.llnl.gov/esg-search/search/",
            'data_node_priority': ["aims3.llnl.gov", "esgf-data1.llnl.gov", "esgf-data2.llnl.gov"],
            'fields': {
                'dataset_id': dataset_id
            }
        })

        tmp.write(config_string)
        tmp.seek(0)

        cmd = [sproket, '-config', tempfile.name, '-y', '-urls.only']
        # if debug:
        #     msg = 'Running sproket command: {}'.format(cmd)
        #     print_message(msg, 'info')

        proc = Popen(cmd, shell=False, stdout=PIPE, stderr=PIPE)
        out, err = proc.communicate()
    if err:
        print(err.decode('utf-8'))
        return False
    else:
        if debug:
            print_message(out, 'info')
        if out:
            return True
        else:
            return False
