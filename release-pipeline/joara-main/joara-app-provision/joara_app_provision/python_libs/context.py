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
from azure.cli.command_modules.role.custom import create_service_principal_for_rbac, create_role_assignment, \
    delete_application
from azure.mgmt.resource.resources.models import DeploymentMode
from msrestazure.azure_exceptions import CloudError
from ..invoke_libs import render, resolvedns
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
import pickle
import time
from github import Github
from azure.keyvault import KeyVaultId
from azure.keyvault import KeyVaultClient
from azure.graphrbac import GraphRbacManagementClient
from azure.keyvault import KeyVaultClient
from azure.mgmt.keyvault import KeyVaultManagementClient
from azure.cli.core._profile import Profile


class Context(object):
    """
    Core init context for the joara, all command and actions are initialized from here. Manages credentials and root path for caller functions
    """
    def __init__(self, **kwargs):
        """
        Init context to manage entire joara app
        :param kwargs:
        """
        try:
            self.__dict__ = kwargs
            self.logger = logging.get_logger(self.__class__.__name__)
            self.file = os.path.abspath(self.file)
            self.script = os.path.basename(self.file)
            self.attributes = {}
            self.attributes.update(kwargs)
            if 'group' in kwargs:
                self.group = self.attributes['group']
            else:
                self.group = ""
            self.cluster_config = get_cluster_config(self.datacenter)

            if not 'RESOURCE_GROUP_PREFIX' in self.cluster_config or not self.cluster_config['RESOURCE_GROUP_PREFIX']:
                self.logger.error(
                    "Exception: Resource group prefix can't be empty, please update RESOURCE_GROUP_PREFIX in clusters.ini file under root project directory")
                sys.exit(1)

            if len(self.cluster_config['RESOURCE_GROUP_PREFIX']) < 5:
                self.logger.error("Exception: Length of RESOURCE_GROUP_PREFIX should be >= 5 character")
                sys.exit(1)

            self.__dict__.update({
                'project_name': self.file.split(os.sep)[-2],
                'project_path': os.path.dirname(self.file),
                'app_datacenter': self.datacenter,
                'app_main': kwargs.get('app_main', self.cluster_config['APP_MAIN']),
                'app_docker_registry': "{}acr{}.azurecr.io".format(self.cluster_config['RESOURCE_GROUP_PREFIX'],
                                                                   self.datacenter),
                "datacenter": self.datacenter
            })
            self.__dict__.update({
                'resource_group_prefix': self.cluster_config['RESOURCE_GROUP_PREFIX'],
                'location': self.cluster_config['LOCATION'],
                'user': self.datacenter})

            if self.group == "azure-setup":
                try:
                    if ('AZURE_SUBSCRIPTION_ID' in os.environ and 'AZURE_TENANT_ID' in os.environ):
                        self.__dict__.update({'subscription_id': os.environ['AZURE_SUBSCRIPTION_ID'],
                                              'tenant_id': os.environ['AZURE_TENANT_ID']})
                    else:
                        self.__dict__.update({'subscription_id': self.cluster_config['AZURE_SUBSCRIPTION_ID'],
                                              'tenant_id': self.cluster_config['AZURE_TENANT_ID']})

                except Exception as e:
                    logs = "Please update your azure subscription id and tenant id under clusters.ini or to environment variables , {}".format(
                        e)
                    self.logger.error(logs)
                    raise RuntimeError(logs)

                self.profile = Profile()
                subscriptions = self.profile.find_subscriptions_on_login(
                    True,
                    None,
                    None,
                    None,
                    self.tenant_id,
                    allow_no_subscriptions=False)
                all_subscriptions = list(subscriptions)
                self.current_user_id = all_subscriptions[0]["user"]["name"]
                self.logger.info("Logged in user id {0}".format(self.current_user_id))
                self.profile.set_active_subscription(self.subscription_id)
                cred, subscription_id, _ = self.profile.get_login_credentials()
                self.credentials = cred
                self.client = ResourceManagementClient(self.credentials, self.subscription_id)
            else:
                self.resource_group = "{}-{}".format(self.resource_group_prefix, self.datacenter)
                try:
                    if (
                                            'AZURE_CLIENT_ID' in os.environ and 'AZURE_CLIENT_SECRET' in os.environ and 'AZURE_TENANT_ID' in os.environ and 'AZURE_SUBSCRIPTION_ID' in os.environ):
                        self.__dict__.update({
                            'subscription_id': os.environ['AZURE_SUBSCRIPTION_ID'],
                            'client_id': os.environ['AZURE_CLIENT_ID'],
                            'client_secret': os.environ['AZURE_CLIENT_SECRET'],
                            'tenant_id': os.environ['AZURE_TENANT_ID']})

                        self.credentials = ServicePrincipalCredentials(
                            client_id=self.client_id,
                            secret=self.client_secret,
                            tenant=self.tenant_id
                        )
                    else:
                        try:
                            if ('AZURE_SUBSCRIPTION_ID' in os.environ and 'AZURE_TENANT_ID' in os.environ):
                                self.__dict__.update({'subscription_id': os.environ['AZURE_SUBSCRIPTION_ID'],
                                                      'tenant_id': os.environ['AZURE_TENANT_ID']})
                            else:
                                self.__dict__.update({'subscription_id': self.cluster_config['AZURE_SUBSCRIPTION_ID'],
                                                      'tenant_id': self.cluster_config['AZURE_TENANT_ID']})

                        except Exception as e:
                            logs = "Please update your azure subscription id under clusters.ini or to environment variables , {}".format(
                                e)
                            self.logger.error(logs)
                            raise RuntimeError(logs)

                        os.makedirs(os.path.join(os.path.expanduser("~"), ".joara"), exist_ok=True)
                        current_token_filename = os.path.join(os.path.expanduser("~"), ".joara",
                                                              "{}.pickle".format(self.resource_group))
                        read_from_cache = os.path.isfile(current_token_filename)

                        if (read_from_cache):
                            azure_credential = pickle.load(open(current_token_filename, "rb"))
                            self.client_id = azure_credential['AZURE_CLIENT_ID']
                            self.client_secret = azure_credential['AZURE_CLIENT_SECRET']
                            self.tenant_id = azure_credential['AZURE_TENANT_ID']
                            self.subscription_id = azure_credential['AZURE_SUBSCRIPTION_ID']

                        else:
                            profile = Profile()
                            subscriptions = profile.find_subscriptions_on_login(
                                True,
                                None,
                                None,
                                None,
                                self.tenant_id,
                                allow_no_subscriptions=False)
                            profile.set_active_subscription(self.subscription_id)

                            credkv, subscription_id, _ = profile.get_login_credentials(
                                resource='https://vault.azure.net')

                            client_kv = KeyVaultClient(credkv)
                            dc_list = ["dev", "test", "prod", "jenkins"]
                            for dc in dc_list:
                                resource_group = "{}-{}".format(self.resource_group_prefix, dc)
                                token_filename = os.path.join(os.path.expanduser("~"), ".joara",
                                                              "{}.pickle".format(resource_group))
                                vault_uri = "https://{}-kv.vault.azure.net".format(resource_group)
                                secret_name_list = ["AZURECLIENTID", "AZURECLIENTSECRET", "AZURETENANTID",
                                                    "AZURESUBSCRIPTIONID"]
                                azure_srvp_credential = {}
                                for secret_name in secret_name_list:
                                    output_secret = client_kv.get_secret(vault_uri, secret_name, secret_version='')
                                    try:
                                        if secret_name == "AZURECLIENTID":
                                            azure_srvp_credential["AZURE_CLIENT_ID"] = output_secret.value
                                        elif secret_name == "AZURECLIENTSECRET":
                                            azure_srvp_credential["AZURE_CLIENT_SECRET"] = output_secret.value
                                        elif secret_name == "AZURETENANTID":
                                            azure_srvp_credential["AZURE_TENANT_ID"] = output_secret.value
                                        elif secret_name == "AZURESUBSCRIPTIONID":
                                            azure_srvp_credential["AZURE_SUBSCRIPTION_ID"] = output_secret.value
                                        else:
                                            self.logger.error(
                                                "No service principal keys found for {}".format(secret_name))
                                            sys.exit(1)
                                    except Exception as e:
                                        logs = "Unable to get secret tokens , {}".format(e)
                                        self.logger.error(logs)
                                        raise RuntimeError(logs)

                                if dc == "jenkins":
                                    secret_name_list = ["GITHUBTOKEN", "SMTPPASSWORD"]
                                    for secret_name in secret_name_list:
                                        output_secret = client_kv.get_secret(vault_uri, secret_name, secret_version='')
                                        try:
                                            if secret_name == "GITHUBTOKEN":
                                                azure_srvp_credential["GITHUB_TOKEN"] = output_secret.value
                                            elif secret_name == "SMTPPASSWORD":
                                                azure_srvp_credential["SMTP_PASSWORD"] = output_secret.value
                                            else:
                                                self.logger.error(
                                                    "No keys found for {}".format(secret_name))
                                                sys.exit(1)
                                        except Exception as e:
                                            logs = "Unable to get secret tokens , {}".format(e)
                                            self.logger.error(logs)
                                            raise RuntimeError(logs)


                                pickle.dump(azure_srvp_credential, open(token_filename, "wb"))

                        azure_credential = pickle.load(open(current_token_filename, "rb"))
                        self.client_id = azure_credential['AZURE_CLIENT_ID']
                        self.client_secret = azure_credential['AZURE_CLIENT_SECRET']
                        self.tenant_id = azure_credential['AZURE_TENANT_ID']
                        self.subscription_id = azure_credential['AZURE_SUBSCRIPTION_ID']

                        if 'GITHUB_TOKEN' in azure_credential:
                            self.github_token = azure_credential['GITHUB_TOKEN']

                        if 'SMTP_PASSWORD' in azure_credential:
                            self.smtp_password = azure_credential['SMTP_PASSWORD']

                        self.credentials = ServicePrincipalCredentials(
                            client_id=self.client_id,
                            secret=self.client_secret,
                            tenant=self.tenant_id
                        )
                except Exception as e:
                    logs = "Unable to authenticate, {}".format(
                        e)
                    self.logger.error(logs)
                    raise RuntimeError(logs)

                if 'SSH_KEY_FILE' in self.cluster_config:
                    self.__dict__.update({
                        'ssh_key_file': "{}{}".format(self.app_main, self.cluster_config['SSH_KEY_FILE'])})
                else:
                    self.__dict__.update({
                        'ssh_key_file': ""})

                os.environ['RESOURCE_GROUP_PREFIX'] = self.resource_group_prefix

                self.logger.info("app_datacenter: {0.app_datacenter} ".format(self))

                if self.group != "":
                    validate_ssh_key(self.ssh_key_file)

                self.client = ResourceManagementClient(self.credentials, self.subscription_id)
                self.check_location()
            self._app_project_path()

        except Exception as err:
            self.logger.error("Exception: In Initializing the context {0}".format(err))
            sys.exit(1)

    def register_providers(self):
        """
        Registers resource providers to subscription
        :return:
        """
        try:
            self.logger.info("################### Started Registering resource providers ###################")
            providers_list = ["Microsoft.Insights","Microsoft.Compute","Microsoft.ContainerService","Microsoft.ContainerRegistry","Microsoft.KeyVault","Microsoft.Storage"]
            for provider in providers_list:
                self.logger.info("Registering resource provider '{}' ".format(provider))
                self.client.providers.register(provider)
            self.logger.info("################### Completed Registering resource providers ###################")
        except CloudError as err:
            self.logger.error("CloudError: {0}".format(err))
            sys.exit(1)
        except Exception as err:
            self.logger.error("Exception: {0}".format(err))
            sys.exit(1)

    def check_location(self):
        """
        Checks azure resource location and exit program if its a not a valid location
        :return:
        """
        supported_regions = ["eastus", "westcentralus"]
        if not self.location in supported_regions:
            self.logger.error("Exception: Service not exist in the specified location {0}".format(self.location))
            self.logger.warn("Supported locations {0}".format(str(supported_regions)))
            sys.exit(1)
        else:
            self.logger.info("Using location: {0}".format(self.location))

        self.logger.info("Using resource group: {0.resource_group_prefix}-{0.datacenter}".format(self))
        if not self._checkazurelocation(self.location):
            self.logger.error(
                "Exception: Specified location {0} not exit under your subscription".format(self.location))
            sys.exit(1)
        else:
            self.logger.info("Using location: {0}".format(self.location))

    def _get_github_token(self):
        """
        Gets github token input from user, if its valid proceeds further else stop here
        :return:
        """
        try:
            while True:
                try:
                    github_token = input("Please enter your GitHuB Token: ")
                except ValueError:
                    self.logger.error("Sorry, I didn't understand that.")
                    continue

                if not github_token:
                    self.logger.error("Sorry, your response is not valid.")
                    continue
                try:
                    self.logger.warning("Validating GitHub token.")
                    g = Github(github_token)
                    org = g.get_organization(self.cluster_config['GIT_HUB_ORG_ID'])
                    org.get_repos()
                    self.github_token = github_token
                    break
                except Exception as err:
                    self.logger.error("GitHub token is invalid.")
                    self.logger.error("Exception: {0}".format(err))
                    continue

            repo_name="test-joara-init"
            repo_exist=False
            for gitrepo in org.get_repos(repo_name):
                if gitrepo.name == repo_name:
                    repo_exist = True

            if not repo_exist:
                repo = org.create_repo(repo_name)
                time.sleep(60)
                org.get_repo(repo_name).create_hook("jenkins", {"jenkins_hook_url": "http://test/github-webhook/"})
                org.get_repo(repo_name).delete()
                self.logger.info("GitHub token is valid.")
        except Exception as err:
            self.logger.error("Exception GitHub Token: {0}".format(err))

    def _check_smtp(self):
        """
        Get Email SMTP password from user
        :return:
        """
        try:
            _RETRY_TIMES = 3
            for l in range(0, _RETRY_TIMES):
                try:
                    smtp_password = input("Please enter your SMTP password: ")
                except ValueError:
                    self.logger.error("Sorry, I didn't understand that.")
                    continue

                if not smtp_password:
                    self.logger.error("Sorry, your response is not valid.")
                    continue
                try:
                    import smtplib
                    self.logger.warning("Validating SMTP details.")
                    server = smtplib.SMTP(self.cluster_config['JENKINS_EMAIL_SMTP_HOST'],
                                          self.cluster_config['JENKINS_EMAIL_SMTP_PORT'])
                    server.login(self.cluster_config['JENKINS_EMAIL_SMTP_USER'], smtp_password)
                    msg = "Hello!-test-joara"
                    server.sendmail(self.cluster_config['JENKINS_ADMIN_EMAIL'],self.cluster_config['NOTIFICATION_EMAIL'], msg)
                    self.smtp_password = smtp_password
                    self.logger.info("SMTP details are valid.")
                    break
                except Exception as err:
                    if l < _RETRY_TIMES - 1:
                        self.logger.error("SMTP details are invalid. Please check your SMTP details in clusters.ini and your entered password")
                        self.logger.error("Exception SMTP: {0}".format(err))
                        self.logger.warning('Invalid smtp details, retrying smtp: %s/%s', l + 1, _RETRY_TIMES)
                        continue
                    else:
                        self.logger.error("SMTP details are invalid.")
                        self.logger.error("Exception SMTP: {0}".format(err))
                        self.logger.warning("##### Please try updating SMTP details manually from jenkins UI ##### ")
                        self.smtp_password = "notvalid"
                        break
        except Exception as err:
            self.logger.error("Exception SMTP details: {0}".format(err))


    def configure_azure(self):
        """
        Core to configure azure with creation of service principal, key vault and role assignment - works only for owner with administrative privileges
        :return:
        """
        self.logger.info("Started azure configure")
        try:
            self.register_providers()
            self.check_location()
            self._get_github_token()
            self._check_smtp()
            if not self.github_token:
                self.logger.error("GitHub Token: {0} is invalid".format(self.github_token))
                sys.exit(1)

            credkv, subscription_id, _ = self.profile.get_login_credentials(resource='https://vault.azure.net')
            credgm, subscription_id, _ = self.profile.get_login_credentials(resource='https://graph.windows.net')
            client_kv = KeyVaultClient(credkv)
            resource_group_name = self.attributes['resourcegroup']
            dc_list = ["dev", "test", "prod", "jenkins"]
            graphrbac_client = GraphRbacManagementClient(
                credgm,
                self.tenant_id
            )
            user = graphrbac_client.users.get(self.attributes['useremail'])
            current_user = graphrbac_client.users.get(self.current_user_id)
            self.logger.info("Access granting to user id {0}".format(user.object_id))
            for dc in dc_list:
                client = ResourceManagementClient(self.credentials, subscription_id)
                resource_group = "{}-{}".format(resource_group_name, dc)
                self.logger.info("Resource group creation started {0}".format(resource_group))
                try:
                    client.resource_groups.create_or_update(
                        resource_group,
                        {
                            'location': self.location
                        }
                    )

                    self.logger.info("Resource group creation completed {0}".format(resource_group))
                except Exception as err:
                    self.logger.error(
                        "Exception: Resource group creation failed for datacenter: {}, {}".format(dc, err))
                    sys.exit(1)
            for dc in dc_list:
                resource_group = "{}-{}".format(resource_group_name, dc)
                kv_client = KeyVaultManagementClient(self.credentials, subscription_id)
                self.logger.info("Key vault creation started for datacenter: {0}".format(dc))
                try:
                    vault = kv_client.vaults.create_or_update(
                        resource_group,
                        "{}-kv".format(resource_group),
                        {
                            'location': self.location,
                            'properties': {
                                'sku': {
                                    'name': 'standard'
                                },
                                'tenant_id': self.tenant_id,
                                'access_policies': [{
                                    'tenant_id': self.tenant_id,
                                    'object_id': user.object_id,
                                    'permissions': {
                                        'keys': ['all'],
                                        'secrets': ['all']
                                    }
                                },
                                    {
                                        'tenant_id': self.tenant_id,
                                        'object_id': current_user.object_id,
                                        'permissions': {
                                            'keys': ['all'],
                                            'secrets': ['all']
                                        }
                                    }
                                ]
                            }
                        }
                    )
                    self.logger.info("Key vault creation completed for datacenter: {0}".format(dc))
                except Exception as err:
                    self.logger.error("Exception: Key vault creation failed for datacenter: {}, {}".format(dc, err))
                    sys.exit(1)
                app_name = resource_group
                self.logger.info("Service principal creation started for datacenter: {0}".format(dc))
                try:
                    json_srvp = create_service_principal_for_rbac(name=app_name, role="owner", show_auth_for_sdk=False,skip_assignment=True)
                    self.logger.info("Service principal creation completed for datacenter: {0}".format(dc))
                except Exception as err:
                    self.logger.error(
                        "Exception: Service principal creation failed for datacenter: {}, {}".format(dc, err))
                    sys.exit(1)

                self.logger.info("Key vault secret creation started for datacenter: {0}".format(dc))

                try:
                    if dc == "jenkins":
                        # Create a secret
                        secret_bundle = client_kv.set_secret(vault.properties.vault_uri, 'GITHUBTOKEN',
                                                             self.github_token)
                        secret_id = KeyVaultId.parse_secret_id(secret_bundle.id)

                        # Create a secret
                        secret_bundle = client_kv.set_secret(vault.properties.vault_uri, 'SMTPPASSWORD',
                                                             self.smtp_password)
                        secret_id = KeyVaultId.parse_secret_id(secret_bundle.id)

                    # Create a secret
                    secret_bundle = client_kv.set_secret(vault.properties.vault_uri, 'AZURECLIENTID',
                                                         json_srvp["appId"])
                    secret_id = KeyVaultId.parse_secret_id(secret_bundle.id)

                    # Create a secret
                    secret_bundle = client_kv.set_secret(vault.properties.vault_uri, 'AZURECLIENTSECRET',
                                                         json_srvp["password"])
                    secret_id = KeyVaultId.parse_secret_id(secret_bundle.id)

                    # Create a secret
                    secret_bundle = client_kv.set_secret(vault.properties.vault_uri, 'AZURETENANTID',
                                                         json_srvp["tenant"])
                    secret_id = KeyVaultId.parse_secret_id(secret_bundle.id)

                    # Create a secret
                    secret_bundle = client_kv.set_secret(vault.properties.vault_uri, 'AZURESUBSCRIPTIONID',
                                                         subscription_id)
                    secret_id = KeyVaultId.parse_secret_id(secret_bundle.id)
                    self.logger.info("Key vault secret creation completed for datacenter: {0}".format(dc))
                except Exception as err:
                    self.logger.error(
                        "Exception: Key vault secret creation failed for datacenter: {}, {}".format(dc, err))
                    sys.exit(1)

                _RETRY_TIMES = 36
                for l in range(0, _RETRY_TIMES):
                    try:

                        if dc == "test":
                            output = create_role_assignment(role="owner", assignee=json_srvp["name"],
                                                            resource_group_name=resource_group)
                            output = create_role_assignment(role="contributor", assignee=json_srvp["name"],
                                                            resource_group_name="{}-{}".format(resource_group_name,
                                                                                               "dev"))
                        elif dc == "prod":
                            output = create_role_assignment(role="owner", assignee=json_srvp["name"],
                                                            resource_group_name=resource_group)
                            output = create_role_assignment(role="contributor", assignee=json_srvp["name"],
                                                            resource_group_name="{}-{}".format(resource_group_name,
                                                                                               "test"))
                        else:
                            output = create_role_assignment(role="owner", assignee=json_srvp["name"],
                                                            resource_group_name=resource_group)

                        output = create_role_assignment(role="owner", assignee=self.attributes['useremail'],
                                                        resource_group_name=resource_group)
                        break
                    except Exception as ex:  # pylint: disable=broad-except
                        if l < _RETRY_TIMES and (' does not reference ' in str(ex) or ' does not exist ' in str(ex)):
                            time.sleep(5)
                            self.logger.warning('Retrying role assignment: %s/%s', l + 1, _RETRY_TIMES)
                        else:
                            self.logger.error(
                                "Creating role assignment principal failed for appid '%s'. Trace followed:\n%s",
                                json_srvp["name"],
                                ex.response.headers if hasattr(ex, 'response') else ex)  # pylint: disable=no-member
                            raise

                self.logger.info("Completed for datacenter: {0}".format(dc))
            self.logger.info("Completed azure configure")
        except Exception as err:
            self.logger.error("Exception: Azure configuration failed, {0}".format(err))
            sys.exit(1)

    def run_win_cmd(self, cmd):
        result = []
        print(cmd)
        subprocess.Popen(cmd, shell=True)

    def _checkazurelocation(self, name):
        """
        Returns true the location used by the user is valid
        :param name:
        :return:
        """
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
        """
        Configures jenkins with pre and post. Pre gets the password for authenticating to jenkins and post configures the entire jenkins
        :return:
        """
        try:
            if self.group == "jenkins":
                self.sshclient = remote.sshclient(
                    "{resourcegroup}-release-jenkins.{location}.cloudapp.azure.com".format(
                        resourcegroup=self.resource_group_prefix,
                        location=self.location), "{}jenkins".format(self.resource_group_prefix))

                self.attrs = {}
                ## Git configuration
                self.attrs['github_credentials_id'] = self.cluster_config['JENKINS_GITHUB_CREDENTIALS_ID']
                self.attrs['github_username'] = self.cluster_config['GIT_HUB_USER_NAME']
                self.attrs['github_token'] = self.github_token
                self.attrs['git_org_id'] = self.cluster_config['GIT_HUB_ORG_ID']

                self.regionmap = {
                    "westcentralus": "West Central US",
                    "eastus": "East US"
                }

                ## Azure configuration - dev
                self.attrs['azure_credentials_id'] = self.cluster_config['JENKINS_AZURE_CREDENTIALS_ID']

                dc_list = ["dev", "test", "prod", "jenkins"]
                for dc in dc_list:
                    resource_group = "{}-{}".format(self.resource_group_prefix, dc)
                    token_filename = os.path.join(os.path.expanduser("~"), ".joara",
                                                  "{}.pickle".format(resource_group))

                    azure_credential = pickle.load(open(token_filename, "rb"))
                    self.attrs['{}_subscriptionId'.format(dc)] = azure_credential['AZURE_SUBSCRIPTION_ID']
                    self.attrs['{}_clientId'.format(dc)] = azure_credential['AZURE_CLIENT_ID']
                    self.attrs['{}_clientSecret'.format(dc)] = azure_credential['AZURE_CLIENT_SECRET']
                    self.attrs['{}_tenant'.format(dc)] = azure_credential['AZURE_TENANT_ID']

                
                self.attrs['location'] = self.regionmap[self.location]

                ## Jenkins VM slave
                self.attrs['jenkins_vm_credentials_id'] = "jenkins_vm_credentials_id"
                self.attrs['jenkins_vm_username'] = "jenkins"
                self.attrs['jenkins_vm_password'] = "cmadmin123!"
                self.attrs['jenkins_storage_account'] = "{}jenkinsslavest".format(self.resource_group_prefix)
                self.attrs['resource_group'] = "{}-jenkins".format(self.resource_group_prefix)

                ## Email Notification settings
                self.attrs['default_suffix'] = "@azure.com"
                self.attrs['reply_to'] = ""
                self.attrs['smtp_host'] = self.cluster_config['JENKINS_EMAIL_SMTP_HOST']
                self.attrs['smtp_password'] = self.smtp_password
                self.attrs['smtp_port'] = self.cluster_config['JENKINS_EMAIL_SMTP_PORT']
                self.attrs['smtp_user'] = self.cluster_config['JENKINS_EMAIL_SMTP_USER']

                ## Jenkins Location
                self.attrs['jenkins_admin_email'] = self.cluster_config['JENKINS_ADMIN_EMAIL']
                self.attrs[
                    'jenkins_main_url'] = "http://{resourcegroup}-release-jenkins.{location}.cloudapp.azure.com:8080".format(
                    resourcegroup=self.resource_group_prefix,
                    location=self.location)

                self.app_render()

                self.sshclient.zip(os.path.join(os.getcwd(), "ansible-jenkins"), "ansible-jenkins")

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
                self.sshclient = remote.sshclient(
                    "{resourcegroup}-release-jenkins.{location}.cloudapp.azure.com".format(
                        resourcegroup=self.resource_group_prefix,
                        location=self.location), "{}jenkins".format(self.resource_group_prefix))
                self.logger.info("Getting Jenkins admin credentials ")

                _RETRY_TIMES = 20
                for l in range(0, _RETRY_TIMES):
                    try:
                        log_output = self.sshclient.sendCommand(
                            "sudo cat /var/lib/jenkins/secrets/initialAdminPassword")
                        if not log_output:
                            raise Exception('Unable to get jenkins credentials')
                        else:
                            self.logger.warn("Jenkins credentials: {}".format(log_output))

                        self.logger.info("Please use the above credentials for configuring jenkins")
                        break
                    except Exception as ex:
                        if l < _RETRY_TIMES-1:
                            time.sleep(30)
                            self.logger.warning('Retrying to get jenkins credentials: %s/%s', l + 1, _RETRY_TIMES)
                        else:
                            self.logger.error(
                                "Unable to find the credentials either you have already configured jenkins, if not re-run the pre-jenkins command after 5 mins")
                            sys.exit(1)



        except Exception as err:
            self.logger.error("Exception: {0}".format(err))
            sys.exit(1)

    def app_render(self):
        """
        Replaces template file with values for jenkins ansible variables
        :return:
        """
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
        """
        Configures azure monitor alerting for CPU loads in Jenkins VM
        :return:
        """
        try:
            self.logger.info("Configuring Azure monitoring alerting for jenkins instance")
            for resource in self.client.resources.list():
                resourcename = "{}commonjenkins".format(self.resource_group_prefix)
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
                        "cpuhigh": cpu_high,
                        "cpulow": cpu_low,
                        "cpuzero": cpu_zero
                    }

                    context = adal.AuthenticationContext('https://login.microsoftonline.com/' + self.tenant_id)
                    token_response = context.acquire_token_with_client_credentials(
                        'https://management.core.windows.net/', self.client_id, self.client_secret)
                    access_token = token_response.get('accessToken')

                    headers = {
                        "Authorization": 'Bearer ' + access_token,
                        "Content-Type": 'application/json'
                    }

                    rules = ["cpuhigh", "cpulow", "cpuzero"]
                    for rule in rules:
                        uri = "https://management.azure.com/subscriptions/{subscription_id}/resourceGroups/{resource_group_prefix}-jenkins/providers/microsoft.insights/alertRules/{rule}?api-version=2014-04-01".format(
                            subscription_id=self.subscription_id, resource_group_prefix=self.resource_group_prefix,
                            rule=rule)
                        self.logger.debug(uri)
                        json_data = render(attributes_rule[rule], attributes)
                        self.logger.debug(json_data)
                        response = put(uri, json=json.loads(json_data), headers=headers)
                        if response.status_code == 201 or response.status_code == 200:
                            response.raise_for_status()
                            self.logger.info("Azure monitor alert rule creation success for {}".format(rule))
                        else:
                            self.logger.error("Azure monitor alert rule creation failed for {}".format(rule))
                            self.logger.error("{},{}".format(response.status_code, response.json()))

                        self.logger.debug(response.json())
        except Exception as err:
            self.logger.error("Exception: Error in creating azure monitor alerting, {0}".format(err))

    def validatedns(self):
        """
        Returns true if the resource group name specified by the user is valid by checking whether the DNS is valid by resolving a DNS
        Validates for all datacenter ACR, Jenkins and ACS resources
        :return: true if resource is valid else false
        """
        all_datacenters = ['dev', 'test', 'prod', 'jenkins']
        for dc in all_datacenters:
            registry_name = "{resourcegroup}acr{datacenter}".format(resourcegroup=self.resource_group_prefix,
                                                                    datacenter=dc)
            resource_group = "{resourcegroup}-{datacenter}".format(resourcegroup=self.resource_group_prefix,
                                                                  datacenter=dc)
            acr_dns = "{}.azurecr.io".format(registry_name)
            acs_dns = "{resourcegroup}-acs-mgmt-{datacenter}.{location}.cloudapp.azure.com".format(
                resourcegroup=self.resource_group_prefix, location=self.location,
                datacenter=dc)
            jenkins_dns = "{resourcegroup}-release-jenkins.{location}.cloudapp.azure.com".format(
                resourcegroup=self.resource_group_prefix, location=self.location)

            dns_kube_list = {
                "acr": acr_dns,
                "acs": acs_dns
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
                if resource_group == item.name:
                    resource_group_exist = True

            if not resource_group_exist:
                self.logger.info(
                    "Resource group {} not found under your subscription: {} ... ".format(resource_group, dc))
            else:
                self.logger.warn(
                    "Resource group {} found under your subscription: {} ... ".format(resource_group, dc))

            self.logger.info("Starting the pre-validate DNS check: {} ... ".format(dc))

            for key, value in dns_list[dc].items():
                if not resource_group_exist and resolvedns(value):
                    self.logger.error(
                        "DNS check failed for {}. Already the DNS is in use, Please specifiy a different resource group name in clusters.ini ".format(
                            key))
                    self.logger.error("Pre-validate condition failed: {} ... ".format(dc))
                    return False
                elif resource_group_exist and resolvedns(value):
                    self.logger.warn(
                        "DNS check passed for {}. Already the DNS is in use in your subscription ".format(key))
                elif not resource_group_exist and not resolvedns(value):
                    self.logger.info("DNS check passed for {}.".format(key))
                else:
                    self.logger.info("DNS check passed for {} ".format(key))
            self.logger.info("Pre-validate condition passed: {} ... ".format(dc))
        self.logger.info("All DNS check passed")
        return True

    def deploy(self, config_dict):
        """Deploy the template to a resource group."""

        # Dict that maps keys of CloudCenter's region names to values of Azure's region names.
        # Used below to control where something is deployed

        self.logger.info("Starting the deployment: {0.app_datacenter} ... ".format(self))

        # try:
        #     self.client.resource_groups.create_or_update(
        #         self.resource_group,
        #         {
        #             'location': self.location
        #         }
        #     )
        # except CloudError as err:
        #     self.logger.error("CloudError: {0}".format(err))
        #     sys.exit(1)
        # except Exception as err:
        #     self.logger.error("Exception: {0}".format(err))
        #     sys.exit(1)

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
            pub_ssh_key_path = os.path.join(os.path.expanduser("~"), ".ssh", "id_rsa.pub")
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
        """
        Manages docker version sync between docker registry and datacenter
        :param config_dict: list of values for dataenter and registry of from and to
        :param args:
        :return:
        """
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
        copy = CopyDocker(datacenter=self.datacenter, **attrs)
        if args.task == "copy":
            copy.copy()

    def configure_git(self, args):
        """
        Configures git repository with repo code, webhooks and protects
        :param args: repo details and actions on the repo
        :return:
        """
        jenkins_host = "{resourcegroup}-release-jenkins.{location}.cloudapp.azure.com".format(
            resourcegroup=self.resource_group_prefix, location=self.location)

        if args.repo == "" and 'GIT_HUB_APP_REPO_NAME' in self.cluster_config and self.cluster_config[
            'GIT_HUB_APP_REPO_NAME']:
            repo_name = self.cluster_config['GIT_HUB_APP_REPO_NAME']
        elif args.repo:
            repo_name = args.repo
        else:
            self.logger.error("Git Hub repo name not specified in the clusters.ini")
            sys.exit(1)

        self.__dict__.update({
            'jenkins_host': jenkins_host,
            'git_hub_token': self.github_token,
            'image': args.image,
            'repo': repo_name})

        git = GitHubApi(**self.__dict__)
        if args.task == "repo":
            git.create_repo(repo_name, os.getcwd())
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
        """
        Performs action on image like deploy, scale, patch, rollback and getservice on Kube
        :param config_dict: List of image and conf details
        :param args: actions to be performed on the image
        :return:
        """
        attrs = {}
        attrs['task'] = args.task
        cluster_config = get_cluster_config(self.datacenter)
        attrs['cluster_config'] = cluster_config
        attrs['app_docker_registry'] = self.app_docker_registry
        attrs['location'] = self.location

        if args.task == "rollback":
            if args.version == "":
                self.logger.info("Image: {}, Version: {} for rollback is not valid".format(config_dict["name"],args.version))
                sys.exit(1)
            attrs['version'] = args.version
        attrs.update(config_dict)

        if args.task in ["deploy", "scale", "patch", "get", "getservice", "delete","rollback"]:
            os.makedirs(os.path.join(os.path.expanduser("~"), ".kube"), exist_ok=True)
            self.sshclient = remote.sshclient(
                "{resourcegroup}-acs-mgmt-{datacenter}.{location}.cloudapp.azure.com".format(
                    resourcegroup=self.resource_group_prefix, location=self.location, datacenter=self.datacenter),
                "{resourcegroup}acs{datacenter}".format(resourcegroup=self.resource_group_prefix,
                                                        datacenter=self.datacenter))
            self.sshclient.copyFileFrom(".kube/config", os.path.join(os.path.expanduser("~"), ".kube", "config"))
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
        elif args.task == "rollback":
            kube.rollback()
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


cpu_high = """{
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

cpu_zero = """{
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

cpu_low = """{
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
