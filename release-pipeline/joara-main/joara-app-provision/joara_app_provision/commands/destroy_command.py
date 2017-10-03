from __future__ import absolute_import, print_function, division
from ..python_libs.context import Context
from ..python_libs.utils import find_app_main
from ..commands import from_base
import os
from ..log import logging
from ..invoke_libs import Attributes
import sys
import time

logger = logging.get_logger(__name__)


def destroy_add_subcommand(parser):
    subcommand = parser.add_parser('destroy')

    subcommand.add_argument(
        '--group',
        required=True,
        type=str,
        choices=[
            'all',
            'jenkins',
            'acr',
            'acs',
            'monitor'
        ],
        help="Which module to destrory"
    )
    subcommand.add_argument(
        '--action',
        type=str,
        choices=[
            'destroy'
        ],
        nargs='?',
        default='destroy',
        help="Which action to be performed by arm"
    )
    subcommand.add_argument('--verbose', required=False, action='count', default=True)
    return subcommand


def destroy_subcommand(args):
    all_datacenters = ['dev', 'test', 'prod', 'jenkins']
    if args.datacenter == "all" and args.group == "all":
        for dc in all_datacenters:
            args = Attributes({'group': "all", "action": 'destroy', "datacenter": dc})
            logger.info("################### Destroying datacenter {}, resource: {} started ###################".format(dc,args.group))
            from_base.destroy(args)
            logger.info("################### Destroying datacenter {}, resource: {} completed ###################".format(dc, args.group))
    else:
        from_base.destroy(args)
