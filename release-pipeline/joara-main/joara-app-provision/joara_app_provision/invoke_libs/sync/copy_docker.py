from multiprocessing import Process, Manager
import yaml
import os
import sys
import json
from ...invoke_libs.version_manager import VersionManager
from ...invoke_libs import Attributes
import traceback
from azure.mgmt.storage import StorageManagementClient
from azure.common.credentials import ServicePrincipalCredentials
from invoke import run
from ...python_libs.utils import find_app_main
from ...commands import from_base
import os
from kubernetes import client, config
from kubernetes.client import api_client
from kubernetes.client.apis import core_v1_api
import pickle
from ...log import logging


class CopyDocker(object):
    """
    Init class for copying docker from one datacenter to other datacenter and deploys to Kube
    """
    def __init__(self, datancenter, **kwargs):
        self.attributes = {
            'user': 'dev',
            'registry_version': 'v2'
        }
        self.logger = logging.get_logger(self.__class__.__name__)
        self.attributes.update(kwargs)
        self.attributes['user'] = self.attributes['cluster_config']['APP_DATACENTER']
        self.app_main = self.attributes['cluster_config']['APP_MAIN']
        self.datacenter = self.attributes['cluster_config']['APP_DATACENTER']
        self.from_datacenter = self.attributes["from_datacenter"]
        self.registry = kwargs["app_docker_registry"]
        self.resource_group_prefix = self.attributes['cluster_config']['RESOURCE_GROUP_PREFIX']
        self.resource_group = "{}-{}".format(self.resource_group_prefix, self.datacenter)

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
                self.logger.exception(logs)
                raise RuntimeError(logs)

        self.credentials = ServicePrincipalCredentials(
            client_id=self.client_id,
            secret=self.client_secret,
            tenant=self.tenant_id
        )

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

        run("az acr login --name {}acr{}".format(self.resource_group_prefix,self.from_datacenter))


        try:
            config.load_kube_config()
            self.apiclient = api_client.ApiClient()
            self.api = core_v1_api.CoreV1Api(self.apiclient)
            self.k8s_beta = client.ExtensionsV1beta1Api()
        except Exception as err:
            self.logger.error()("Error copying Kube config, Exception: {}".format(err))
            sys.exit(1)

        self.version_manager = VersionManager(**self.__dict__)


    def cd(self, directory, fg='green'):
        while True:
            prev = directory
            directory = directory.format(self)
            if prev == directory:
                break
        self.logger.info('cd {}'.format(directory))
        os.chdir(directory)

    def copyfromstroage(self, datacenter='local'):
        """
        Copies images version yml from stroage to local
        :param datacenter: name of datacenter
        :return:
        """
        ifolderpath = os.path.join(self.app_main, 'infrastructure', 'images_version')
        try:
            if datacenter != 'local' :
                storage_client = StorageManagementClient(self.credentials, os.environ['AZURE_SUBSCRIPTION_ID'])
                resource_group = "{}-{}".format(self.resource_group_prefix, datacenter)
                storage_name = "{}{}".format(self.resource_group_prefix, datacenter)
                storage_keys = storage_client.storage_accounts.list_keys(resource_group, storage_name)
                storage_keys = {v.key_name: v.value for v in storage_keys.keys}
                if storage_keys:
                    self.logger.info("Got storage keys")
                    os.environ['AZURE_STORAGE_KEY'] = storage_keys['key1']
                    os.environ['AZURE_STORAGE_ACCOUNT'] = storage_name
                else:
                    self.logger.info("Unable to get storage keys")
                    sys.exit(1)
                cmd = "az storage blob download --container-name imagesversion --file {}/images_{datacenter}.yml --name images_{datacenter}.yml".format(
                    ifolderpath, datacenter=datacenter)
                run(cmd, echo=True)
        except Exception as err:
            self.logger.error(
                "ERROR: unable to down image from storage inventory, {error}".format(error=err))
            pass

    def copy(self):
        """
        Copy all docker which is different in version from one datacenter to other
        :return:
        """
        # procs = 3

        self.copyfromstroage(self.from_datacenter)
        self.copyfromstroage(self.datacenter)
        list_image = self.version_manager.get_images_list(datacenter=self.from_datacenter)

        # Create a list of jobs and then iterate through
        # the number of processes appending each process to
        # the job list
        manager = Manager()
        return_dict = manager.dict()
        jobs = []
        if self.datacenter != self.from_datacenter:
            # for i in range(0, procs):
            for image_name in list_image:

                image_dic = self.version_manager.get_latest_image_sync_dict(image_name, datacenter=self.from_datacenter)
                current_dc_image_dic = self.version_manager.get_latest_image_sync_dict(image_name,datacenter=self.datacenter)

                name = image_dic['image']
                from_registry = image_dic['registry']
                from_user = image_dic['user']
                tag = image_dic['version']
                user = self.attributes['user']
                if 'not exist' not in tag  and (from_registry != self.registry or user != from_user):
                    if not current_dc_image_dic or (current_dc_image_dic['version'] != image_dic['version']):
                        process = Process(target=self.syncdocker,
                                          args=(from_registry, from_user, name, tag, return_dict))
                        jobs.append(process)
                    else:

                        self.logger.info( "image {} version are already in sync".format(image_name))

        if len(jobs) == 0:
            self.logger.info( "No images exist to copy from datacenter: {} to  datacenter: {}".format( self.from_datacenter,self.datacenter))

        else:
            self.logger.info("Total no. of images to copy from datacenter: {} to  datacenter: {} is {}".format(self.from_datacenter, self.datacenter,len(jobs)))

            for j in jobs:
                j.start()

            # Ensure all of the processes have finished
            for j in jobs:
                j.join()

            if len(return_dict.values()) == len(jobs):

                self.logger.info("Successfully copied images from datacenter: {} to  datacenter: {}".format(self.from_datacenter,self.datacenter))
                self.logger.info("Overall status: {}".format(str(return_dict)))

            else:
                self.logger.info("ERROR: All images are not copied from datacenter: {} to  datacenter: {}, please refer error messages".format(self.from_datacenter,self.datacenter))
                self.logger.info("Overall status: {}".format(str(return_dict)))


    def syncdocker(self, from_registry, from_user, image, version, return_dict):
        """
        Syncs docker version from one docker registry to other docker registry datacenter and deploys to Kube
        :param from_registry: from which docker registry to copy
        :param from_user: dcker registry user
        :param image: name of the image to copy
        :param version: version of image to copy
        :param return_dict: returns the stauts of copy
        :return:
        """
        fqdi = "{registry}/{user}/{image}:{version}".format(
            registry=from_registry,
            user=from_user,
            image=image,
            version=version
        )

        tofqdi = "{registry}/{user}/{image}:{version}".format(
            registry=self.registry,
            user=self.attributes['user'],
            image=image,
            version=version
        )
        self.logger.info("pull image started for: {}".format(fqdi))

        run("docker pull {fqdi}".format(fqdi=fqdi))
        self.logger.info("pull image completed for: {}".format(fqdi))


        run("docker tag {fqdi} {tofqdi}".format(fqdi=fqdi, tofqdi=tofqdi))
        self.logger.info("tag image completed for: {}".format(tofqdi))

        run("az acr login --name {}acr{}".format(self.resource_group_prefix,self.datacenter))
        self.logger.info("push image started for: {}".format(tofqdi))
        run("docker push {tofqdi}".format(tofqdi=tofqdi))

        self.logger.info("push image completed for: {}".format(tofqdi))



        try:
            localimagedic = self.version_manager.get_latest_image_sync_dict(image, datacenter=self.from_datacenter)
            currentimagedic = self.version_manager.get_latest_image_sync_dict(image, datacenter=self.datacenter)

            currentimagedic['image'] = image
            currentimagedic['version'] = localimagedic['version']
            currentimagedic['branch'] = localimagedic['branch']
            currentimagedic['commit'] = localimagedic['commit']
            currentimagedic['environment'] = self.datacenter
            currentimagedic["registry"] = self.registry
            currentimagedic['build_hostname'] = localimagedic['build_hostname']
            currentimagedic['build_ip_address'] = localimagedic['build_ip_address']
            currentimagedic['user'] = self.attributes['user']
            self.version_manager.update_images_yaml(datacenter=self.datacenter, **currentimagedic)
            self.logger.info("sync storage for data datacenter : {} for image: {} completed".format(self.datacenter, image))


        except Exception as err:
            self.logger.error("ERROR: {} : image sync failure for {} ".format(err,image))

        try:
            self.cd(self.app_main)
            self.logger.info("Deploying image: {}".format(tofqdi))
            resp = self.k8s_beta.list_namespaced_replica_set(namespace="default")
            count = 1
            for i in resp.items:
                if i.metadata.name == image:
                    count = int(i.spec.replicas)
                    self.logger.info(
                        "Deployment: {image} already running in datacenter {datacenter} with replica {count} deployed".format(
                            image=self.image, datacenter=self.datacenter, count=count))
            module = os.path.join('infrastructure', 'images', 'run')
            args = Attributes(
                {'task': 'deploy', "count": count, 'datacenter': self.datacenter})
            from_base.provision_images(module, [image], args)
            self.logger.info("Completed deploying image: {}".format(image))

        except Exception as err:
            self.logger.error("ERROR: {} : image deploy failure {} ".format(err,image))
            sys.exit(1)

        self.logger.info('All copy and deploy steps completed for image {}'.format(image))
        return_dict[image] = 'completed'

