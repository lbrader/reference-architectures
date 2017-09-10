from __future__ import absolute_import, print_function, division
from ..commands import from_base
from ..python_libs.utils import find_joara_app_main
import os


def sync_image_add_subcommand(parser):
    """Register sync subcommand

    :param parser: argparse parser
    """
    subcommand = parser.add_parser('syncimage')
    subcommand.add_argument(
        '--group',
        required=True,
        type=str,
        choices=[
            'image'
        ],
        help="Which action to perform, the operation are performed under images"
    )
    subcommand.add_argument(
        '--task',
        type=str,
        required=True,
        choices=[
            'copy'
        ],
        help="Which action to perform, use copy to copy images from one datacenter to another"

    )

    subcommand.add_argument(
        '--source',
        required=True,
        type=str,
        choices=[
            'test', 'dev'
        ]
    )

    subcommand.add_argument('--verbose', required=False, action='count', default=True)
    return subcommand


def sync_subcommand(args):
    """Execute sync subcommand

    Based on a `group` argument passed to the command (see sync_add_subcommand) executes the specified group

    :param args: argparse parsed arguments

    """

    joara_app_main = find_joara_app_main()
    run_file = os.path.join(joara_app_main, 'infrastructure', 'sync', 'run')
    from_base.sync_version(run_file, args)
