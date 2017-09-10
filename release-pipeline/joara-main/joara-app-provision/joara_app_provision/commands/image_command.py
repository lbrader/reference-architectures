from __future__ import absolute_import, print_function, division
from ..python_libs.utils import find_joara_app_main
from ..commands import from_base
import os
from ..log import logging
import platform
import sys
logger = logging.get_joara_logger(__name__)

def image_add_subcommand(parser):
    subcommand = parser.add_parser('image')

    subcommand.add_argument(
        '--task',
        type=str,
        required=True,
        choices=[
            'build',
            'push',
            'deploy',
            'scale',
            'patch',
            'delete',
            'get'
        ],
        help="Which action to be performed on the image "
    )

    subcommand.add_argument(
        '--images',
        required=True,
        nargs="+",
        type=str,
        help="Which images to provision "
    )

    subcommand.add_argument(
        '--count',
        type=int,
        nargs='?',
        default=1,
        help="How many replicas to scale")

    subcommand.add_argument(
        '--version',
        type=str,
        nargs='?',
        help="How many replicas to scale")

    subcommand.add_argument('--verbose', required=False, action='count', default=True)

    return subcommand


def image_subcommand(args):
    for image in args.images:
        module = os.path.join('infrastructure', 'images', 'run')
        if args.task in ["build", "push", "all"]:
            if platform.system() == 'Windows':
                logger.error("Image build,push option is not avaiable for windows OS")
                sys.exit(1)

        from_base.provision_images(module, [image], args)
