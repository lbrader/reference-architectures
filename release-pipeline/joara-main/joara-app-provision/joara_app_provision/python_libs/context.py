from __future__ import absolute_import, print_function, division
from functools import wraps
from time import sleep
from ..env import get_cluster_config
from subprocess import check_call, getoutput
import os
import sys
import subprocess
from azure.common.credentials import ServicePrincipalCredentials
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.resource.resources.models import DeploymentMode
from msrestazure.azure_exceptions import CloudError
from ..invoke_libs import render
import json
from . import remote
import zipfile
from ..log import logging
from ..invoke_libs.kube import KubeApi
import yaml
from ..invoke_libs.image import Image
from ..invoke_libs.sync.copy_docker import CopyDocker
from ..invoke_libs.validators import validate_ssh_key
import tempfile
import shutil


class Context(object):
    def __init__(self, **kwargs):
        self.__dict__ = kwargs
        self.logger = logging.get_joara_logger(self.__class__.__name__)
        self.file = os.path.abspath(self.file)
        self.script = os.path.basename(self.file)
        self.cluster_config = get_cluster_config(self.datacenter)
        self.__dict__.update({
            'project_name': self.file.split(os.sep)[-2],
            'project_path': os.path.dirname(self.file),
            'joara_app_datacenter': self.datacenter,
            'joara_app_main': kwargs.get('joara_app_main', self.cluster_config['JOARA_APP_MAIN']),
            'joara_app_latest': self.cluster_config['JOARA_APP_LATEST'],
            'vault_password': self.cluster_config['VAULT_PASSWORD'],
            'users_path_exists': False,
            'joara_app_docker_registry': self.cluster_config['JOARA_APP_DOCKER_REGISTRY'],
            "datacenter": self.datacenter
        })

        try:
            if ('AZURE_CLIENT_ID' in os.environ and 'AZURE_CLIENT_SECRET' in os.environ and 'AZURE_TENANT_ID' in os.environ and 'AZURE_SUBSCRIPTION_ID' in os.environ):
                self.__dict__.update({
                    'subscription_id': os.environ['AZURE_SUBSCRIPTION_ID'],
                    'client_id': os.environ['AZURE_CLIENT_ID'],
                    'client_secret': os.environ['AZURE_CLIENT_SECRET'],
                    'tenant_id': os.environ['AZURE_TENANT_ID']})
            else:
                self.__dict__.update({
                    'subscription_id': self.cluster_config['AZURE_SUBSCRIPTION_ID'],
                    'client_id': self.cluster_config['AZURE_CLIENT_ID'],
                    'client_secret': self.cluster_config['AZURE_CLIENT_SECRET'],
                    'tenant_id': self.cluster_config['AZURE_TENANT_ID']})

                os.environ['AZURE_CLIENT_ID'] = self.client_id
                os.environ['AZURE_CLIENT_SECRET'] = self.client_secret
                os.environ['AZURE_TENANT_ID'] = self.tenant_id
                os.environ['AZURE_SUBSCRIPTION_ID'] = self.subscription_id
        except Exception as e:
            logs = " Please update your azure credentials under culsters.ini or to environment variables , {}".format(e)
            self.logger.error(logs)
            raise RuntimeError(logs)

        if 'SSH_KEY_FILE' in self.cluster_config:
            self.__dict__.update({
                'ssh_key_file': "{}{}".format(self.joara_app_main, self.cluster_config['SSH_KEY_FILE'])})
        else:
            self.__dict__.update({
                'ssh_key_file': ""})

        self.__dict__.update({
            'resource_group_prefix': self.cluster_config['RESOURCE_GROUP_PREFIX'],
            'location': self.cluster_config['LOCATION'],
            'user': self.cluster_config['USER']})

        os.environ['JOARA_APP_LATEST'] = self.cluster_config['JOARA_APP_LATEST']
        os.environ['JOARA_RESOURCE_GROUP_PREFIX'] = self.resource_group_prefix

        self.logger.info("joara_app_datacenter: {0.joara_app_datacenter} ".format(self))
        self.resource_group = "{}-{}".format(self.resource_group_prefix, self.datacenter)

        validate_ssh_key(self.ssh_key_file)
        self.credentials = ServicePrincipalCredentials(
            client_id=self.client_id,
            secret=self.client_secret,
            tenant=self.tenant_id
        )

        self.regionmap = {
            "us-west": "westus",
            "us-southcentral": "southcentralus",
            "us-east": "eastus"
        }

        self.client = ResourceManagementClient(self.credentials, self.subscription_id)

        if os.path.exists('/Users'):
            self.users_path_exists = True
        self._app_project_path()

    def __str__(self):
        result = ''
        newline = ''
        for key in self.__dict__:
            result = '{}{}{}: {}'.format(
                result, newline, key, self.__dict__[key])
            newline = '\n'
        return result

    def cd_and_run(self, directory, run_args):
        self.cd(directory)
        self.run('./run --datacenter ' + self.datacenter + ' ' + run_args)

    def cd(self, directory, fg='green'):
        while True:
            prev = directory
            directory = directory.format(self)
            if prev == directory:
                break
        self.logger.debug('cd {}'.format(directory))
        os.chdir(directory)

    def getoutput(self, cmd, log=True):
        while True:
            prev = cmd
            cmd = cmd.format(self)
            if prev == cmd:
                break

        if log:
            self.logger.debug(cmd)
        getoutput(cmd)

    def run(self, cmd, log=True):
        while True:
            prev = cmd
            cmd = cmd.format(self)
            if prev == cmd:
                break

        if log:
            self.logger.debug(cmd)
        check_call(cmd, shell=True)

    def configure(self):
        try:
            if self.group == "jenkins":
                self.sshclient = remote.sshclient("joara-release-jenkins.{location}.cloudapp.azure.com".format(
                    location=self.regionmap[self.location]), "joarajenkins")

                self.sshclient.zip(
                    os.path.join(self.joara_app_main, "infrastructure", "configure", "jenkins", "ansible-jenkins"),
                    "ansible-jenkins")

                self.sshclient.sendCommand("sudo rm -rf /tmp/*")
                self.sshclient.sendCommand("ls -la /tmp/")
                self.sshclient.copyFile("ansible-jenkins.zip")
                self.sshclient.copyFile(
                    os.path.join(self.joara_app_main, "infrastructure", "configure", "jenkins", "configure.sh"))
                self.sshclient.sendCommand("ls -la /tmp/")
                # self.sshclient.sendCommand("eval \"$(ps aux | grep -ie configure.sh  | awk '{print \"kill -9 \" $2}')\"")
                self.logger.info("Started configuring jenkins ")
                log_output = self.sshclient.sendCommand("chmod +x /tmp/configure.sh ; cd /tmp/ ; ./configure.sh ")

                if "Completed Configure Jenkins" in log_output:
                    self.logger.info("Completed configuring jenkins ")
                else:
                    self.logger.exception("Error in jenkins configuration,Please refer logs")
                    sys.exit(1)

                os.remove("ansible-jenkins.zip")


            if self.group == "pre-jenkins":
                self.sshclient = remote.sshclient("joara-release-jenkins.{location}.cloudapp.azure.com".format(
                    location=self.regionmap[self.location]), "joarajenkins")
                self.logger.info("Getting Jenkins admin credentials ")
                self.sshclient.sendCommand("sudo cat /var/lib/jenkins/secrets/initialAdminPassword")
                self.logger.info("Please use the above credentials for configuring jenkins ")
        except Exception as err:
            self.logger.error("Exception: {0}".format(err))
            sys.exit(1)

    def deploy(self, config_dict):
        """Deploy the template to a resource group."""

        # Dict that maps keys of CloudCenter's region names to values of Azure's region names.
        # Used below to control where something is deployed
        self.logger.info("Starting the deployment: {0.joara_app_datacenter} ... ".format(self))

        try:
            self.client.resource_groups.create_or_update(
                self.resource_group,
                {
                    'location': self.regionmap[self.location]
                }
            )
        except CloudError as err:
            self.logger.error("CloudError: {0}".format(err))
            sys.exit(1)
        except Exception as err:
            self.logger.error("Exception: {0}".format(err))
            sys.exit(1)

        try:
            template_path = os.path.join(self.app_project_path, 'templates', 'template.json')
            with open(template_path, 'r') as template_file_fd:
                template = json.load(template_file_fd)
        except Exception as err:
            self.logger.error("Error loading the ARM Template: {0}. Check your syntax".format(err))
            sys.exit(1)

        try:
            parameters_path = os.path.join(self.app_project_path, 'templates', 'parameters.json')
            with open(parameters_path, 'r') as armparams_file_fd:
                parameters = armparams_file_fd.read()
        except Exception as err:
            self.logger.error("Error loading the ARM Parameters File: {0}. Check your syntax".format(err))
            sys.exit(1)

        attributes = {
            "datacenter": self.datacenter,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }

        if 'sshkey' in str(parameters):
            pub_ssh_key_path = os.path.expanduser('{user}/.ssh/id_rsa.pub'.format(user=os.path.expanduser("~")))
            with open(pub_ssh_key_path, 'r') as pub_ssh_file_fd:
                sshkey = pub_ssh_file_fd.read()
                attributes.update({
                    "sshkey": sshkey.strip()})

        attributes.update(config_dict)
        parameters = render(str(parameters), attributes)
        parameters = json.loads(str(parameters).replace("'", '"').replace("False", "false"))

        parameters = parameters['parameters']
        deployment_properties = {
            'mode': DeploymentMode.incremental,
            'template': template,
            'parameters': parameters
        }
        try:
            deployment_async_operation = self.client.deployments.create_or_update(
                self.resource_group,
                'joara-resource',
                deployment_properties
            )

            result = deployment_async_operation.result()
            msg = "Deployment completed. Outputs:"
            for k, v in result.properties.outputs.items():
                msg += f"\n- {k} = {str(v['value'])}"
            self.logger.info(msg)
        except CloudError as err:
            self.logger.error("CloudError: {0}".format(err))
            sys.exit(1)
        except Exception as err:
            self.logger.error("Exception: {0}".format(err))
            sys.exit(1)

        self.logger.info("Completed the deployment: {0.joara_app_datacenter} ... ".format(self))

    def destroy(self):
        """Destroy the given resource group"""
        self.logger.info("Deleting resource group: {0.joara_app_datacenter} ... ".format(self))
        try:
            self.client.resource_groups.delete(self.resource_group)
        except CloudError as err:
            self.logger.error("CloudError: {0}".format(err))
            sys.exit(1)
        except Exception as err:
            self.logger.error("Exception: {0}".format(err))
            sys.exit(1)

        self.logger.info("Completed deleting: {0.joara_app_datacenter} ... ".format(self))

    def sync_action(self, config_dict, args):
        attrs = {}
        cluster_config = get_cluster_config(self.datacenter)
        attrs['cluster_config'] = cluster_config
        attrs.update(config_dict)
        copy = CopyDocker(datancenter=self.datacenter, **attrs)
        if args.task == "copy":
            copy.copy()

    def image_action(self, config_dict, args):
        attrs = {}
        with open("conf.yml", 'r') as f:
            conf = yaml.load(f)
        attrs.update(conf)
        attrs['flatten'] = False
        attrs['move'] = True
        attrs['task'] = args.task
        cluster_config = get_cluster_config(self.datacenter)
        attrs['cluster_config'] = cluster_config
        attrs.update(config_dict)

        if args.task in ["deploy", "scale", "patch", "get", "delete", "push"]:
            kube = KubeApi(datacenter=self.datacenter, **attrs)
        if args.task in ["build", "push", "all"]:
            image = Image(**attrs)

        if args.task == "deploy":
            kube.deploy()
        elif args.task == "scale":
            kube.scale()
        elif args.task == "patch":
            kube.patch()
        elif args.task == "get":
            kube.get()
        elif args.task == "delete":
            kube.delete()
        elif args.task == "build":
            image.build()
        elif args.task == "push":
            image.push()
        elif args.task == "all":
            image.build()
            image.push()
            kube.deploy()
        else:
            self.logger.error("No task exist")

    # def _app_project_path(self):
    #     xs = self.project_path.split(os.sep)
    #     self.app_project_path = ''
    #     include = False
    #     for x in xs:
    #         if include:
    #             self.app_project_path = '{}/{}'.format(
    #                 self.app_project_path, x)
    #         if x == 'joara-main':
    #             include = True
    #     self.app_project_path = '{}{}'.format(
    #         self.joara_app_main, self.app_project_path)

    def _app_project_path(self):
        xs = self.project_path.split(os.sep)
        self.app_project_path = ''
        include = False
        for x in xs:
            if include:
                self.app_project_path = '{}/{}'.format(
                    self.app_project_path, x)
            if 'joara-main' in x:
                include = True

        if self.app_project_path == '' and 'infrastructure' in xs:
            self.app_project_path = os.sep.join(xs[xs.index('infrastructure'):])
        else:
            self.app_project_path = self.app_project_path.lstrip(os.path.sep)

        self.logger.info("project path: {}".format(self.app_project_path))
        self.app_project_path = os.path.join(self.joara_app_main, self.app_project_path)
        self.logger.info("Absolute project path: {} ".format(self.app_project_path))

    def cd_project(self):
        self.cd(self.app_project_path)


    def get_temp_dir(self):
        temp_dir = os.path.join(tempfile.gettempdir())
        return temp_dir

    def copy_sub_project(self, sub_project):
        self.cd(os.path.join(self.app_project_path, sub_project))
        temp_dir = self.get_temp_dir()
        self.logger.info("project path:{}".format(os.path.join(self.app_project_path, sub_project)))
        self.logger.info("temp path:{}".format(os.path.join(os.path.join(temp_dir, sub_project))))
        self.copy_and_overwrite(os.path.join(self.app_project_path, sub_project), os.path.join(temp_dir, sub_project))
        self.cd(os.path.join(temp_dir, sub_project))

    def copy_project(self):
        self.cd_project()
        temp_dir = self.get_temp_dir()
        self.copy_and_overwrite(os.path.join(self.app_project_path), os.path.join(temp_dir, self.project_name))
        self.logger.info("project path:{}".format(os.path.join(temp_dir, self.project_name)))
        self.cd(os.path.join(temp_dir, self.project_name))

    def copy_and_overwrite(self, from_path, to_path):
        if os.path.exists(to_path):
            shutil.rmtree(to_path, ignore_errors=True)
        shutil.copytree(from_path, to_path)
