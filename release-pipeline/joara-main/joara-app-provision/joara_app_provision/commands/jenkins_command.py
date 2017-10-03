from __future__ import absolute_import, print_function, division
from ..commands import from_base
from ..log import logging

logger = logging.get_logger(__name__)
def jenkins_add_subcommand(parser):
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
    if 'jenkins' in args.group:
        from_base.configure_jenkins(args)
    if 'monitor' in args.group:
        from_base.configure_monitor(args)

