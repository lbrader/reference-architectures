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
from azure.mgmt.resource.subscriptions.subscription_client import SubscriptionClient
from azure.cli.core._profile import Profile
from azure.mgmt.resource.resources.models import DeploymentMode
from msrestazure.azure_exceptions import CloudError
from ..invoke_libs import render,resolvedns
import json
from . import remote
import zipfile
from ..log import logging
from ..invoke_libs.kube import KubeApi
from ..invoke_libs.git import GitHubApi
import yaml
from ..invoke_libs.image import Image
from ..invoke_libs.sync.copy_docker import CopyDocker
from ..invoke_libs.validators import validate_ssh_key
import tempfile
import shutil
from requests import post, put, get
from jinja2 import Environment, FileSystemLoader
import adal
import re

class Context(object):
    def __init__(self, **kwargs):

        try:
            self.__dict__ = kwargs
            self.logger = logging.get_logger(self.__class__.__name__)
            self.file = os.path.abspath(self.file)
            self.script = os.path.basename(self.file)
            self.cluster_config = get_cluster_config(self.datacenter)

            if not 'RESOURCE_GROUP_PREFIX' in self.cluster_config or not self.cluster_config['RESOURCE_GROUP_PREFIX']:
                self.logger.error("Exception: Resource group prefix can't be empty, please update RESOURCE_GROUP_PREFIX in clusters.ini file under root project directory")
                sys.exit(1)

            if len(self.cluster_config['RESOURCE_GROUP_PREFIX']) < 5:
                self.logger.error("Exception: Length of RESOURCE_GROUP_PREFIX should be >= 5 character")
                sys.exit(1)

            self.__dict__.update({
                'project_name': self.file.split(os.sep)[-2],
                'project_path': os.path.dirname(self.file),
                'app_datacenter': self.datacenter,
                'app_main': kwargs.get('app_main', self.cluster_config['APP_MAIN']),
                'app_docker_registry': "{}acr{}.azurecr.io".format(self.cluster_config['RESOURCE_GROUP_PREFIX'],self.datacenter),
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
                    'ssh_key_file': "{}{}".format(self.app_main, self.cluster_config['SSH_KEY_FILE'])})
            else:
                self.__dict__.update({
                    'ssh_key_file': ""})

            self.__dict__.update({
                'resource_group_prefix': self.cluster_config['RESOURCE_GROUP_PREFIX'],
                'location': self.cluster_config['LOCATION'],
                'user': self.datacenter})

            os.environ['RESOURCE_GROUP_PREFIX'] = self.resource_group_prefix

            self.logger.info("app_datacenter: {0.app_datacenter} ".format(self))
            self.resource_group = "{}-{}".format(self.resource_group_prefix, self.datacenter)


            self.credentials = ServicePrincipalCredentials(
                client_id=self.client_id,
                secret=self.client_secret,
                tenant=self.tenant_id
            )

            supported_regions = ["eastus", "westcentralus"]
            if not self.location in supported_regions:
                self.logger.error("Exception: Service not exist in the specified location {0}".format(self.location))
                self.logger.warn("Supported locations {0}".format(str(supported_regions)))
                sys.exit(1)
            else:
                self.logger.info("Using location: {0}".format(self.location))

            self.logger.info("Using resource group: {0.resource_group_prefix}-{0.datacenter}".format(self))
            if not self._checkazurelocation(self.location):
                self.logger.error("Exception: Specified location {0} not exit under your subscription".format(self.location))
                sys.exit(1)
            else:
                self.logger.info("Using location: {0}".format(self.location))

            try:
                profile = Profile()
                subscriptions = profile.find_subscriptions_on_login(
                    False,
                    self.client_id,
                    self.client_secret,
                    True,
                    self.tenant_id,
                    allow_no_subscriptions=False)
                subscription_name = json.loads(json.dumps(profile.get_subscription(self.subscription_id)))["name"]
                self.subscription_name =  re.sub('\W+', '', subscription_name).lower()
            except Exception as err:
                self.logger.error("Exception: Unable to get subscription details for the credentials provided {0}".format(err))
                sys.exit(1)

            validate_ssh_key(self.ssh_key_file)

            self.client = ResourceManagementClient(self.credentials, self.subscription_id)

            self._app_project_path()

        except Exception as err:
            self.logger.error("Exception: In Initializing the context {0}".format(err))
            sys.exit(1)

    def _checkazurelocation(self,name):
        try:
            result = list(SubscriptionClient(self.credentials).subscriptions.list_locations(self.subscription_id))
            for l in result:
                if name == l.name:
                    return True
            return False
        except Exception as err:
            self.logger.error("Exception: Unable to azure locations {0}".format(err))
            sys.exit(1)

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

    def cd(self, directory):
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



    def configure_jenkins(self):
        try:
            if self.group == "jenkins":
                self.sshclient = remote.sshclient("{resourcegroup}-release-jenkins.{location}.cloudapp.azure.com".format(resourcegroup=self.resource_group_prefix,
                    location=self.location), "{}jenkins".format(self.resource_group_prefix))

                self.attrs = {}
                ## Git configuration
                self.attrs['github_credentials_id'] = self.cluster_config['JENKINS_GITHUB_CREDENTIALS_ID']
                self.attrs['github_username'] = self.cluster_config['GIT_HUB_USER_NAME']
                self.attrs['github_token'] = self.cluster_config['GIT_HUB_TOKEN']
                self.attrs['git_org_id'] = self.cluster_config['GIT_HUB_ORG_ID']

                self.regionmap = {
                    "westcentralus": "West Central US",
                    "eastus": "East US"
                }

                ## Azure configuration
                self.attrs['azure_credentials_id'] = self.cluster_config['JENKINS_AZURE_CREDENTIALS_ID']
                self.attrs['subscriptionId'] = self.subscription_id
                self.attrs['clientId'] = self.client_id
                self.attrs['clientSecret'] = self.client_secret
                self.attrs['tenant'] = self.tenant_id
                self.attrs['location'] = self.regionmap[self.location]

                ## Jenkins VM slave
                self.attrs['jenkins_vm_credentials_id'] = "jenkins_vm_credentials_id"
                self.attrs['jenkins_vm_username'] = "jenkins"
                self.attrs['jenkins_vm_password'] = "cmadmin123!"
                self.attrs['jenkins_storage_account'] = "{}jenkinsslavest".format(self.resource_group_prefix)
                self.attrs['resource_group'] = "{}-jenkins".format(self.resource_group_prefix)

                ## Email Notification settings
                self.attrs['default_suffix'] = self.cluster_config['EMAIL_DEFAULT_SUFFIX']
                self.attrs['reply_to'] = self.cluster_config['EMAIL_REPLY_TO']
                self.attrs['smtp_host'] = self.cluster_config['EMAIL_SMTP_HOST']
                self.attrs['smtp_password'] = self.cluster_config['EMAIL_SMTP_PASSWORD']
                self.attrs['smtp_port'] = self.cluster_config['EMAIL_SMTP_PORT']
                self.attrs['smtp_user'] = self.cluster_config['EMAIL_SMTP_USER']

                ## Jenkins Location
                self.attrs['jenkins_admin_email'] = self.cluster_config['JENKINS_ADMIN_EMAIL']
                self.attrs[
                    'jenkins_main_url'] = "http://{resourcegroup}-release-jenkins.{location}.cloudapp.azure.com:8080".format(
                    resourcegroup=self.resource_group_prefix,
                    location=self.location)

                self.app_render()

                self.sshclient.zip(os.path.join(os.getcwd(), "ansible-jenkins"),"ansible-jenkins")

                self.sshclient.sendCommand("sudo rm -rf /tmp/*")
                self.sshclient.sendCommand("ls -la /tmp/")
                self.sshclient.copyFile("ansible-jenkins.zip")
                self.sshclient.copyFile(
                    os.path.join(self.app_main, "infrastructure", "configure", "jenkins", "configure.sh"))
                self.sshclient.sendCommand("ls -la /tmp/")
                self.logger.info("Started configuring jenkins ")
                log_output = self.sshclient.sendCommand("chmod +x /tmp/configure.sh ; cd /tmp/ ; ./configure.sh ")

                if log_output and "Completed Configure Jenkins" in log_output:
                    self.logger.info("Completed configuring jenkins ")
                else:
                    self.logger.exception("Error in jenkins configuration,Please refer logs")
                    sys.exit(1)

                os.remove("ansible-jenkins.zip")


            if self.group == "pre-jenkins":
                self.sshclient = remote.sshclient("{resourcegroup}-release-jenkins.{location}.cloudapp.azure.com".format(resourcegroup=self.resource_group_prefix,
                    location=self.location), "{}jenkins".format(self.resource_group_prefix))
                self.logger.info("Getting Jenkins admin credentials ")
                log_output = self.sshclient.sendCommand("sudo cat /var/lib/jenkins/secrets/initialAdminPassword")
                if not log_output:
                    self.logger.error("Unable to find the credentials either you have already configured jenkins, if not re-run the command after 5 mins")
                    sys.exit(1)
                else:
                    self.logger.warn("Jenkins credentials: {}".format(log_output))

                self.logger.info("Please use the above credentials for configuring jenkins")
        except Exception as err:
            self.logger.error("Exception: {0}".format(err))
            sys.exit(1)



    def app_render(self):
        list_files = ['all.yml']
        for files in list_files:
            self.app_render_template(self.find(files), files)


    def app_render_template(self, path, file):
        if path and os.path.exists(os.path.join(path, file)):
            env = Environment(loader=FileSystemLoader(os.path.join(path)))
            template = env.get_template(file)
            output_from_parsed_template = template.render(self.attrs)
            with open(os.path.join(path, file), "w") as fh:
                fh.write(output_from_parsed_template)


    def find(self, name):
        for root, dirs, files in os.walk(os.getcwd()):
            if name in files:
                return os.path.join(root)

    def configure_alerting(self):
       try:
        self.logger.info("Configuring Azure monitoring alerting for jenkins instance")
        for resource in self.client.resources.list():
            resourcename= "{}commonjenkins".format(self.resource_group_prefix)
            if resource.type == 'Microsoft.Compute/virtualMachines' and resource.name == resourcename:
                self.logger.info("Found jenkins instance {}".format(resource.name))
                attributes = {
                    "location": self.location,
                    "resourceid": resource.id,
                    "notification_email": self.cluster_config['NOTIFICATION_EMAIL'],
                    "lowthreshold": self.cluster_config['AZURE_MONITOR_CPU_LOWER_THRESHOLD'],
                    "higherthreshold": self.cluster_config['AZURE_MONITOR_CPU_UPPER_THRESHOLD']
                }

                if not attributes["lowthreshold"].isdigit():
                    self.logger.error("AZURE_MONITOR_CPU_UPPER_THRESHOLD value in clusters.ini is not an integer")
                    sys.exit(1)

                if not attributes["higherthreshold"].isdigit():
                    self.logger.error("AZURE_MONITOR_CPU_UPPER_THRESHOLD value in clusters.ini is not an integer")
                    sys.exit(1)

                attributes_rule = {
                     "cpuhigh" : cpu_high,
                     "cpulow": cpu_low,
                     "cpuzero": cpu_zero
                }
                context = adal.AuthenticationContext('https://login.microsoftonline.com/' + self.tenant_id)
                token_response = context.acquire_token_with_client_credentials('https://management.core.windows.net/',
                                                                               self.client_id, self.client_secret)
                access_token = token_response.get('accessToken')

                headers = {
                    "Authorization": 'Bearer ' + access_token,
                    "Content-Type": 'application/json'
                }

                rules = ["cpuhigh","cpulow","cpuzero"]
                for rule in rules:
                    uri = "https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group_prefix}-jenkins/providers/microsoft.insights/alertRules/{rule}?api-version=2014-04-01".format(subscription_id=self.subscription_id,resource_group_prefix=self.resource_group_prefix,rule=rule)
                    self.logger.debug(uri)
                    json_data = render(attributes_rule[rule], attributes)
                    self.logger.debug(json_data)
                    response = put(uri, json=json.loads(json_data), headers=headers)
                    if response.status_code == 201 or response.status_code == 200:
                        response.raise_for_status()
                        self.logger.info("Azure monitor alert rule creation success for {}".format(rule))
                    else:
                        self.logger.error("Azure monitor alert rule creation failed for {}".format(rule))
                        self.logger.error(response.status_code,response.json())

                    self.logger.debug(response.json())
       except Exception as err:
          self.logger.error("Exception: Error in creating azure monitor alerting, {0}".format(err))

    def validatedns(self):
        registry_name="{resourcegroup}acr{datacenter}".format(resourcegroup=self.resource_group_prefix,datacenter=self.datacenter)
        acr_dns = "{}.azurecr.io".format(registry_name)
        acs_dns = "{resourcegroup}-acs-mgmt-{datacenter}.{location}.cloudapp.azure.com".format(
            resourcegroup=self.resource_group_prefix, location=self.location,
            datacenter=self.datacenter)
        jenkins_dns = "{resourcegroup}-release-jenkins.{location}.cloudapp.azure.com".format(resourcegroup=self.resource_group_prefix,location=self.location)


        dns_kube_list = {
            "acr":acr_dns,
            "acs":acs_dns
        }

        dns_jenkins_list = {
            "jenkins": jenkins_dns
        }
        dns_list = {
            "dev": dns_kube_list,
            "test": dns_kube_list,
            "prod": dns_kube_list,
            "jenkins": dns_jenkins_list,
        }
        self.logger.info("Starting the pre-validate resource group check: {0.app_datacenter} ... ".format(self))
        resource_group_exist = False
        for item in self.client.resource_groups.list():
            if self.resource_group == item.name:
                resource_group_exist = True

        if not resource_group_exist:
            self.logger.info("Resource group {0.resource_group} not found under your subscription: {0.app_datacenter} ... ".format(self))
        else:
            self.logger.warn("Resource group {0.resource_group} found under your subscription: {0.app_datacenter} ... ".format(self))

        self.logger.info("Starting the pre-validate DNS check: {0.app_datacenter} ... ".format(self))

        for key, value in dns_list[self.datacenter].items():
           if not resource_group_exist and resolvedns(value):
               self.logger.error("DNS check failed for {}. Already the DNS is in use, Please specifiy a different resource group name in clusters.ini ".format(key))
               return False
           elif resource_group_exist and resolvedns(value):
               self.logger.warn("DNS check passed for {}. Already the DNS is in use in your subscription ".format(key))
           elif not resource_group_exist and not resolvedns(value):
               self.logger.info("DNS check passed for {}.".format(key))
           else:
               self.logger.info("DNS check passed for {} ".format(key))



        self.logger.info("All DNS check passed")
        return True

    def deploy(self, config_dict):
        """Deploy the template to a resource group."""

        # Dict that maps keys of CloudCenter's region names to values of Azure's region names.
        # Used below to control where something is deployed

        self.logger.info("Starting the deployment: {0.app_datacenter} ... ".format(self))

        try:
            self.client.resource_groups.create_or_update(
                self.resource_group,
                {
                    'location': self.location
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
            "resourcegroup": self.resource_group_prefix,
            "location": self.location,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }

        if 'sshkey' in str(parameters):
            pub_ssh_key_path = os.path.join(os.path.expanduser("~"),".ssh","id_rsa.pub")
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
                '{}-resource'.format(self.resource_group_prefix),
                deployment_properties
            )

            result = deployment_async_operation.result()
            msg = "Deployment completed. Outputs:"
            for k, v in result.properties.outputs.items():
                msg += f"\n- {k} = {str(v['value'])}"
            self.logger.warn(msg)
        except CloudError as err:
            self.logger.error("CloudError: {0}".format(err))
            sys.exit(1)
        except Exception as err:
            self.logger.error("Exception: {0}".format(err))
            sys.exit(1)

        self.logger.info("Completed the deployment: {0.app_datacenter} ... ".format(self))

    def destroy(self):
        """Destroy the given resource group"""
        self.logger.info("Deleting resource group: {0.app_datacenter} ... ".format(self))
        try:
            self.client.resource_groups.delete(self.resource_group)
        except CloudError as err:
            self.logger.error("CloudError: {0}".format(err))
            sys.exit(1)
        except Exception as err:
            self.logger.error("Exception: {0}".format(err))
            sys.exit(1)

        self.logger.info("Completed deleting: {0.app_datacenter} ... ".format(self))

    def sync_action(self, config_dict, args):
        attrs = {}
        cluster_config = get_cluster_config(self.datacenter)
        attrs['cluster_config'] = cluster_config
        attrs['app_docker_registry'] = self.app_docker_registry
        attrs['location'] = self.location
        attrs.update(config_dict)
        os.makedirs("{user}/.kube".format(user=os.path.expanduser("~")), exist_ok=True)
        self.sshclient = remote.sshclient("{resourcegroup}-acs-mgmt-{datacenter}.{location}.cloudapp.azure.com".format(
            resourcegroup=self.resource_group_prefix, location=self.location,
            datacenter=self.datacenter), "{resourcegroup}acs{datacenter}".format(
            resourcegroup=self.resource_group_prefix, datacenter=self.datacenter))
        self.sshclient.copyFileFrom(".kube/config", "{user}/.kube/config".format(user=os.path.expanduser("~")))
        self.logger.info("Copied kube config from acs remote server")
        copy = CopyDocker(datancenter=self.datacenter, **attrs)
        if args.task == "copy":
            copy.copy()

    def configure_git(self, args):
       jenkins_host= "{resourcegroup}-release-jenkins.{location}.cloudapp.azure.com".format(resourcegroup=self.resource_group_prefix,location=self.location)

       if args.repo == "" and 'GIT_HUB_APP_REPO_NAME' in self.cluster_config and  self.cluster_config['GIT_HUB_APP_REPO_NAME']:
           repo_name=self.cluster_config['GIT_HUB_APP_REPO_NAME']
       elif args.repo:
           repo_name=args.repo
       else:
           self.logger.error("Git Hub repo name not specificied in the clusters.ini")
           sys.exit(1)

       self.__dict__.update({
           'jenkins_host': jenkins_host,
           'image': args.image,
           'repo': repo_name})


       git = GitHubApi( **self.__dict__)
       if args.task == "repo":
            git.create_repo(repo_name,os.getcwd())
       elif args.task == "deleterepo":
           git.delete_repo(repo_name)
       elif args.task == "orghook":
           git.create_org_hook()
       elif args.task == "repohook":
           git.create_repo_hook(repo_name)
       elif args.task == "protect":
           git.set_protection(repo_name)
       elif args.task == "all":
           git.create_repo(repo_name, os.getcwd())
           git.create_repo_hook(repo_name)
           git.set_protection(args.image)

    def image_action(self, config_dict, args):
        attrs = {}
        # if args.task in ["build", "push", "deploy", "all"]:
        #     attrs['flatten'] = False
        #     attrs['move'] = True

        attrs['task'] = args.task
        cluster_config = get_cluster_config(self.datacenter)
        attrs['cluster_config'] = cluster_config
        attrs['app_docker_registry'] =self.app_docker_registry
        attrs['location'] = self.location
        attrs.update(config_dict)

        if args.task in ["deploy", "scale", "patch", "get", "getservice", "delete"]:
            os.makedirs(os.path.join(os.path.expanduser("~"),".kube"), exist_ok=True)
            self.sshclient = remote.sshclient("{resourcegroup}-acs-mgmt-{datacenter}.{location}.cloudapp.azure.com".format(resourcegroup=self.resource_group_prefix,location=self.location,datacenter=self.datacenter), "{resourcegroup}acs{datacenter}".format(resourcegroup=self.resource_group_prefix,datacenter=self.datacenter))
            self.sshclient.copyFileFrom(".kube/config",os.path.join(os.path.expanduser("~"),".kube","config"))
            self.logger.info("Copied kube config from acs remote server")
            kube = KubeApi(datacenter=self.datacenter, **attrs)
        if args.task in ["build", "push"]:
            image = Image(**attrs)

        if args.task == "deploy":
            kube.deploy()
        elif args.task == "scale":
            kube.scale()
        elif args.task == "patch":
            kube.patch()
        elif args.task == "get":
            kube.get()
        elif args.task == "getservice":
            kube.getservice()
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


    def _app_project_path(self):
        xs = self.project_path.split(os.sep)
        self.app_project_path = ''
        include = False
        for x in xs:
            if include:
                self.app_project_path = os.path.join(self.app_project_path, x)
            if 'joara-main' in x:
                include = True

        if self.app_project_path == '' and 'infrastructure' in xs:
            self.app_project_path = os.sep.join(xs[xs.index('infrastructure'):])
        else:
            self.app_project_path = self.app_project_path.lstrip(os.path.sep)

        self.logger.info("project path: {}".format(self.app_project_path))
        self.app_project_path = os.path.join(self.app_main, self.app_project_path)
        self.logger.info("Absolute project path: {} ".format(self.app_project_path))

    def cd_project(self):
        self.cd(self.app_project_path)


    def get_temp_dir(self):
        temp_dir = os.path.join(tempfile.gettempdir(), '.{}'.format(hash(os.times())))
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
        shutil.rmtree(to_path, ignore_errors=True)
        if os.path.exists(to_path):
            shutil.rmtree(to_path, ignore_errors=True)
        shutil.copytree(from_path, to_path)



cpu_high="""{
  "location": "{{ location }}",
  "tags": { },
  "properties": {
    "name": "CPUHigh Plan",
    "description": "The CPU is high across the Jenkins instances of Plan",
    "isEnabled": true,
    "condition": {
      "odata.type": "Microsoft.Azure.Management.Insights.Models.ThresholdRuleCondition",
      "dataSource": {
        "odata.type": "Microsoft.Azure.Management.Insights.Models.RuleMetricDataSource",
        "resourceUri": "{{ resourceid }}",
        "metricName": "Percentage CPU"
        
      },
      "operator": "GreaterThan",
      "threshold": {{ higherthreshold }},
      "windowSize": "PT5M"
    },
    "actions": [
      {
        "odata.type": "Microsoft.Azure.Management.Insights.Models.RuleEmailAction",
        "sendToServiceOwners": true,
        "customEmails": ["{{ notification_email }}"]
      }
    ]
  }
}""".strip()


cpu_zero="""{
  "location": "{{ location }}",
  "tags": { },
  "properties": {
    "name": "CPULow Plan",
    "description": "The CPU is Low across the Jenkins instances of Plan",
    "isEnabled": true,
    "condition": {
      "odata.type": "Microsoft.Azure.Management.Insights.Models.ThresholdRuleCondition",
      "dataSource": {
        "odata.type": "Microsoft.Azure.Management.Insights.Models.RuleMetricDataSource",
        "resourceUri": "{{ resourceid }}",
        "metricName": "Percentage CPU"
      },
      "operator": "LessThanOrEqual",
      "threshold": 0,
      "windowSize": "PT5M"
    },
    "actions": [
      {
        "odata.type": "Microsoft.Azure.Management.Insights.Models.RuleEmailAction",
        "sendToServiceOwners": true,
        "customEmails": ["{{ notification_email }}"]
      }
    ]
  }
}""".strip()

cpu_low="""{
  "location": "{{ location }}",
  "tags": { },
  "properties": {
    "name": "CPULow Plan",
    "description": "The CPU is Low across the Jenkins instances of Plan",
    "isEnabled": true,
    "condition": {
      "odata.type": "Microsoft.Azure.Management.Insights.Models.ThresholdRuleCondition",
      "dataSource": {
        "odata.type": "Microsoft.Azure.Management.Insights.Models.RuleMetricDataSource",
        "resourceUri": "{{ resourceid }}",
        "metricName": "Percentage CPU"
      },
      "operator": "LessThanOrEqual",
      "threshold": {{ lowthreshold }},
      "windowSize": "PT5M"
    },
    "actions": [
      {
        "odata.type": "Microsoft.Azure.Management.Insights.Models.RuleEmailAction",
        "sendToServiceOwners": true,
        "customEmails": ["{{ notification_email }}"]
      }
    ]
  }
}""".strip()