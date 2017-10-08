from __future__ import absolute_import, print_function, division
from ..commands import from_base
from ..log import logging
from ..invoke_libs import Attributes
import sys
import time
import shutil
import os
logger = logging.get_logger(__name__)


def bootstrap_add_subcommand(parser):
    '''
    Register bootstrap commands
    :param parser:argparse parser
    :return:
    '''
    subcommand = parser.add_parser('bootstrap')
    subcommand.add_argument(
        '--group',
        required=True,
        type=str,
        choices=[
            'jenkins',
            'acr',
            'acs',
            'storage',
            'monitor',
            'all'
        ],
        help="Which module to provision, use all to provision everything."
    )

    subcommand.add_argument(
        '--count',
        type=int,
        default='1',
        help="what is the count of agent nodes"
    )

    subcommand.add_argument('--verbose', required=False, action='count', default=True)
    return subcommand


def bootstrap_subcommand(args):
    """ Executes bootstrap command
    Based on a `group` argument passed to the command (see bootstrap_add_subcommand) provisions the specified group
    :param args: argparse parsed arguments
    :return:
    """
    try:
        kube_datacenters = ['dev', 'test', 'prod']
        all_datacenters = ['dev', 'test', 'prod', 'jenkins']
        groups = ['acr', 'acs', 'storage']
        if args.datacenter == "all" and args.group == "all":
           ### `all` provisions everything (acs,acr,storage) for all datacenter
            gitargs = Attributes(
                {'group': "git", "image": "azure-vote", "repo": "", "task": "all", "datacenter": "dev"})
            logger.info(
                "################### Configuring git repo for azure-vote app, resource: {} ###################".format(
                    gitargs.group))
            from_base.configure_git(gitargs)
            logger.info(
                "################### Completed configuring git repo for azure-vote app, resource: {} ###################".format(
                    gitargs.group))
            for dc in all_datacenters:
                if dc in kube_datacenters:
                    for group in groups:
                        args = Attributes({'group': group, "count": args.count, "datacenter": dc})
                        logger.info(
                            "################### Started Provisioning datacenter: {}, resource: {} ###################".format(
                                dc, args.group))
                        from_base.provision(args)
                        logger.info(
                            "################### Completed Provisioning datacenter: {}, resource: {} ###################".format(
                                dc, args.group))
                elif dc == "jenkins":
                    args = Attributes({'group': "jenkins", "count": args.count, "datacenter": dc})
                    logger.info(
                        "################### Provisioning datacenter: {}, resource: {} ###################".format(dc,
                                                                                                                   args.group))
                    from_base.provision(args)
                    logger.info(
                        "################### Completed Provisioning datacenter: {}, resource: {} ###################".format(
                            dc, args.group))

                    logger.info(
                        "################### Configuring Azure Monitor for: {}, resource: {} ###################".format(dc,
                                                                                                                         args.group))
                    args = Attributes({'group': "monitor", "datacenter": dc})
                    from_base.configure_monitor(args)
                    logger.info(
                        "################### Completed configuring Azure Monitor for: {}, resource: {} ###################".format(
                            dc, args.group))

                    logger.warn(
                        "################### We will be waiting for 5 mins for Jenkins machine to come up ###################")
                    time.sleep(300)
                    logger.info("################### Started pre-configuring jenkins ###################")
                    args = Attributes({'group': "pre-jenkins", "datacenter": dc})
                    from_base.configure_jenkins(args)
                    logger.info("################### Completed pre-configuring jenkins ###################")
                    logger.warn(
                        "################### Please configure jenkins in web ui by following the steps present in the document, on completion please type yes or no ###################")

                    try:
                        response = input("Have you configured jenkins ? Please type yes or no to continue:")
                    except SyntaxError:
                        pass

                    if response.lower() == "yes":
                        args = Attributes({'group': "jenkins", "datacenter": dc})
                        from_base.configure_jenkins(args)
                        logger.info("################### All steps completed ###################")
                    else:
                        logger.warn(
                            "################### Your response is {}, so jenkins configuration not proceeded. ###################".format(
                                response))
                        sys.exit(1)
        ### `all` provisions everything (acs,acr,storage) for only selected datacenter datacenter
        elif args.datacenter in kube_datacenters and args.group == "all":
            for group in groups:
                args = Attributes(
                    {'group': group, "count": args.count, "datacenter": args.datacenter})
                from_base.provision(args)
        ### provisions only selected resource from the group and for only selected datacenter datacenter
        elif args.datacenter in kube_datacenters and args.group in groups:
            from_base.provision(args)
        ### provisions only jenkins in jenkins datacenter
        elif args.datacenter == "jenkins" and args.group == "jenkins":
            from_base.provision(args)
        else:
            logger.warn(
                "Action on datacenter:{datacenter} and group:{group} is not valid".format(datacenter=args.datacenter,
                                                                                          group=args.group))

        shutil.rmtree(os.path.join(os.path.expanduser("~"), ".joara"), ignore_errors=True)
    except Exception as err:
        logger.error('ERROR: Bootstrap command got an Exception: {}'.format(err))
