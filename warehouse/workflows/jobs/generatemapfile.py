from warehouse.jobs import WorkflowJob

NAME = 'GenerateMapfile'

class GenerateMapfile(WorkflowJob):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cmd = ''
