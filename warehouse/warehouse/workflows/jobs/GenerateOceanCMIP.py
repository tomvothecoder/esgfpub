import os
import yaml
from pathlib import Path
from tempfile import NamedTemporaryFile
from subprocess import Popen, PIPE
from warehouse.workflows.jobs import WorkflowJob

NAME = 'GenerateOceanCMIP'


class GenerateOceanCMIP(WorkflowJob):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = NAME
        self._requires = {
            'ocean-native-mon': None,
            'atmos-native-mon': None
        }
        self._cmd = ''

    def resolve_cmd(self):

        # step one, collect the information we're going to need for the CWL parameter file
        with open(self._spec_path, 'r') as i:
            spec = yaml.load(i, Loader=yaml.SafeLoader)

        raw_ocean_dataset = self.requires['ocean-native-mon']
        raw_atmos_dataset = self.requires['atmos-native-mon']
        cwl_config = self.config['cmip_ocn_mon']

        parameters = {
            'mpas_data_path': raw_ocean_dataset.latest_warehouse_dir,
            'atm_data_path': raw_atmos_dataset.latest_warehouse_dir
        }
        parameters.update(cwl_config)

        _, _, _, model_version, experiment, variant, table, cmip_var, _ = self.dataset.dataset_id.split(
            '.')

        # if we want to run all the variables
        # we can pull them from the dataset spec
        if cmip_var == 'all':
            is_all = True
            cmip_var = [x for x in spec['tables'][table] if x != 'all']
        else:
            is_all = False
            cmip_var = [cmip_var]

        # info_file = NamedTemporaryFile(delete=False)
        # cmd = f"e3sm_to_cmip --info -i {parameters['mpas_data_path']} --mode mpaso -v {', '.join(cmip_var)} -t {self.config['cmip_tables_path']} --info-out {info_file.name}"
        # proc = Popen(cmd.split(), stdout=PIPE, stderr=PIPE)
        # _, err = proc.communicate()
        # if err:
        #     print(err)
        #     return None
        # with open(info_file.name, 'r') as instream:
        #     variable_info = yaml.load(instream, Loader=yaml.SafeLoader)

        # for item in variable_info:
        #     if ',' in item['E3SM Variables']:
        #         e3sm_var = [v.strip() for v in item['E3SM Variables'].split(',')]
        #     else:
        #         e3sm_var = [item['E3SM Variables']]

        parameters['std_var_list'] = ['PSL']
        parameters['mpas_var_list'] = cmip_var
        cwl_workflow = "mpaso-atm/mpaso-atm.cwl"

        parameters['tables_path'] = self.config['cmip_tables_path']
        parameters['metadata_path'] = {
            'class': 'File',
            'path': os.path.join(
                self.config['cmip_metadata_path'], 
                model_version, 
                f"{experiment}_{variant}.json")
            }
        parameters['hrz_atm_map_path'] = self.config['grids']['ne30_to_180x360']
        parameters['mpas_map_path'] = self.config['grids']['oEC60to30_to_180x360']

        raw_case_spec = spec['project']['E3SM'][raw_ocean_dataset.model_version][raw_ocean_dataset.experiment]
        parameters['mpas_namelist_path'] = raw_case_spec['mpaso_namelist']
        parameters['mpas_restart_path'] = raw_case_spec['mpas_restart']
        parameters['workflow_output'] = str(self.dataset.warehouse_path)

        # step two, write out the parameter file and setup the temp directory
        var_id = 'all' if is_all else cmip_var[0]
        parameter_path = os.path.join(
            self._slurm_out, f"{self.dataset.experiment}-{self.dataset.model_version}-{self.dataset.ensemble}-ocn-cmip-mon-{var_id}.yaml")
        with open(parameter_path, 'w') as outstream:
            yaml.dump(parameters, outstream)

        tmp_path = Path(self._slurm_out, 'tmp')
        if not tmp_path.exists():
            tmp_path.mkdir()

        # step three, render out the CWL run command
        if not self.serial:
            parallel = "--parallel"
        else:
            parallel = ''
        self._cmd = f"cwltool --tmpdir-prefix={tmp_path} {parallel} --preserve-environment UDUNITS2_XML_PATH {os.path.join(self.config['cwl_workflows_path'], cwl_workflow)} {parameter_path}"
