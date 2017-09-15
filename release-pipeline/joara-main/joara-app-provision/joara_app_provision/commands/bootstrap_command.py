from __future__ import absolute_import, print_function, division
from ..commands import from_base


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
    if args.group == "all":
        groups = ["acs","acr","storage"]
        for group in groups:
            args = Attributes(
                {'group': group, "count": args.count, "datacenter": args.datacenter})
            from_base.provision(args)
    else:
        from_base.provision(args)


class Attributes(object):
    def __init__(self, *initial_data, **kwargs):
        for dictionary in initial_data:
            for key in dictionary:
                setattr(self, key, dictionary[key])
        for key in kwargs:
            setattr(self, key, kwargs[key])