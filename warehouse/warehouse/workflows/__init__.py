
import yaml
import importlib
import os
import sys
import inspect
from pprint import pformat
from pathlib import Path

from warehouse.workflows import jobs
import warehouse.resources as resources
from warehouse.workflows import jobs
from warehouse.util import setup_logging, log_message


resource_path, _ = os.path.split(resources.__file__)
DEFAULT_SPEC_PATH = os.path.join(resource_path, 'dataset_spec.yaml')
DEFAULT_CONF_PATH = os.path.join(resource_path, 'warehouse_config.yaml')

with open(DEFAULT_CONF_PATH, 'r') as instream:
    warehouse_conf = yaml.load(instream, Loader=yaml.SafeLoader)
DEFAULT_WAREHOUSE_PATH = warehouse_conf['DEFAULT_WAREHOUSE_PATH']
DEFAULT_PUBLICATION_PATH = warehouse_conf['DEFAULT_PUBLICATION_PATH']
DEFAULT_ARCHIVE_PATH = warehouse_conf['DEFAULT_ARCHIVE_PATH']
DEFAULT_STATUS_PATH = warehouse_conf['DEFAULT_STATUS_PATH']

NAME = 'Warehouse'


class Workflow(object):

    def __init__(self, parent=None, slurm_scripts='temp', **kwargs):
        self.parent = parent
        self.transitions = {}
        self.children = {}
        self.slurm_scripts = slurm_scripts
        self.name = NAME.upper()
        self.jobs = self.load_jobs()
        self.params = kwargs
        self.job_workers = kwargs.get('job_workers')
        self.debug = kwargs.get('debug')
        setup_logging('info', 'Warehouse.log')

    def load_jobs(self):
        """
        get the path to the jobs directory which should be a sibling
        of the warehouse.py file
        """
        modules = {}
        jobs_path = Path(jobs.__file__).parent.absolute()

        for file in jobs_path.glob('*'):
            if file.name == '__init__.py' or file.is_dir():
                continue
            module_string = f'warehouse.workflows.jobs.{file.stem}'
            module = importlib.import_module(module_string)
            job_class = getattr(module, module.NAME)
            modules[module.NAME] = job_class
        return modules

    def get_status_prefix(self, prefix=""):
        """
        From any node in the workflow tree, get the correct status message prefix
        """
        if self.parent != None:
            prefix = f'{self.name}:{prefix}'
            return self.parent.get_status_prefix(prefix)
        else:
            # return prefix
            return self.name + ':' + prefix

    def next_state(self, dataset, state, params, idx=0):
        """
        Parameters: 
            dataset (Dataset) : The dataset which is changing state
            state (string) : The state to move out from (trimmed to "test_state" below)
            idx (int) : The recursive depth index
        Returns the name of the next state to transition to given the current state of the dataset
        """
        log_message("info", " ----- entered next_state() ----- ")
        log_message("info", f"WF_init next_state: self.name = {self.name} for dataset {dataset.dataset_id}")
        log_message("debug", f"WF_init next_state: current state = {state}")
        # import ipdb; ipdb.set_trace()
        self.print_debug(f"next_state: current = *{state}*")
        state_attrs = state.split(':')
        if len(state_attrs) < 3:
            test_state = state
        else:
            test_state = f"{state_attrs[-3]}:{state_attrs[-2]}"       # OMG this is brittle.

        # test_state = test_state.upper()
        state_attrs_curr = state_attrs[idx].upper()

        prefix = self.get_status_prefix()
        log_message("info", f"WF_init next_state: status_prefix = {prefix}")
        log_message("info", f"WF_init next_state: state_attrs = {state_attrs}")
        log_message("info", f"WF_init next_state: curr test_state = {test_state}")
        log_message("debug", f"WF_init next_state: self.transitions.keys = {self.transitions.keys()}")
        log_message("debug", f"WF_init next_state: self.children.keys = {self.children.keys()}")

        if test_state in self.transitions.keys():
            log_message("info", f"WF_init next_state: test_state {test_state} FOUND in self.transition.keys: leads to {self.transitions[test_state]}")
            if dataset.grid == "native":
                target_data_type = f'{dataset.realm}-native-{dataset.freq}'
            else:
                target_data_type = f'{dataset.realm}-{dataset.data_type.replace("-", "")}-{dataset.freq}'

            log_message("info", f"WF_init next_state: target_data_type = {target_data_type}")
            self.print_debug(f"target_data_type: {target_data_type}")
            transitions = self.transitions[test_state].get(target_data_type)
            log_message("info", f"WF_init next_state: transitions = {transitions}")
            if transitions is None:
                try:
                    return [(f'{prefix}{x}:', self, params) for x in self.transitions[test_state]['default']]
                except KeyError as e:
                    log_message('error', f"Dataset {dataset.dataset_id} tried to go to the 'default' transition from the {test_state}, but no default was found")
                    sys.exit(1)
            else:
                ret_list = [(f'{prefix}{x}:', self, params) for x in transitions]
                log_message("info", f"WF_init next_state: for {dataset.dataset_id} returning {ret_list}")
                return ret_list

        elif state_attrs_curr == "WAREHOUSE":
            return self.next_state(dataset, state, params, idx + 1)     # jump over "WAREHOUSE" state component, try again

        # import ipdb; ipdb.set_trace()
        elif state_attrs_curr in self.children.keys():
            log_message("info", f"WF_init next_state: state_attrs_curr {state_attrs_curr} FOUND in self.children.keys: leads to {self.children[state_attrs_curr]}")
            return self.children[state_attrs_curr].next_state(dataset, state, params, idx + 1)  # recurse

        else:
            log_message("error", f"WF_init next_state: target state {test_state} is not present in the transition graph for {self.name}")
            log_message("error", f"WF_init next_state: (info) idx={idx}, state_attrs_curr = {state_attrs_curr}")
            log_message("error", f"WF_init next_state: (info) child_keys: {self.children.keys()}")

            # import ipdb; ipdb.set_trace()
            sys.exit(1)

    def get_job(self, dataset, state, params, scripts_path, slurm_out_path, workflow, job_workers=8, **kwargs):
        state_attrs = state.split(':')
        job_name = state_attrs[-3]

        if job_name == state_attrs[1]:
            parent = state_attrs[0]
        else:
            parent = f"{state_attrs[0]}:{state_attrs[1]}"

        self.print_debug(f"initializing job {job_name} for {dataset.dataset_id} from state {state}:{params}")

        job = self.jobs[job_name]
        job_instance = job(
            dataset,
            state,
            scripts_path,
            slurm_out_path,
            params=params,
            slurm_opts=kwargs.get('slurm_opts', []),
            parent=parent,
            job_workers=self.job_workers,
            spec=kwargs.get('spec'),
            config=kwargs.get('config'),
            debug=kwargs.get('debug'),
            serial=kwargs.get('serial', True),
            tmpdir=kwargs.get('tmpdir', os.environ.get('TMPDIR', '/tmp')))

        other_datasets = [x for x in kwargs.get('other_datasets') if x.dataset_id != dataset.dataset_id]
        job_instance.setup_requisites(other_datasets)
        try:
            job_reqs = {k:v.dataset_id for k,v in job_instance.requires.items() if v is not None}
        except AttributeError as error:
            log_message('error', f"Job instance {job_instance} unable to find its requirements {job_instance.requires.items()}, is there a missing dataset?")
            return job_instance

        if not job_instance.meets_requirements() and job_instance.dataset.project != 'CMIP6' and 'time-series' not in job_instance.dataset.dataset_id and 'climo' not in job_instance.dataset.dataset_id:
            log_message('error', f"Job {job_instance} has unsatisfiable requirements {job_reqs}")
            
        return job_instance

    def load_transitions(self):
        transition_path = Path(Path(inspect.getfile(
            self.__class__)).parents[0], 'transitions.yaml')
        with open(transition_path, 'r') as instream:
            self.transitions = yaml.load(instream, Loader=yaml.SafeLoader)
            log_message("info", f"WF_init: {self.name} loads transitions")
            log_message("debug", f"WF_init: {self.name} loads transitions {self.transitions}")

    def load_children(self):
        my_path = Path(inspect.getfile(self.__class__)).parent.absolute()
        workflows = {}
        for d in os.scandir(my_path):
            if not d.is_dir() or d.name == "jobs" or d.name == "__pycache__":
                continue

            module_path = Path(my_path, d.name, '__init__.py')
            if not module_path.exists():
                log_message('error', f"{module_path} doesnt exist, doesnt look like this is a well formatted workflow")
                sys.exit(1)

            workflows_string = f"warehouse{os.sep}workflows"
            idx = str(my_path.resolve()).find(workflows_string)
            if self.name == NAME:
                module_name = f'warehouse.workflows.{d.name}'
            else:
                module_name = f'warehouse.workflows{str(my_path)[idx+len(workflows_string):].replace(os.sep, ".")}.{d.name}'

            self.print_debug(f"loading workflow module {module_name}")

            module = importlib.import_module(module_name)
            workflow_class = getattr(module, module.NAME)
            workflow_instance = workflow_class(
                parent=self,
                slurm_scripts=self.slurm_scripts)
            workflow_instance.load_children()
            workflow_instance.load_transitions()
            workflows[module.NAME.upper()] = workflow_instance
        self.children = workflows

    def toString(self):
        info = {}
        if self.parent == None:
            for name, instance in self.children.items():
                info[name] = instance.toString()
            return pformat(info, indent=4)
        else:
            if self.children:
                for name, instance in self.children.items():
                    info[name] = instance.toString()
                return info
            else:
                return self.transitions

    def print_debug(self, msg):
        if self.debug:
            log_message('debug', msg)

    @staticmethod
    def add_args(parser):
        parser.add_argument(
            '-d', '--dataset-id',
            nargs="*",
            help="Dataset IDs that should have the workflow applied to them. If this is "
                 "given without the data-path, the default warehouse value will be used."
                 "If its an E3SM dataset, the ID should be in the form 'E3SM.model_version.experiment.(atm_res)_atm_(ocn_res)_ocean.realm.grid.data-type.freq.ensemble-number' "
                 "\t\t for example: 'E3SM.1_3.G-IAF-DIB-ISMF-3dGM.1deg_atm_60-30km_ocean.ocean.native.model-output.mon.ens1' "
                 "If its a CMIP6 dataset, the ID should be in the format 'CMIP6.activity.source.model-version.case.variant.table.variable.grid-name'  "
                 "\t\t for example: 'CMIP6.CMIP.E3SM-Project.E3SM-1-1.historical.r1i1p1f1.CFmon.cllcalipso.gr' ")
        parser.add_argument(
            '--data-path',
            help="Path to a directory containing a single dataset that should have "
                 "the workflow applied to them. If given, also use the --dataset-id flag "
                 "to specify the dataset-id that should be applied to the data\n")
        parser.add_argument(
            '--job-workers',
            type=int,
            default=8,
            help='number of parallel workers each job should create when running, default is 8')
        parser.add_argument(
            '-w', '--warehouse-path',
            default=DEFAULT_WAREHOUSE_PATH,
            help=f"The root path for pre-publication dataset staging, default={DEFAULT_WAREHOUSE_PATH}")
        parser.add_argument(
            '-p', '--publication-path',
            default=DEFAULT_PUBLICATION_PATH,
            help=f"The root path for data publication, default={DEFAULT_PUBLICATION_PATH}")
        parser.add_argument(
            '-a', '--archive-path',
            default=DEFAULT_ARCHIVE_PATH,
            help=f"The root path for the data archive, default={DEFAULT_ARCHIVE_PATH}")
        parser.add_argument(
            '--status-path',
            default=DEFAULT_STATUS_PATH,
            help=f'The path to where to store dataset status files, default={DEFAULT_STATUS_PATH}')
        parser.add_argument(
            '--debug',
            action='store_true',
            help='Print additional debug information to the console')
        parser.add_argument(
            '--testing',
            action='store_true',
            help='run in testing mode')
        return parser

    @staticmethod
    def arg_checker(args, command=NAME):
        if args.data_path and not args.dataset_id:
            log_message('error', "\nIf the data_path is given, please also give a dataset ID for the data at the path\n")
            return False, command
        if not args.dataset_id and not args.data_path:
            log_message('error', "\nError: please specify either the dataset-ids to process, or the data-path to find datasets\n")
            return False, command
        if isinstance(args.dataset_id, list) and len(args.dataset_id) > 1 and args.data_path:
            log_message('error', "\nMultiple datasets were given along with the --data-path. For multiple datasets you must use the --warehouse-path and the E3SM publication directory structure")
            return False, command
        return True, command
