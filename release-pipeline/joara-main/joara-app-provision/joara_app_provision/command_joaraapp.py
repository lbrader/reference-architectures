#!/usr/bin/env python
from __future__ import absolute_import, print_function, division
from .commands.bootstrap_command import bootstrap_add_subcommand, bootstrap_subcommand
from .commands.sync_command import sync_image_add_subcommand, sync_subcommand
from .commands.jenkins_command import jenkins_add_subcommand, jenkins_subcommand
from .commands.image_command import image_add_subcommand, image_subcommand
from .commands.git_command import git_add_subcommand, git_subcommand
from .commands.destroy_command import destroy_add_subcommand, destroy_subcommand
import argparse
import sys
from .log.logging import configure_logging, get_logger
from .log import logging

def main():
    """Main entry point into the provisioning script
    """
    args = sys.argv[1:]
    logging_stream = None
    output = sys.stdout
    configure_logging(args, logging_stream)
    logger = get_logger(__name__)
    logger.debug('Command arguments %s', args)
    if args and (args[0] == '--version' or args[0] == '-v'):
       print("v1.0.0")
       sys.exit(1)


    parser = argparse.ArgumentParser(description="Run script to provision JOARA-APP")

    datacenters = ["jenkins","dev", "test", "prod"]
    parser.add_argument(
        "-d", "--datacenter",
        type=str,
        required=False,
        choices=datacenters,
        default="dev",
        help="Where to apply the run script"
    )


    subparsers = parser.add_subparsers(dest='cmd', help='')

    jenkins_add_subcommand(subparsers)
    git_add_subcommand(subparsers)
    bootstrap_add_subcommand(subparsers)
    sync_image_add_subcommand(subparsers)
    image_add_subcommand(subparsers)
    destroy_add_subcommand(subparsers)

    args = parser.parse_args()

    if args.datacenter is None:
        raise RuntimeError('Please specify datacenter ({})'.format(datacenters))


    elif args.cmd == 'bootstrap':
        bootstrap_subcommand(args)
    elif args.cmd == 'image':
        image_subcommand(args)
    elif args.cmd == 'destroy':
        destroy_subcommand(args)
    elif args.cmd == 'jenkinsconfigure':
        jenkins_subcommand(args)
    elif args.cmd == 'gitconfigure':
        git_subcommand(args)
    elif args.cmd == 'syncimage':
        sync_subcommand(args)
    else:
        raise RuntimeError('Unknown subcommand {}'.format(args.cmd))
