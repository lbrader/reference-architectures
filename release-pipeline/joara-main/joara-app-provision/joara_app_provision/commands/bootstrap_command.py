from __future__ import absolute_import, print_function, division
from ..commands import from_base
from ..log import logging
from ..invoke_libs import Attributes
import sys
import time

logger = logging.get_logger(__name__)


def bootstrap_add_subcommand(parser):
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
        help="Which module to provision, use all to provision everything. "
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
    kube_datacenters = ['dev', 'test', 'prod']
    all_datacenters = ['dev', 'test', 'prod', 'jenkins']
    groups = ['acr', 'acs', 'storage']
    if args.datacenter == "all" and args.group == "all":
        for dc in all_datacenters:
            args = Attributes(
                {'group': "all", "count": args.count, "datacenter": dc})
            if from_base.validate_dns(args):
                logger.info("Pre-validate condition passed: {} ... ".format(dc))
            else:
                logger.error("Pre-validate condition failed: {} ... ".format(dc))
                sys.exit(1)

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

    elif args.datacenter in kube_datacenters and args.group == "all":
        if from_base.validate_dns(args):
            logger.info("Pre-validate condition passed: {} ... ".format(args.datacenter))
        else:
            logger.error("Pre-validate condition failed: {} ... ".format(args.datacenter))
            sys.exit(1)

        for group in groups:
            args = Attributes(
                {'group': group, "count": args.count, "datacenter": args.datacenter})
            from_base.provision(args)
    elif args.datacenter in kube_datacenters and args.group in groups:
        if from_base.validate_dns(args):
            logger.info("Pre-validate condition passed: {} ... ".format(args.datacenter))
        else:
            logger.error("Pre-validate condition failed: {} ... ".format(args.datacenter))
            sys.exit(1)
        from_base.provision(args)
    elif args.datacenter == "jenkins" and args.group == "jenkins":
        if from_base.validate_dns(args):
            logger.info("Pre-validate condition passed: {} ... ".format(args.datacenter))
        else:
            logger.error("Pre-validate condition failed: {} ... ".format(args.datacenter))
            sys.exit(1)
        from_base.provision(args)
    else:
        logger.warn(
            "Action on datacenter:{datacenter} and group:{group} is not valid".format(datacenter=args.datacenter,
                                                                                      group=args.group))
