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
from ..log import logging

class Image(object):
    def __init__(self, **kwargs):
        self.attributes = {
            'user': 'dev',
            'dockerfile_ext': None,
            'registry_version': 'v2',
            'deploy': False
        }
        self.logger = logging.get_joara_logger(self.__class__.__name__)
        self.attributes.update(kwargs)
        if 'dockerfile_ext' in kwargs:
            self.attributes['dockerfile'] = "Dockerfile.{}".format(kwargs['dockerfile_ext'])
        else:
            self.attributes['dockerfile'] = "Dockerfile"

        self.task =self.attributes['task']
        self.attributes['joara_app_main'] = self.attributes['cluster_config']['JOARA_APP_MAIN']
        self.attributes['user'] = self.attributes['cluster_config']['JOARA_APP_DOCKER_USER']
        self.joara_app_main = self.attributes['joara_app_main']
        self.attributes['datacenter'] = self.attributes['cluster_config']['JOARA_APP_DATACENTER']
        self.docker_user = self.attributes['cluster_config']['JOARA_APP_DOCKER_USER']
        self.docker_registry = self.attributes['cluster_config']['JOARA_APP_DOCKER_REGISTRY']
        self.resource_group_prefix = self.attributes['cluster_config']['RESOURCE_GROUP_PREFIX']
        self.datacenter = self.attributes['datacenter']
        self.attributes['commit'] = self._get_git_commit()

        try:
            if ( 'AZURE_CLIENT_ID' in os.environ and 'AZURE_CLIENT_SECRET' in os.environ and 'AZURE_TENANT_ID' in os.environ and 'AZURE_SUBSCRIPTION_ID' in os.environ) :
                self.credentials = ServicePrincipalCredentials(
                    client_id=os.environ['AZURE_CLIENT_ID'],
                    secret=os.environ['AZURE_CLIENT_SECRET'],
                    tenant=os.environ['AZURE_TENANT_ID']
                )
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
                logs = "### Please update your azure credentials under culsters.ini or to environment variables ###, {}".format(e)
                self.logger.error(logs)
                raise RuntimeError(logs)

        if ('AZURE_CLIENT_ID' in os.environ and 'AZURE_CLIENT_SECRET' in os.environ and 'AZURE_TENANT_ID' in os.environ and 'AZURE_SUBSCRIPTION_ID' in os.environ):
            storage_client = StorageManagementClient(self.credentials, os.environ['AZURE_SUBSCRIPTION_ID'])
            resource_group = "{}-{}".format(self.resource_group_prefix, self.datacenter)
            storage_name = "{}{}".format(self.resource_group_prefix, self.datacenter)
            storage_keys = storage_client.storage_accounts.list_keys(resource_group, storage_name)
            storage_keys = {v.key_name: v.value for v in storage_keys.keys}

            if storage_keys:
                os.environ['AZURE_STORAGE_KEY']=  storage_keys['key1']
                os.environ['AZURE_STORAGE_ACCOUNT'] = storage_name
                run("az storage container create -n {}".format("imagesversion"))

            run("az login -u {} -p {} --tenant {} --service-principal".format(os.environ['AZURE_CLIENT_ID'], os.environ['AZURE_CLIENT_SECRET'],
                                                                              os.environ['AZURE_TENANT_ID']))
            run("az acr login --name joaraacr{}".format(self.datacenter))
        else:
            logs = "### Please update your azure credentials under culsters.ini or to environment variables ###, "
            self.logger.error(logs)
            raise RuntimeError(logs)

        if self.task == "build" or self.task == "push" :
            self.attributes['version'] = self._get_next_version()

            self.attributes['fqdi'] = "{registry}/{user}/{image}:{version}".format(
                registry=self.attributes['cluster_config'][
                    'JOARA_APP_DOCKER_REGISTRY'],
                user=self.attributes['user'],
                image=self.attributes['image'],
                version=self.attributes['version']
            )
            self.version_manager = VersionManager(**self.__dict__)

    def current_version(self):
        return str(self._get_version())

    def version(self):
        return self.attributes['version']


    def build(self):
        currentimagedic = self.version_manager.get_latest_image_dict()
        self.attributes['currentimagedic'] = currentimagedic

        with open('VERSION', 'w') as f:
            f.write(self.attributes['version'])
        with open('COMMIT', 'w') as f:
            f.write(self.attributes['commit'])

        run("docker build --file {dockerfile} --tag {fqdi} .".format(**
                                                                     self.attributes), echo=True)
        imagedic = {}
        imagedic['image'] = self.attributes['image']
        imagedic['version'] = self.attributes['version']
        imagedic['branch'] = self._get_git_branch()
        imagedic['commit'] = '{}'.format(self.attributes['commit'])
        imagedic['environment'] = self.attributes['cluster_config']['JOARA_APP_DATACENTER']
        imagedic['build_hostname'] = socket.gethostname()
        imagedic['build_ip_address'] = self._get_ip_address()

        currentimagedic.update(imagedic)

        self.version_manager.update_images_yaml(**currentimagedic)
        self.logger.info("build image completed for: {}".format(self.attributes['fqdi']))

    def push(self):
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
        currentimagedic['environment'] = self.attributes['cluster_config']['JOARA_APP_DATACENTER']
        currentimagedic['build_hostname'] = localimagedic['build_hostname']
        currentimagedic['build_ip_address'] = localimagedic['build_ip_address']

        self.version_manager.update_images_yaml(datacenter=self.datacenter, **currentimagedic)



    def _get_ip_address(self):
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
        git_dir = os.path.join(self.joara_app_main)
        repo = Repo(git_dir)
        try:
            commitid = repo.head.reference.commit.hexsha
            commit = commitid
        except:
            commit = 'Not found'
        return commit

    def _get_git_branch(self):
        git_dir = os.path.join(self.joara_app_main)
        repo = Repo(git_dir)
        try:
            branch = repo.active_branch
            branch = branch.name
        except:
            branch = 'Not found'
        return branch

    def _get_version(self):
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
        if self.attributes['registry_version'] == 'v1':
            return self._get_tags_v1()
        else:
            return self._get_tags_v2()

    def _get_tags_v2(self):
        try:
            response = self.getoutput("az acr repository show-tags --name joaraacr{datacenter} --repository {datacenter}/{image}  -o json".format(datacenter=self.attributes['cluster_config']['JOARA_APP_DATACENTER'],image=self.attributes['image']))
            response=json.loads(response)
            return response
        except Exception as err:
            self.logger.error("Error getting image detail from repo: {0}.".format(err))
            return None
        return response

    def _get_next_version(self):
        v = self._get_version()
        if not v:
            return '0.0.1'
        else:
            return self._get_local_next_version(v)

    def _get_local_next_version(self, v):
        try:

            base_url = "unix:/" + \
                       self.attributes['cluster_config']['DOCKER_SOCK']

            client = Client(base_url=base_url)
            images = client.images()
            found = False
            v.patch += 1

            docker_registry = "{registry}/{user}/{image}:{v}".format(
                v=str(v),
                registry=self.attributes['cluster_config'][
                    'JOARA_APP_DOCKER_REGISTRY'],
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

