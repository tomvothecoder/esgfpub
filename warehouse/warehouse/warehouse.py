import os
import sys
import yaml
import json
import importlib
import inspect

from pathlib import Path
from time import sleep
from tqdm import tqdm
from concurrent.futures import ProcessPoolExecutor, as_completed
from termcolor import colored, cprint

from warehouse.workflows import Workflow
from warehouse.dataset import Dataset, DatasetStatus
from warehouse.slurm import Slurm
from warehouse.listener import Listener
import warehouse.resources as resources

DEFAULT_WAREHOUSE_PATH = '/p/user_pub/e3sm/warehouse/'
DEFAULT_PUBLICATION_PATH = '/p/user_pub/work/'
DEFAULT_ARCHIVE_PATH = '/p/user_pub/e3sm/archive'

resource_path, _ = os.path.split(resources.__file__)
DEFAULT_SPEC_PATH = os.path.join(resource_path, 'dataset_spec.yaml')
NAME = 'auto'


class AutoWarehouse():

    def __init__(self, *args, **kwargs):
        super().__init__()

        self.warehouse_path = Path(kwargs.get(
            'warehouse_path', DEFAULT_WAREHOUSE_PATH))
        self.publication_path = Path(kwargs.get(
            'publication_path', DEFAULT_PUBLICATION_PATH))
        self.archive_path = Path(kwargs.get(
            'archive_path', DEFAULT_ARCHIVE_PATH))
        self.spec_path = Path(kwargs.get('spec_path', DEFAULT_SPEC_PATH))
        self.sproket_path = kwargs.get('sproket', 'sproket')
        self.num_workers = kwargs.get('num', 8)
        self.serial = kwargs.get('serial', False)
        self.testing = kwargs.get('testing', False)
        self.dataset_ids = kwargs.get('dataset_id')
        self.sproket_path = kwargs.get('sproket', 'sproket')
        self.slurm_path = kwargs.get('slurm', 'slurm_scripts')
        self.report_missing = kwargs.get('report_missing')
        self.job_workers = kwargs.get('job_workers', 8)
        self.datasets = None
        self.datasets_from_path = kwargs.get('datasets_from_path', False)
        os.makedirs(self.slurm_path, exist_ok=True)
        self.should_exit = False

        self.scripts_path = Path(Path(inspect.getfile(
            self.__class__)).parent.absolute(), 'scripts').resolve()

        if not self.report_missing:
            self.workflow = kwargs.get('workflow', Workflow(slurm_scripts=self.slurm_path))
            
            self.workflow.load_children()
            self.workflow.load_transitions()

            # this is a list of WorkflowJob objects
            self.job_pool = {}

            # create the local Slurm object
            self.slurm = Slurm()

            # create the filesystem listener
            self.listener = Listener(warehouse=self)
            self.listener.start()

        if self.serial:
            cprint("Running warehouse in serial mode", 'cyan')
        else:
            cprint(
                f"Running warehouse in parallel mode with {self.num_workers} workers", 'white')

        with open(self.spec_path, 'r') as instream:
            self.dataset_spec = yaml.load(instream, Loader=yaml.SafeLoader)

    def status_was_updated(self, path):
        """
        This should be called whenever a datasets status file is updated
        Parameters: path (str) -> the path to the directory containing the status file
        """
        # import ipdb; ipdb.set_trace()
        dataset_id = None
        path_split = path.split(os.sep)
        length = len(path_split)
        for i in range(1, length):
            test = '.'.join(path_split[length - i : -1])
            if test in self.datasets.keys():
                dataset_id = test
                break
        if dataset_id is None:
            print("something went wrong")
            import ipdb; ipdb.set_trace()

        # update the datasets status with the value just put into the status file
        print(f"Got a status update from {dataset_id}")
        dataset = self.datasets[dataset_id]
        dataset.load_dataset_status_file()

        # check to see of there's a slurm ID in the second to last status
        # and if there is, and the latest is either Pass or Fail, then 
        # remove the job from the job_pool
        latest, second_latest = dataset.get_latest_status()
        if second_latest is not None:
            latest_attrs = latest.split(':')
            second_latest_attrs = second_latest.split(':')
            if "slurm_id" in second_latest_attrs[-1]:
                job_id = int(second_latest_attrs[-1][second_latest_attrs[-1].index('=')+1:])
                if second_latest_attrs[-3] == latest_attrs[-3]:
                    if 'Pass' in latest_attrs[-2] or 'Fail' in latest_attrs[-2]:
                        for job, slurm_id in self.job_pool.items():
                            if slurm_id == job_id:
                                self.job_pool.pop(job)
                                break
        dataset.status = latest
        self.start_datasets()

    def __call__(self, check_esgf=True):
        try:
            # find missing datasets
            self.setup_datasets(check_esgf)

            if self.report_missing:
                self.print_missing()
                return 0

            # start a workflow for each dataset as needed
            import ipdb; ipdb.set_trace()
            self.start_datasets()

            # wait around while jobs run
            while True:
                if should_exit:
                    sys.exit(0)
                sleep(10)

        except KeyboardInterrupt:
            self.listener.stop()
            exit(1)

        return 0
    
    def print_missing(self):
        # import ipdb; ipdb.set_trace()
        found_missing = False
        for x in self.datasets.values():
            if x.missing:
                found_missing = True
                for m in x.missing:
                    print(f"{m}")
            elif x.status == DatasetStatus.UNITITIALIZED.name:
                cprint(f"No files in dataset {x.dataset_id}", 'red')
        if not found_missing:
            cprint("No missing files in datasets", 'red')
            

    def setup_datasets(self, check_esgf=True):
        cprint("Initializing the warehouse", 'green')
        cmip6_ids = [x for x in self.collect_cmip_datasets()]
        if self.testing:
            cmip6_ids = cmip6_ids[:100]
        e3sm_ids = [x for x in self.collect_e3sm_datasets()]
        if self.testing:
            e3sm_ids = e3sm_ids[:100]
        dataset_ids = cmip6_ids + e3sm_ids
        
        # if the user gave us a wild card, filter out anything
        # that doesn't match their pattern
        if self.dataset_ids is not None:
            ndataset_ids = []
            for i in dataset_ids:
                found = False
                for ii in self.dataset_ids:
                    if ii in i:
                        found = True
                        break
                if found:
                    ndataset_ids.append(i)
            dataset_ids = ndataset_ids
        
        if not dataset_ids:
            cprint('No datasets match pattern from --dataset-id flag', 'red')
            sys.exit(1)
        # import ipdb; ipdb.set_trace()

        # instantiate the dataset objects with the paths to
        # where they should look for their data files
        self.datasets = {
            dataset_id: Dataset(
                dataset_id,
                pub_base=self.publication_path,
                warehouse_base=self.warehouse_path,
                archive_base=self.archive_path,
                sproket=self.sproket_path)
            for dataset_id in dataset_ids
        }

        # fill in the start and end year for each dataset
        for dataset_id, dataset in self.datasets.items():
            if dataset.project == 'CMIP6':
                start_year = self.dataset_spec['project']['CMIP6'][dataset.activity][
                    dataset.model_version][dataset.experiment]['start']
                end_year = self.dataset_spec['project']['CMIP6'][dataset.activity][
                    dataset.model_version][dataset.experiment]['end']
            else:
                start_year = self.dataset_spec['project']['E3SM'][dataset.model_version][dataset.experiment]['start']
                end_year = self.dataset_spec['project']['E3SM'][dataset.model_version][dataset.experiment]['end']

            dataset.start_year = start_year
            dataset.end_year = end_year

        # if the dataset is a time-series, find out what
        # its data variables are
        for dataset in self.datasets.values():
            if 'time-series' in dataset.data_type:
                facets = dataset.dataset_id.split('.')
                realm_vars = self.dataset_spec['time-series'][dataset.realm]
                exclude = self.dataset_spec['project']['E3SM'][facets[1]][facets[2]].get(
                    'except')
                if exclude:
                    dataset.datavars = [
                        x for x in realm_vars if x not in exclude]
                else:
                    dataset.datavars = realm_vars

        # find the state of each dataset
        if check_esgf:
            if not self.serial:
                pool = ProcessPoolExecutor(max_workers=self.num_workers)
                futures = [pool.submit(x.find_status)
                        for x in self.datasets.values()]
                for future in tqdm(as_completed(futures), total=len(futures), desc="Searching ESGF for datasets"):
                    dataset_id, status, missing = future.result()
                    if isinstance(status, DatasetStatus):
                        status = status.name
                    self.datasets[dataset_id].status = status
                    self.datasets[dataset_id].missing = missing
            else:
                for dataset in tqdm(self.datasets.values()):
                    # import ipdb; ipdb.set_trace()
                    dataset_id, status, _ = dataset.find_status()
                    if isinstance(status, DatasetStatus):
                        status = status.name
                    self.datasets[dataset_id].status = status

        return

    def filter_job_pool(self, jobs, datasets):
        # search all datasets to see if there's one that matches
        # the requirements for the job
        for job in self.job_pool:
            if not job.meets_requirements():
                for dataset in datasets.values():
                    if job.dataset.experiment == dataset.experiment \
                            and job.dataset.experiment == dataset.experiment \
                            and job.dataset.model_version == dataset.model_version \
                            and job.dataset.ensemble == dataset.ensemble \
                            and job.matches_requirement(dataset) \
                            and (dataset.status == DatasetStatus.SUCCESS.name or job.name in dataset.get_latest_status()):
                        job.setup_requisites(dataset)
        return

    def workflow_error(self, dataset):
        cprint(f"Dataset {dataset.dataset_id} FAILED from {dataset.status}", 'red')

    def workflow_success(self, dataset):
        cprint(f"Dataset {dataset.dataset_id} SUCCEEDED from {dataset.status}", 'cyan')

    def start_datasets(self):
        """
        Resolve next steps for datasets and create job objects for them
        Parameters: datasets dict of string dataset_ids to dataset objects
        Returns: list of new job objects
        """
        new_jobs = []
        for dataset_id, dataset in self.datasets.items():
            if dataset.status in [DatasetStatus.SUCCESS.name, DatasetStatus.FAILED.name]:
                continue
            if dataset.status not in [x.name for x in DatasetStatus]:
                if 'Ready' in dataset.status or 'Pass' in dataset.status or 'Fail' in dataset.status:
                    # we keep a reference to the workflow instance, so when
                    # we make a job we can reconstruct the parent workflow name
                    # for the status file
                    params = {}
                    if (parameters := dataset.status.split(':')[-1]):
                        for item in parameters.split(','):
                            key, value = item.split('=')
                            params[key] = value.replace('^', ':')

                    next_states = [(dataset.status, self.workflow, params)]
                    engaged_states = []
                    while next_states:

                        state, workflow, params = next_states.pop(0)
                        if dataset.is_blocked(state):
                            continue
                        if 'Engaged' in state:
                            engaged_states.append((state, workflow, params))
                            continue
                        elif "WAREHOUSE:Pass" in state:
                            self.workflow_success(dataset)
                            dataset.status = state
                            # import ipdb;ipdb.set_trace()
                            continue
                        elif "Exit:Fail" in state:
                            self.workflow_error(dataset)
                            dataset.status = state
                            continue
                        elif 'Fail' in state:
                            self.workflow_error(dataset)
                            new_state = self.workflow.next_state(dataset, state, params)
                            if new_state:
                                new_state, _, _ = new_state.pop()
                                dataset.update_status(new_state, params)
                            continue
                        elif 'Pass' in state:
                            self.workflow_success(dataset)
                            new_state = self.workflow.next_state(dataset, state, params)
                            if new_state:
                                new_state, _, _ = new_state.pop()
                                dataset.update_status(new_state, params)
                            continue

                        new_states = self.workflow.next_state(dataset, state, params)
                        if new_states is None:
                            continue
                        next_states.extend(new_states)
                    
                    if not engaged_states:
                        self.check_done()
                        return

                    for state, workflow, params in engaged_states:
                        newjob = self.workflow.get_job(
                            dataset,
                            state,
                            params,
                            self.scripts_path,
                            self.slurm_path,
                            workflow=workflow,
                            job_workers=self.job_workers)

                        if (matching_job := self.find_matching_job(newjob)) is None:
                            new_jobs.append(newjob)
                        else:
                            matching_job.setup_requisites(newjob.dataset)
        if new_jobs is not None:
            self.job_pool.update({
                x: None for x in new_jobs
            })
    
        # start the jobs in the job_pool if they're ready
        self.filter_job_pool(self.job_pool, self.datasets)

        for job in self.job_pool:
            if job.meets_requirements():
                if (job_id := job(self.slurm)) is not None:
                    self.job_pool[job] = job_id
                else:
                    cprint(f"Error starting up job {job}", 'red')

        self.check_done()
        return
    
    def check_done(self):
        all_done = True
        for dataset in self.datasets.values():
            if "WAREHOUSE:Pass" not in dataset.status:
                all_done = False
        if all_done:
            self.listener.observer.stop()
            self.should_exit = True
            sys.exit(0)
        return

    def find_matching_job(self, searchjob):
        for job in self.job_pool.keys():
            if job.name == searchjob.name \
                    and job.dataset.experiment == searchjob.dataset.experiment \
                    and job.dataset.model_version == searchjob.dataset.model_version \
                    and job.dataset.ensemble == searchjob.dataset.ensemble \
                    and not job.meets_requirements() and not searchjob.meets_requirements() \
                    and job.matches_requirement(searchjob.dataset) \
                    and searchjob.matches_requirement(job.dataset):
                return job
        return


    def collect_cmip_datasets(self, **kwargs):
        for activity_name, activity_val in self.dataset_spec['project']['CMIP6'].items():
            for version_name, version_value in activity_val.items():
                for experimentname, experimentvalue in version_value.items():
                    for ensemble in experimentvalue['ens']:
                        for table_name, table_value in self.dataset_spec['tables'].items():
                            for variable in table_value:
                                if variable in experimentvalue['except'] or table_name in experimentvalue['except']:
                                    continue
                                dataset_id = f"CMIP6.{activity_name}.E3SM-Project.{version_name}.{experimentname}.{ensemble}.{table_name}.{variable}.gr"
                                yield dataset_id

    def collect_e3sm_datasets(self, **kwargs):
        for version in self.dataset_spec['project']['E3SM']:
            for experiment, experimentinfo in self.dataset_spec['project']['E3SM'][version].items():
                for ensemble in experimentinfo['ens']:
                    for res in experimentinfo['resolution']:
                        for comp in experimentinfo['resolution'][res]:
                            for item in experimentinfo['resolution'][res][comp]:
                                for data_type in item['data_types']:
                                    if item.get('except') and data_type in item['except']:
                                        continue
                                    dataset_id = f"E3SM.{version}.{experiment}.{res}.{comp}.{item['grid']}.{data_type}.{ensemble}"
                                    yield dataset_id

    @staticmethod
    def add_args(parser,):
        p = parser.add_parser(
            name=NAME,
            help="Automated warehouse processing")
        p.add_argument(
            '-n', '--num',
            default=8,
            type=int,
            help="Number of parallel workers")
        p.add_argument(
            '-s', '--serial',
            action="store_true",
            help="Run everything in serial")
        p.add_argument(
            '-w', '--warehouse-path',
            default=DEFAULT_WAREHOUSE_PATH,
            help="The root path for pre-publication dataset staging")
        p.add_argument(
            '-p', '--publication-path',
            default=DEFAULT_PUBLICATION_PATH,
            help="The root path for data publication")
        p.add_argument(
            '-a', '--archive-path',
            default=DEFAULT_ARCHIVE_PATH,
            help="The root path for the data archive")
        p.add_argument(
            '-d', '--dataset-spec',
            default=DEFAULT_SPEC_PATH,
            help='The path to the dataset specification yaml file')
        p.add_argument(
            '--dataset-id',
            nargs='*',
            help='Only run the automated processing for the given datasets, this can the the complete dataset_id, '
                 'or a wildcard such as E3SM.1_0.')
        p.add_argument(
            '--job-workers',
            type=int,
            default=8,
            help='number of parallel workers each job should create when running')
        p.add_argument(
            '--testing',
            action="store_true",
            help='run the warehouse in testing mode')
        p.add_argument(
            '--sproket',
            required=False,
            default='sproket',
            help='path to sproket binary if its not in your $PATH')
        p.add_argument(
            '--slurm-path',
            required=False,
            default='slurm_scripts',
            help='The directory to hold slurm batch scripts as well as console output from batch jobs')
        p.add_argument(
            '--report-missing',
            required=False,
            action='store_true',
            help='After collecting the datasets, print out any that have missing files and exit')
        return NAME, parser

    @staticmethod
    def arg_checker(args):
        return True, NAME