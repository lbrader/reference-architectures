
from __future__ import absolute_import, print_function, division
from ..python_libs.context import Context
from ..python_libs.utils import find_app_main
import os
import shutil
from pathlib import Path
import yaml
from ..log import logging
import sys

logger = logging.get_logger(__name__)

def provision_images(module, images,  args):
    """
    List of actions on the image like build,push,deploy,patch,rollback etc.,
    :param module: which image to action
    :param images: List of images to be run
    :param args: command line arguments passed to the script
    :return:
    """
    try:
        app_main = find_app_main()
        run_file = os.path.join(app_main, module)
        context = Context(file=run_file, task=args.task,  datacenter=args.datacenter)
        for image in images:
            if args.task in ["build", "push", "deploy", "all"]:
                context.copy_sub_project(image)

            if args.task in ["deploy"]:
                backend = Path("backend.yml")
                if backend.is_file():
                    with open("backend.yml", 'r') as f:
                        backend = yaml.load(f)
                    attributes = {}
                    attributes.update(backend)
                    context.image_action(attributes, args)

            if args.task in ["build", "push", "deploy", "all"]:
                conf = Path("conf.yml")
                if conf.is_file():
                    with open("conf.yml", 'r') as f:
                        conf = yaml.load(f)
                    attributes = {
                        "count": args.count,
                        "image": image,
                        "name": conf['name'] if 'name' in conf else image,
                        "env": {}
                    }
                    attributes.update(conf)
                    context.image_action(attributes, args)

            if not args.task in ["build", "push", "deploy", "all"]:
                attributes = {
                    "count": args.count,
                    "image": image,
                    "name": image
                }
                context.image_action(attributes, args)
    except Exception as err:
        logger.error('ERROR: Provisioning images got an Exception: {}'.format(err))
        sys.exit(1)


def sync_version(run_file, args):
    """
    Executes a copy action for images from one datacenter to other datacenter and deploy's to Kube
    :param run_file:
    :param args: command line arguments passed to the script
    :return:
    """
    context = Context(file=run_file, task=args.task,  datacenter=args.datacenter)
    attributes ={
        "from_datacenter": args.source
    }
    context.sync_action(attributes,args)

def validate_dns(args):
    """
    Executes a DNS validation to check whether the DNS already exist
    :param args: command line arguments passed to the script
    :return:
    """
    app_main = find_app_main()
    module_path = os.path.join(app_main, 'infrastructure', 'provisioning',args.group,'run')
    context = Context(
        file=module_path,
        datacenter=args.datacenter,
        group=args.group
    )
    if context.validatedns():
        os.chdir(app_main)
        return True
    else:
        return False


def provision(args):
    """
    Executes a provisioning of resources like acs,acr,storage and jenkins
    :param args: command line arguments passed to the script
    :return:
    """
    app_main = find_app_main()
    module_path = os.path.join(app_main, 'infrastructure', 'provisioning',args.group,'run')

    if args.group == 'acs':
        attributes = {
            "agentcount": args.count
        }
    else:
        attributes = { }


    context = Context(
        file=module_path,
        datacenter=args.datacenter,
        group=args.group
    )
    context.copy_project()
    context.deploy(attributes)
    os.chdir(app_main)


def configure_jenkins(args):
    """
    Executes pre and post configure of jenkins
    :param args: command line arguments passed to the script
    :return:
    """
    try:
        app_main = find_app_main()
        if 'jenkins' in args.group:
            module_path = os.path.join(app_main, 'infrastructure', 'configure','jenkins','run')
        context = Context(
            file=module_path,
            datacenter=args.datacenter,
            group=args.group
        )
        try:
            files = ["id_rsa","id_rsa.pub"]
            for file in files:
                shutil.copyfile(os.path.join(os.path.expanduser("~"), ".ssh",file),os.path.join(app_main, 'infrastructure', 'configure','jenkins','ansible-jenkins','roles','jenkins','files','ssh',file))

            logger.info("Completed copying ssh keys for jenkins configuration")
        except Exception as err:
            logger.error("Error copying ssh keys for jenkins configuration at: {0}".format(err))
            sys.exit(1)

        context.copy_project()
        context.configure_jenkins()
        os.chdir(app_main)
    except Exception as err:
        logger.error('ERROR: Jenkins configure got an Exception: {}'.format(err))

def configure_monitor(args):
    """
    Executes configure azure monitor to jenkins
    :param args: command line arguments passed to the script
    :return:
    """
    app_main = find_app_main()
    module_path = os.path.join(app_main, 'infrastructure', 'configure','jenkins','run')
    context = Context(
        file=module_path,
        datacenter=args.datacenter,
        group=args.group
    )

    context.configure_alerting()

def configure_git(args):
    """
    Executes configuring repo in github adds new repo and settings
    :param args: command line arguments passed to the script
    :return:
    """
    app_main = find_app_main()
    if 'git' in args.group:
        module_path = os.path.join(app_main, 'infrastructure', 'images_repo',args.image,'run')
    context = Context(
        file=module_path,
        datacenter=args.datacenter,
        group=args.group
    )
    context.copy_project()
    context.configure_git(args)
    os.chdir(app_main)


def configure_azure(args):
    """
    Executes creation of azure service principle, role assignment and key vault. Works only with Owner and Administrator privilege users
    :param args: command line arguments passed to the script
    :return:
    """
    app_main = find_app_main()
    context = Context(
        file="",
        datacenter=args.datacenter,
        group=args.group,
        resourcegroup=args.resourcegroup,
        useremail=args.useremail
    )
    if context.validatedns():
        os.chdir(app_main)
        context.configure_azure()
    else:
        sys.exit(1)



def destroy(args):
    """
    Executes destroying of azure resource groups
    :param args: command line arguments passed to the script
    :return:
    """
    app_main = find_app_main()
    module_path = os.path.join(app_main, 'infrastructure', 'provisioning', args.group, 'run')
    context = Context(file=module_path, datacenter=args.datacenter,action=args.action)
    context.destroy()

