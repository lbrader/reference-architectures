from __future__ import absolute_import, print_function
from ..image import Image
from .. import render
import yaml
import os
from kubernetes import client, config
from kubernetes.client import api_client
from kubernetes.client.apis import core_v1_api
from invoke import run
import sys
from itertools import chain
from ...log import logging

try:
    from itertools import imap
except ImportError:
    # Python 3...
    imap=map


class KubeApi(object):

    def __init__(self, datacenter, **kwargs):
        self.logger = logging.get_joara_logger(self.__class__.__name__)
        self.datacenter = datacenter
        self.image = kwargs['image']
        img = Image(deploy=True, **kwargs)
        self.version = img.current_version()
        user= kwargs["cluster_config"]["JOARA_APP_DOCKER_USER"]

        try:

            os.makedirs("{user}/.kube".format(user=os.path.expanduser("~")), exist_ok=True)
            run(
                "scp  -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i {user}/.ssh/id_rsa joaraacs{datacenter}@jora-acs-mgmt-{datacenter}.eastus.cloudapp.azure.com:.kube/config {user}/.kube/config".format(
                    user=os.path.expanduser("~"), datacenter=self.datacenter))
            self.logger.info("Copied kube config from acs remote server")
            config.load_kube_config()
            self.apiclient = api_client.ApiClient()
            self.api = core_v1_api.CoreV1Api(self.apiclient)
            self.k8s_beta = client.ExtensionsV1beta1Api()
        except Exception as err:
            self.logger.error("Error copying Kube config, Exception: {} ".format(err))
            sys.exit(1)

        attributes = {
            "datacenter": self.datacenter,
            "version": self.version,
            "user": user,
            "replicas": kwargs['count'] if int(kwargs['count']) > 1 else self._getreplica(),
            "name": self.image,
            "registry": kwargs["cluster_config"]["JOARA_APP_DOCKER_REGISTRY"],
            "deploy_app": deployment_app,
            "service_app": service_app
        }
        attributes.update(kwargs)
        self.attributes = attributes
        self.replicas= int(self.attributes["replicas"])


        self.deploy_app = render(attributes['deploy_app'], attributes)
        self.service_app = render(attributes['service_app'], attributes)



    def _getreplica(self):
        count = 1
        try:
            resp = self.k8s_beta.list_namespaced_replica_set(namespace="default")
            for i in resp.items:
                if i.metadata.labels["name"] == self.image:
                    count = int(i.spec.replicas)
                    if count > 0:
                        self.logger.info("Deployment already running in datacenter")
                        self.logger.debug("Deployment: {image} already running in datacenter {datacenter} with replica {count} deployed ###".format(
                            image=self.image, datacenter=self.datacenter, count=count))
                        return count
            return count
        except Exception as err:
            self.logger.error("Error getting replica details: {}. ".format(err))
            return count

    def _get_running_imageversion(self):
        try:
            resp = self.k8s_beta.list_namespaced_deployment(namespace="default")
            for i in resp.items:
                if i.metadata.name == self.image:
                    deployedimage = i.spec.template.spec.containers[0].image
                    xs = deployedimage.split(':')
                    xs = list(self.flatmap(lambda ys: ys.split('/'), xs))
                    tag = xs.pop()
                    image = xs.pop()
                    self.logger.info("Deployment already running in datacenter")
                    self.logger.debug("Deployment: {image} already running in datacenter {datacenter} with image name {deployedimage} deployed ###".format(
                            image=self.image, datacenter=self.datacenter, deployedimage=deployedimage))
                    return tag
            return "Not Found"
        except Exception as err:
            self.logger.error("Error getting ruuning details: {}. ".format(err))
            return "Not Found"

    def deploy(self):
        try:
             dep = yaml.load(self.deploy_app)
             if not self._is_deployment_deployed():
                 resp = self.k8s_beta.create_namespaced_deployment(
                     body=dep, namespace="default")
                 self.logger.info("Deployment created.Image:{image}".format(image=self.image))
                 self.logger.debug("Deployment created. status='{}' ".format(resp.status))
             else:
                 self.logger.info("Deployment {} already exist, so it will patch ".format(self.image))
                 run_version=self._get_running_imageversion()
                 run_replica = int(self._getreplica())
                 self.logger.debug("Deployment compare {run_version}={version} ,{run_replica}={replicas} ".format(run_version=run_version.strip(), version=self.version.strip(), run_replica=run_replica,replicas=self.replicas))
                 if not "Not Found" in run_version and ( run_version.strip() != self.version.strip() or  run_replica != self.replicas):
                    self.patch()
                 else:
                     self.logger.info("Deployment {} already exist, with same schema, so patch skipped ".format(self.image))

             if not self._is_service_deployed():
                 srv = yaml.load(self.service_app)

                 resp = self.api.create_namespaced_service(body=srv,
                                                      namespace="default")
                 self.logger.info("Service created")
                 self.logger.debug("Service created. status='{}' ".format(resp.status))
             else:
                 self.logger.info("Service {} already exist ".format(self.image))
        except Exception as err:
            self.logger.error("Error deployment details: {}. ".format(err))
            sys.exit(1)

    def scale(self):
        try:
             dep = yaml.load(self.deploy_app)

             if self._is_deployment_deployed():
                 resp=self.k8s_beta.patch_namespaced_deployment_scale(name=self.image, body=dep, namespace="default")
                 self.logger.info("Scale Deployment created.")
                 self.logger.debug("Scale Deployment created. status='{}' ".format(resp.status))
             else:
                 self.logger.info("Deployment {} not exist ".format(self.image))
        except Exception as err:
            self.logger.error("Error scale details: {}. ".format(err))
            sys.exit(1)

    def delete(self):
        try:
             if self._is_deployment_deployed():
                 resp=self.k8s_beta.delete_collection_namespaced_deployment(namespace="default")
                 self.logger.info("Delete Deployment created. ")
                 self.logger.debug("Delete Deployment created. status='{}' ".format(resp.status))
             else:
                 self.logger.info("Deployment {} not exist ".format(self.image))

             if self._is_service_deployed():
                 resp = self.api.delete_namespaced_service(name=self.image,namespace="default")
                 self.logger.info("Delete Service created.")
                 self.logger.debug("Delete Service created. status='{}' ".format(resp.status))
             else:
                 self.logger.info("Service {} not exist ".format(self.image))
        except Exception as err:
            self.logger.error("Error delete details: {}. ".format(err))
            sys.exit(1)


    def patch(self):
        try:
             dep = yaml.load(self.deploy_app)
             if self._is_deployment_deployed():
                 resp=self.k8s_beta.patch_namespaced_deployment(name=self.image, body=dep, namespace="default")
                 self.logger.info("Patch Deployment created.")
                 self.logger.debug("Patch Deployment created. status='{}' ".format(resp.status))
             else:
                 self.logger.info("Deployment {} not exist, Please deploy first ".format(self.image))
        except Exception as err:
            self.logger.error("Error patching deployment details: {}. ".format(err))
            return False

    def _is_deployment_deployed(self):
        try:
            resp = self.k8s_beta.list_namespaced_deployment(namespace="default")
            for i in resp.items:
                if i.metadata.name == self.image:
                    self.logger.info("Deployment: {deployment} deployed ###".format(deployment=self.image))
                    return True
            return False
        except Exception as err:
            self.logger.error("Error getting deployment details: {}. ".format(err))
            return False

    def get(self):
        try:
            resp = self.k8s_beta.list_namespaced_deployment(namespace="default")
            for i in resp.items:
                if i.metadata.name == self.image:
                    self.logger.info("Deployment Details: {deployment} ###".format(deployment=i))
                    return True

                self.logger.info("Deployment Details: {image} doesn't exist".format(image=self.image))
            return False
        except Exception as err:
            self.logger.error("Error getting deployment details: {}. ".format(err))
            return False

    def flatmap(self,f, items):
        return chain.from_iterable(imap(f, items))

    def _is_service_deployed(self):
        try:
            resp = self.api.list_namespaced_service(namespace="default")
            self.logger.debug("Service details. status='{}' ".format(resp))
            for i in resp.items:
                if i.metadata.name == self.image:
                    self.logger.info("Service: {service} running @ip: {ip} ###".format(service=self.image,ip=i.status.load_balancer.ingress[0].ip))
                    return True
            return False
        except Exception as err:
            self.logger.error("Error getting service details: {}. ".format(err))
            return False


deployment_app = """
apiVersion: extensions/v1beta1
kind: Deployment
metadata:
  name: {{ image }}
spec:
  replicas: {{ replicas }}
  template:
    metadata:
      labels:
        name: {{ image }}
    spec:
      containers:
      - image: {{ registry }}/{{ user }}/{{ image }}:{{ version }}
        name: {{ image }}
        imagePullPolicy: Always
        ports:
        - containerPort: {{ port }}
          name: http-server
          
""".strip()

service_app = """
apiVersion: v1
kind: Service
metadata:
  name: {{ image }}
  labels:
    name: {{ image }}
spec:
  type: LoadBalancer
  ports:
    - port: 80
      targetPort: {{ port }}
      protocol: TCP
  selector:
    name: {{ image }}
    
""".strip()