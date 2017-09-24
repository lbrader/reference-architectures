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
        self.logger = logging.get_logger(self.__class__.__name__)
        self.datacenter = datacenter

        self.image = kwargs['image']
        self.name = kwargs['name']

        try:
            config.load_kube_config()
            self.apiclient = api_client.ApiClient()
            self.api = core_v1_api.CoreV1Api(self.apiclient)
            self.k8s_beta = client.ExtensionsV1beta1Api()
        except Exception as err:
            self.logger.error("Error loading Kube config, Exception: {} ".format(err))
            sys.exit(1)

        if 'type' in kwargs and kwargs['type'] == "backend":
            self.logger.info("Deploying backend {}".format(self.name))
            self.version = kwargs['version']
            user = kwargs["user"]
        else:
            img = Image(deploy=True, **kwargs)
            self.version = img.current_version()
            user = kwargs["cluster_config"]["APP_DATACENTER"]

        attributes = {
            "datacenter": self.datacenter,
            "version": self.version,
            "user": user,
            "env": {},
            "cpu": "250m",
            "limitscpu": "500m",
            "replicas": kwargs['count'] if int(kwargs['count']) > 1 else self._getreplica(),
            "name": self.name,
            "registry": kwargs["app_docker_registry"],
            "deploy_app": deployment_app,
            "service_app": service_app
        }
        attributes.update(kwargs)
        self.attributes = attributes
        self.replicas = int(self.attributes["replicas"])
        self.deploy_app = render(attributes['deploy_app'], attributes)
        self.service_app = render(attributes['service_app'], attributes)
        self.logger.info("Image processing name:{image}, version:{version}".format(image=self.image,version=self.version))
        self.logger.warn("Image processing name:{image}, version:{version}".format(image=self.image, version=self.version))

    def _getreplica(self):
        count = 1
        try:
            resp = self.k8s_beta.list_namespaced_replica_set(namespace="default")
            for i in resp.items:
                if "app" in i.metadata.labels and i.metadata.labels["app"] == self.name:
                    count = int(i.spec.replicas)
                    self.logger.info("Current replica for image:{image} is {count}".format(image=self.name,count=count))
                    if count > 0:
                        self.logger.info("Deployment already running in datacenter")
                        self.logger.debug("Deployment: {image} already running in datacenter {datacenter} with replica {count} deployed".format(
                            image=self.name, datacenter=self.datacenter, count=count))
                        return count
            return count
        except Exception as err:
            self.logger.exception("Error getting replica details: {}. ".format(err))
            return count

    def _get_running_imageversion(self):
        try:
            resp = self.k8s_beta.list_namespaced_deployment(namespace="default")
            for i in resp.items:
                if i.metadata.name == self.name:
                    deployedimage = i.spec.template.spec.containers[0].image
                    xs = deployedimage.split(':')
                    xs = list(self.flatmap(lambda ys: ys.split('/'), xs))
                    tag = xs.pop()
                    image = xs.pop()
                    self.logger.info("Deployment already running in datacenter")
                    self.logger.debug("Deployment: {image} already running in datacenter {datacenter} with image name {deployedimage} deployed".format(
                            image=self.name, datacenter=self.datacenter, deployedimage=deployedimage))
                    return tag
            return "Not Found"
        except Exception as err:
            self.logger.error("Error getting ruuning details: {}. ".format(err))
            return "Not Found"

    def deploy(self):
        try:
             dep = yaml.load(self.deploy_app)
             self.logger.debug(dep)
             if not self._is_deployment_deployed():
                 resp = self.k8s_beta.create_namespaced_deployment(
                     body=dep, namespace="default")
                 self.logger.info("Deployment created.Image:{image}".format(image=self.name))
                 self.logger.debug("Deployment created. status='{}' ".format(resp.status))
             else:
                 self.logger.info("Deployment {} already exist, so it will patch ".format(self.name))
                 run_version=self._get_running_imageversion()
                 run_replica = int(self._getreplica())
                 self.logger.debug("Deployment compare {run_version}={version} ,{run_replica}={replicas} ".format(run_version=str(run_version).strip(), version=str(self.version).strip(), run_replica=run_replica,replicas=self.replicas))
                 if not "Not Found" in run_version and ( str(run_version).strip() != str(self.version).strip() or  run_replica != self.replicas):
                    self.patch()
                 else:
                     self.logger.info("Deployment {} already exist, with same schema, so patch skipped ".format(self.name))

             if not self._is_service_deployed():
                 srv = yaml.load(self.service_app)
                 self.logger.debug(srv)
                 resp = self.api.create_namespaced_service(body=srv,
                                                      namespace="default")
                 self.logger.info("Service created")
                 self.logger.debug("Service created. status='{}' ".format(resp.status))
             else:
                 self.logger.info("Service {} already exist ".format(self.name))
        except Exception as err:
            self.logger.exception("Error deployment details: {}. ".format(err))
            sys.exit(1)

    def scale(self):
        try:
             dep = yaml.load(self.deploy_app)

             if self._is_deployment_deployed():
                 resp=self.k8s_beta.patch_namespaced_deployment_scale(name=self.name, body=dep, namespace="default")
                 self.logger.info("Scale Deployment created.")
                 self.logger.debug("Scale Deployment created. status='{}' ".format(resp.status))
             else:
                 self.logger.info("Deployment {} not exist ".format(self.name))
        except Exception as err:
            self.logger.error("Error scale details: {}. ".format(err))
            sys.exit(1)

    def delete(self):
        try:
             if self._is_deployment_deployed():
                 resp=self.k8s_beta.delete_collection_namespaced_deployment(namespace="default")
                 #resp = self.k8s_beta.delete_namespaced_deployment(name=self.name,namespace="default")
                 self.logger.info("Delete Deployment created. ")
                 self.logger.debug("Delete Deployment created. status='{}' ".format(resp.status))
             else:
                 self.logger.info("Deployment {} not exist ".format(self.name))

             if self._is_service_deployed():
                 resp = self.api.delete_namespaced_service(name=self.name,namespace="default")
                 self.logger.info("Delete Service created.")
                 self.logger.debug("Delete Service created. status='{}' ".format(resp.status))
             else:
                 self.logger.info("Service {} not exist ".format(self.name))
        except Exception as err:
            self.logger.error("Error delete details: {}. ".format(err))
            sys.exit(1)


    def patch(self):
        try:
             dep = yaml.load(self.deploy_app)
             if self._is_deployment_deployed():
                 resp=self.k8s_beta.patch_namespaced_deployment(name=self.name, body=dep, namespace="default")
                 self.logger.info("Patch Deployment created.")
                 self.logger.debug("Patch Deployment created. status='{}' ".format(resp.status))
             else:
                 self.logger.info("Deployment {} not exist, Please deploy first ".format(self.name))
        except Exception as err:
            self.logger.error("Error patching deployment details: {}. ".format(err))
            return False

    def _is_deployment_deployed(self):
        try:
            resp = self.k8s_beta.list_namespaced_deployment(namespace="default")
            for i in resp.items:
                if i.metadata.name == self.name:
                    self.logger.info("Deployment: {deployment} deployed".format(deployment=self.name))
                    return True
            return False
        except Exception as err:
            self.logger.error("Error getting deployment details: {}. ".format(err))
            return False

    def get(self):
        try:
            resp = self.k8s_beta.list_namespaced_deployment(namespace="default")
            for i in resp.items:
                if i.metadata.name == self.name:
                    self.logger.info("Deployment Details: {deployment}".format(deployment=i))
                    return True

                self.logger.info("Deployment Details: {image} doesn't exist".format(image=self.name))
            return False
        except Exception as err:
            self.logger.error("Error getting deployment details: {}. ".format(err))
            return False

    def getservice(self):
        try:
            resp = self.api.list_namespaced_service(namespace="default")
            self.logger.debug("Service details. status='{}' ".format(resp))
            for i in resp.items:
                if i.metadata.name == self.name:
                    self.logger.info("Service: {service} running @ip: {ip}, @port: {port}".format(service=self.name,ip=i.status.load_balancer.ingress[0].ip,port=i.spec.ports[0].target_port))
                    self.logger.warning("Service: {service} running @ip: {ip}, @port: {port}".format(service=self.name,ip=i.status.load_balancer.ingress[0].ip,port=i.spec.ports[0].target_port))
                    return True
            self.logger.info("No Service details found for image {}, may be the service not deployed ".format(self.name))
            return False
        except Exception as err:
            self.logger.error("Error getting service details: {}. ".format(err))
            return False

    def flatmap(self,f, items):
        return chain.from_iterable(imap(f, items))

    def _is_service_deployed(self):
        try:
            resp = self.api.list_namespaced_service(namespace="default")
            self.logger.debug("Service details. status='{}' ".format(resp))
            for i in resp.items:
                if i.metadata.name == self.name:
                    self.logger.info("Service: {service} running @ip: {ip}".format(service=self.name,ip=i.status.load_balancer.ingress[0].ip))
                    return True
            return False
        except Exception as err:
            self.logger.error("Error getting service details: {}. ".format(err))
            return False


deployment_app_old = """
apiVersion: extensions/v1beta1
kind: Deployment
metadata:
  name: {{ name }}
spec:
  replicas: {{ replicas }}
  template:
    metadata:
      labels:
        name: {{ name }}
    spec:
      containers:
      - image: {{ registry }}/{{ user }}/{{ image }}:{{ version }}
        name: {{ name }}
        imagePullPolicy: Always
        ports:
        - containerPort: {{ port }}
          name: http-server
        env:
          {{ env }}
""".strip()

deployment_app= """
apiVersion: extensions/v1beta1
kind: Deployment
metadata:
  name: {{ name }}
spec:
  replicas: {{ replicas }}
  strategy:
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 1
  minReadySeconds: 5 
  template:
    metadata:
      labels:
        app: {{ name }}
    spec:
      containers:
      - name: {{ name }}
        image: {{ registry }}/{{ user }}/{{ image }}:{{ version }}
        ports:
        - containerPort: {{ port }}
        resources:
          requests:
            cpu: {{ cpu }}
          limits:
            cpu: {{ limitscpu }}
        env:
          {{ env }}
""".strip()

service_app_old = """
apiVersion: v1
kind: Service
metadata:
  name: {{ name }}
  labels:
    name: {{ name }}
spec:
  type: LoadBalancer
  ports:
    - port: 80
      targetPort: {{ port }}
      protocol: TCP
  selector:
    name: {{ name }}
    
""".strip()

service_app = """
apiVersion: v1
kind: Service
metadata:
  name: {{ name }}
spec:
  type: LoadBalancer
  ports:
  - port: 80
    targetPort: {{ port }}
  selector:
    app: {{ name }}
""".strip()