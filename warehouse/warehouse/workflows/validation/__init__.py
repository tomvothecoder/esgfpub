from pathlib import Path
from warehouse.workflows import Workflow

NAME = 'Validation'
COMMAND = 'validate'


class Validation(Workflow):

    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)
        self.name = NAME.upper()

    def __call__(self):
        ...

    @staticmethod
    def add_args(parser):
        p = parser.add_parser(
            name=COMMAND,
            help='validate a raw dataset')
        p.add_argument(
            '-p', '--path',
            required=True,
            help="root path to the warehouse root directory")
        p.add_argument(
            '-d', '--dataset',
            required=True,
            help="the dataset_id to extract")
        return COMMAND, parser

    @staticmethod
    def arg_checker(args):
        if not Path(args.path).exists():
            print("The given path {args.path} does not exist")
            return False, COMMAND
        return True, COMMAND
