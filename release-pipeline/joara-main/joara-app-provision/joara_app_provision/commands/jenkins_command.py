from __future__ import absolute_import, print_function, division
from ..commands import from_base
from ..log import logging
import os
import shutil

logger = logging.get_logger(__name__)
def jenkins_add_subcommand(parser):
    """
    Registers jenkins command
    :param parser: argparse parser
    :return:
    """
    subcommand = parser.add_parser('jenkinsconfigure')
    subcommand.add_argument(
        '--group',
        required=True,
        type=str,
        choices=[
            'jenkins',
            'pre-jenkins',
            'monitor',
        ],
        help="Which module to configure. "
    )


    subcommand.add_argument('--verbose', required=False, action='count', default=True)

    return subcommand


def jenkins_subcommand(args):
    try:
        if 'jenkins' in args.group:
            ### Configures jenkins
            from_base.configure_jenkins(args)
        if 'monitor' in args.group:
            ### Adds monitor to jenkins VM
            from_base.configure_monitor(args)
        shutil.rmtree(os.path.join(os.path.expanduser("~"), ".joara"), ignore_errors=True)
    except Exception as err:
        logger.error('ERROR: Jenkins command got an Exception: {}'.format(err))

