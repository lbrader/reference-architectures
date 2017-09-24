from __future__ import absolute_import, print_function, division
from ..commands import from_base
from ..log import logging
from ..invoke_libs import Attributes
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
            'vm',
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

    kube_datacenters = ['dev','test','prod']
    groups = ['acr', 'acs', 'storage']
    if args.datacenter in kube_datacenters and  args.group == "all":
        groups = ["acs","acr","storage"]
        for group in groups:
            args = Attributes(
                {'group': group, "count": args.count, "datacenter": args.datacenter})
            from_base.provision(args)
    elif args.datacenter in kube_datacenters and args.group in groups:
        from_base.provision(args)
    elif args.datacenter == "jenkins" and args.group == "jenkins":
        from_base.provision(args)
    else:
        logger.warn("Action on datacenter:{datacenter} and group:{group} is not valid".format(datacenter=args.datacenter,group=args.group))


