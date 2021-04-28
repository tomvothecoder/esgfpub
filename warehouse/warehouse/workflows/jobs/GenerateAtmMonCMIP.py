from warehouse.workflows.jobs import WorkflowJob

NAME = 'GenerateAtmCMIP'

class GenerateAtmCMIP(WorkflowJob):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = NAME
        self._requires = { 'atmos-native-mon': None }
        self._cmd = ''
