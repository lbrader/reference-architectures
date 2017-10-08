from __future__ import absolute_import, print_function
from invoke import run
from subprocess import check_call, check_output,getoutput
from docker import Client
from ..invoke_libs.version_manager import VersionManager
from distutils.util import strtobool
from datetime import datetime
from pytz import timezone
from semantic_version import Version
import os
from git import Repo
import sys
import socket
import json
from azure.mgmt.storage import StorageManagementClient
from azure.common.credentials import ServicePrincipalCredentials
import git
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.containerregistry import ContainerRegistryManagementClient
from azure.cli.command_modules.acr.custom import acr_login
from base64 import b64encode
import requests
from requests.utils import to_native_string
import pickle
from ..log import logging

class Image(object):
    """
    Init image context with details of image and credentials
    """
    def __init__(self, **kwargs):
        self.attributes = {
            'user': 'dev',
            'dockerfile_ext': None,
            'registry_version': 'v2',
            'deploy': False
        }
        self.logger = logging.get_logger(self.__class__.__name__)
        self.attributes.update(kwargs)
        if 'dockerfile_ext' in kwargs:
            self.attributes['dockerfile'] = "Dockerfile.{}".format(kwargs['dockerfile_ext'])
        else:
            self.attributes['dockerfile'] = "Dockerfile"

        self.task =self.attributes['task']
        self.attributes['app_main'] = self.attributes['cluster_config']['APP_MAIN']
        self.attributes['user'] = self.attributes['cluster_config']['APP_DATACENTER']
        self.app_main = self.attributes['app_main']
        self.attributes['datacenter'] = self.attributes['cluster_config']['APP_DATACENTER']
        self.datacenter = self.attributes['datacenter']
        self.docker_user = self.attributes['cluster_config']['APP_DATACENTER']
        self.app_docker_registry="{}acr{}.azurecr.io".format(self.attributes['cluster_config']['RESOURCE_GROUP_PREFIX'], self.datacenter)
        self.resource_group_prefix = self.attributes['cluster_config']['RESOURCE_GROUP_PREFIX']
        self.resource_group = "{}-{}".format(self.resource_group_prefix, self.datacenter)
        self.attributes['commit'] = self._get_git_commit()
        self.attributes['datetime'] = self._get_utcnow()

        try:
            if ( 'AZURE_CLIENT_ID' in os.environ and 'AZURE_CLIENT_SECRET' in os.environ and 'AZURE_TENANT_ID' in os.environ and 'AZURE_SUBSCRIPTION_ID' in os.environ) :

                self.__dict__.update({
                    'subscription_id': os.environ['AZURE_SUBSCRIPTION_ID'],
                    'client_id': os.environ['AZURE_CLIENT_ID'],
                    'client_secret': os.environ['AZURE_CLIENT_SECRET'],
                    'tenant_id': os.environ['AZURE_TENANT_ID']})
            else:
                cuurent_token_filename = os.path.join(os.path.expanduser("~"), ".joara",
                                                      "{}.pickle".format(self.resource_group))
                read_from_cache = os.path.isfile(cuurent_token_filename)

                if (read_from_cache):
                    azure_credentital = pickle.load(open(cuurent_token_filename, "rb"))
                    self.client_id = azure_credentital['AZURE_CLIENT_ID']
                    self.client_secret = azure_credentital['AZURE_CLIENT_SECRET']
                    self.tenant_id = azure_credentital['AZURE_TENANT_ID']
                    self.subscription_id = azure_credentital['AZURE_SUBSCRIPTION_ID']

                os.environ['AZURE_CLIENT_ID'] = self.client_id
                os.environ['AZURE_CLIENT_SECRET'] = self.client_secret
                os.environ['AZURE_TENANT_ID'] = self.tenant_id
                os.environ['AZURE_SUBSCRIPTION_ID'] = self.subscription_id
        except Exception as e:
                logs = "### Please update your azure credentials under culsters.ini or to environment variables ###, {}".format(e)
                self.logger.error(logs)
                raise RuntimeError(logs)

        self.credentials = ServicePrincipalCredentials(
            client_id=self.client_id,
            secret=self.client_secret,
            tenant=self.tenant_id
        )

        self.client = ContainerRegistryManagementClient(self.credentials, self.subscription_id)

        if self.task == "build" or self.task == "push":
            if ('AZURE_CLIENT_ID' in os.environ and 'AZURE_CLIENT_SECRET' in os.environ and 'AZURE_TENANT_ID' in os.environ and 'AZURE_SUBSCRIPTION_ID' in os.environ):
                storage_client = StorageManagementClient(self.credentials, os.environ['AZURE_SUBSCRIPTION_ID'])

                storage_name = "{}{}".format(self.resource_group_prefix, self.datacenter)
                storage_keys = storage_client.storage_accounts.list_keys(self.resource_group, storage_name)
                storage_keys = {v.key_name: v.value for v in storage_keys.keys}

                if storage_keys:
                    os.environ['AZURE_STORAGE_KEY']=  storage_keys['key1']
                    os.environ['AZURE_STORAGE_ACCOUNT'] = storage_name
                    run("az storage container create -n {}".format("imagesversion"))


            else:
                logs = "### Please update your azure credentials under culsters.ini or to environment variables ###, "
                self.logger.error(logs)
                raise RuntimeError(logs)

        if not self.attributes['image']:
            self.logger.error("Image name {} is not a valid".format(self.attributes['image']))
            sys.exit(1)


        if self.task == "build" or self.task == "push" :
            run("az login -u {} -p {} --tenant {} --service-principal".format(os.environ['AZURE_CLIENT_ID'], os.environ['AZURE_CLIENT_SECRET'],
                 os.environ['AZURE_TENANT_ID']))
            run("az acr login --name {}acr{}".format(self.resource_group_prefix,self.datacenter))
            #self._docker_login()
            self.attributes['version'] = self._get_next_version()

            self.attributes['fqdi'] = "{registry}/{user}/{image}:{version}".format(
                registry=self.app_docker_registry,
                user=self.attributes['user'],
                image=self.attributes['image'],
                version=self.attributes['version']
            )
            self.version_manager = VersionManager(**self.__dict__)

    def current_version(self):
        """
        Return the current version of image for build or deploy or push
        :return:
        """
        return str(self._get_version())

    def version(self):
        return self.attributes['version']


    def build(self):
        """
        Build docker image with FQDI of datacenter, user, image and version
        :return:
        """
        try:
            currentimagedic = self.version_manager.get_latest_image_dict()
            self.attributes['currentimagedic'] = currentimagedic

            with open('VERSION', 'w') as f:
                f.write(self.attributes['version'])
            with open('COMMIT', 'w') as f:
                f.write(self.attributes['commit'])

            run("docker build --file {dockerfile} --build-arg GIT_COMMIT={commit} --build-arg VERSION={version} --build-arg DATETIME={datetime} --tag {fqdi} .".format(**self.attributes), echo=True)
            imagedic = {}
            imagedic['image'] = self.attributes['image']
            imagedic['version'] = self.attributes['version']
            imagedic['branch'] = self._get_git_branch()
            imagedic['commit'] = '{}'.format(self.attributes['commit'])
            imagedic['environment'] = self.attributes['cluster_config']['APP_DATACENTER']
            imagedic['build_hostname'] = socket.gethostname()
            imagedic['build_ip_address'] = self._get_ip_address()

            currentimagedic.update(imagedic)

            self.version_manager.update_images_yaml(**currentimagedic)
            self.logger.info("build image completed for: {}".format(self.attributes['fqdi']))
        except Exception as e:
            logs = "Error in bulding docker image, {}".format(e)
            self.logger.error(logs)
            raise RuntimeError(logs)

    def push(self):
        """
        Pushes docker image to registry
        :return:
        """
        try:
            localimagedic = self.version_manager.get_latest_image_dict()
            v = localimagedic['version']

            if self.attributes.get('flatten', False):
                cmd = "docker-squash -t {fqdi} {fqdi}".format(**self.attributes)
                run(cmd, echo=True)

            run("docker push {fqdi}".format(**self.attributes), echo=True)

            currentimagedic = self.version_manager.get_latest_image_dict(datacenter=self.datacenter)

            currentimagedic['image'] = self.attributes['image']
            currentimagedic['version'] = localimagedic['version']
            currentimagedic['branch'] = localimagedic['branch']
            currentimagedic['commit'] = localimagedic['commit']
            currentimagedic['environment'] = self.attributes['cluster_config']['APP_DATACENTER']
            currentimagedic['build_hostname'] = localimagedic['build_hostname']
            currentimagedic['build_ip_address'] = localimagedic['build_ip_address']

            self.version_manager.update_images_yaml(datacenter=self.datacenter, **currentimagedic)
        except Exception as e:
            logs = "Error in pushing docker image, {}".format(e)
            self.logger.error(logs)
            raise RuntimeError(logs)

    def _get_utcnow(self):
        """
        Return UTC time
        :return:
        """
        fmt = "%Y-%m-%dT%H-%M-%S.%f%Z"
        now_utc = datetime.now(timezone('UTC'))
        return now_utc.strftime(fmt)

    def _get_ip_address(self):
        """
        Returns IP address of host
        :return:
        """
        try:
            return '{}'.format(socket.gethostbyname(socket.gethostname()))
        except:
            return 'Not found'


    def getoutput(self, cmd,  log=True):
        while True:
            prev = cmd
            cmd = cmd.format(self)
            if prev == cmd:
                break

        if log:
            self.logger.info(cmd)
        getoutput(cmd)

    def _get_git_commit(self):
        """
        Returns git commit id
        :return:
        """
        git_dir = os.path.join(self.app_main)
        repo = Repo(git_dir)
        try:
            commitid = repo.head.reference.commit.hexsha
            commit = commitid
        except:
            commit = 'Notfound'
        return commit

    def _get_git_branch(self):
        """
        Returns git branch name
        :return:
        """
        git_dir = os.path.join(self.app_main)
        repo = Repo(git_dir)
        try:
            branch = repo.active_branch
            branch = branch.name
        except:
            branch = 'Not found'
        return branch

    def _get_version(self):
        """
        Returns image version of docker
        :return:
        """
        tags = self._get_tags()
        if tags is None:
            return None
        else:
            return sorted([Version(v) for v in tags])[-1]

    def getoutput(self, cmd, log=True):
        if log:
            self.logger.info(cmd)
        return getoutput(cmd)

    def _get_tags(self):
        """
        Returns tags of docker image
        :return:
        """
        if self.attributes['registry_version'] == 'v1':
            return self._get_tags_v1()
        else:
            return self._get_tags_v2()


    def _docker_login(self):
        """
        Logins for docker registry respective to datacenter
        :return:
        """
        try:

            resource_group="{resourcegroup}-{datacenter}".format(resourcegroup=self.resource_group_prefix,datacenter=self.datacenter)
            registry_name="{resourcegroup}acr{datacenter}".format(resourcegroup=self.resource_group_prefix,datacenter=self.datacenter)
            registries = self.client.registries
            registry = registries.get(resource_group, registry_name)

            if registry.admin_user_enabled:
                cred = registries.list_credentials(resource_group, registry_name)
                acr_login("{}.azurecr.io".format(registry_name),resource_group,cred.username,cred.passwords[0].value)
                self.logger.info("Docker logged in with ACR Credentials")
            else:
                self.logger.error("ACR Not enable with admin access, please enable it")
        except Exception as err:
            self.logger.error("Error logging into docker using acr credentials: {0}.".format(err))

    def _get_tags_v2(self):
        """
        Returns docker tags version of docker container, reads the tags from docker registry respective to datacenter and image name
        :return:
        """
        try:

            resource_group="{resourcegroup}-{datacenter}".format(resourcegroup=self.resource_group_prefix,datacenter=self.datacenter)
            registry_name="{resourcegroup}acr{datacenter}".format(resourcegroup=self.resource_group_prefix,datacenter=self.datacenter)
            registries=self.client.registries
            registry = registries.get(resource_group, registry_name)
            repository="{datacenter}/{image}".format(datacenter=self.datacenter,image=self.attributes['image'])

            if registry.admin_user_enabled:
                cred = registries.list_credentials(resource_group, registry_name)
                try:
                    response = self._obtain_data_from_registry("{}.azurecr.io".format(registry_name),
                                                               "/v2/_catalog", cred.username,
                                                               cred.passwords[0].value)
                    repositories_list = response["repositories"]
                    if not "{}".format(repository) in repositories_list:
                        self.logger.error("Requested image: {} not exist in the registry: {}".format(repository,"{}.azurecr.io".format(registry_name)))
                        if self.task == "build" or self.task == "push":
                            return None
                        else:
                            sys.exit(1)
                    else:
                        self.logger.info("Requested image: {} exist in the registry: {}".format(repository,
                                                                                                "{}.azurecr.io".format(
                                                                                                    registry_name)))
                        response= self._obtain_data_from_registry("{}.azurecr.io".format(registry_name),
                                                                   "/v2/{}/tags/list".format(repository), cred.username,
                                                                   cred.passwords[0].value)
                        response= response["tags"]
                        self.logger.info("ACR Image versions:{}".format(response))
                except Exception as err:
                    self.logger.error("Error getting image details from repo: {0}.".format(err))
            else:
                self.logger.error("ACR Not enable with admin access, please enable it")
            return response
        except Exception as err:
            self.logger.error("Error getting image version details from repo: {0}.".format(err))
            return None
        return response

    def _basic_auth_str(self,username, password):
        return 'Basic ' + to_native_string(
            b64encode(('%s:%s' % (username, password)).encode('latin1')).strip()
        )

    def _headers(self,username, password):
        auth = self._basic_auth_str(username, password)
        return {'Authorization': auth}

    def _obtain_data_from_registry(self,login_server,
                                   path,
                                   username,
                                   password):
        try:
            registryEndpoint = 'https://' + login_server
            self.logger.info("Connecting to ACR: {}".format(registryEndpoint + path))
            response = requests.get(
                registryEndpoint + path,
                headers=self._headers(username, password)
            )

            if response.status_code == 200:
                result = response.json()
                return result
            else:
                self.logger.exception("Error getting image detail from acr")
        except Exception as err:
            self.logger.error("Error getting image detail from repo: {0}.".format(err))
            return None

    def _get_next_version(self):
        """
        Returns next version for the docker to be build
        :return:
        """
        v = self._get_version()
        if not v:
            return '0.0.1'
        else:
            return self._get_local_next_version(v)

    def _get_local_next_version(self, v):
        """
        Return local docker version incase the version details not exist in docker registry
        :param v:
        :return:
        """
        try:

            base_url= "unix:///var/run/docker.sock"

            client = Client(base_url=base_url)
            images = client.images()
            found = False
            v.patch += 1

            docker_registry = "{registry}/{user}/{image}:{v}".format(
                v=str(v),
                registry=self.app_docker_registry,
                user=self.attributes['user'],
                image=self.attributes['image']
            )

            for image in images:
                if docker_registry in image['RepoTags']:
                    found = True

            if found:
                return str(v)
            else:
                if (self.task == "push" or self.task == "deploy") or self.attributes['deploy']:
                    v.patch -= 1
                    return str(v)
                else:
                    return str(v)
        except:
            self.logger.error("Is docker running on localhost:2375?")
            print_exc()
            return str(v)

