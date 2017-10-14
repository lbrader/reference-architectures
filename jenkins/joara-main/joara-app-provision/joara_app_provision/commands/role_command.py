from __future__ import absolute_import, print_function, division
from ..commands import from_base
from ..invoke_libs import Attributes
import sys
from ..log import logging

logger = logging.get_logger(__name__)
def azure_add_subcommand(parser):
    """
    Registers azure role commands
    :param parser: argparse parser
    :return:
    """
    subcommand = parser.add_parser('azureconfigure')
    subcommand.add_argument(
        '--group',
        required=True,
        type=str,
        choices=[
            'azure-setup'
        ],
        help="Which module to configure. "
    )

    subcommand.add_argument(
        '--resourcegroup',
        required=True,
        nargs="?",
        type=str,
        help="What is the resource group"
    )

    subcommand.add_argument(
        '--useremail',
        required=True,
        nargs="?",
        type=str,
        help="What is the user email id"
    )
    subcommand.add_argument('--verbose', required=False, action='count', default=True)

    return subcommand


def azure_subcommand(args):
    ### Configures azure pre-setup
    from_base.configure_azure(args)



