import os
from distutils.util import strtobool
import yaml
from shutil import copyfile
from invoke import run
import sys
from ..log import logging



class VersionManager(object):
    """
    Manages version of the docker image respective to datacenter in an yml file
    """
    def __init__(self, **kwargs):
        self.__dict__ = kwargs
        self.logger = logging.get_logger(self.__class__.__name__)


    def get_latest_image_dict(self, datacenter='local'):
        """
        Returns the current details of image in dict by reading the yml file from storage
        :param datacenter: name of datacenter
        :return: dict with image meta details
        """
        ifolderpath = os.path.join(self.app_main, 'infrastructure', 'images_version')
        fnamelatest = os.path.join(ifolderpath, 'images_{}.yml'.format(datacenter))
        try:
            if datacenter != 'local':
                cmd = "az storage blob download --container-name imagesversion --file {}/images_{datacenter}.yml --name images_{datacenter}.yml".format(
                    ifolderpath, datacenter=self.datacenter)
                run(cmd, echo=True)
        except Exception as err:
            self.logger.error("ERROR: Requested image: {image} details are not exist in storage image inventory, {error}".format(
                image=self.attributes['image'],error=err))
            pass

        with open(fnamelatest) as f:
            imagedict = yaml.load(f)

        if self.attributes['deploy'] == True and self.attributes['image'] not in imagedict:
            raise RuntimeError(self.logger.error( "ERROR: Requested image: {} details are not exist in image inventory \n "
                "please add the image details to all images_{}.yml file under provisioning/images_version".format(
                    self.attributes['image'], datacenter))
               )

        if imagedict and self.attributes['image'] in imagedict:
            imagedict = imagedict[self.attributes['image']]
            return imagedict
        else:
            dic = {}
            dicitem = {}
            dicitem["branch"] = "{{ branch }}"
            dicitem["build_hostname"] = "{{ build_hostname }}"
            dicitem["build_ip_address"] = "{{ build_ip_address }}"
            dicitem["commit"] = "{{ commit }}"
            dicitem["environment"] = "{{ environment }}"
            dicitem["image"] = self.attributes['image']
            dicitem["registry"] =  self.app_docker_registry
            dicitem["user"] = self.attributes['user']
            dicitem["version"] = "{{ version }}"
            dic[self.attributes['image']] = dict()
            dic[self.attributes['image']].update(dicitem)
            with   open(fnamelatest, 'a') as f:
                yaml.dump(dic, f, default_flow_style=False)
            return dicitem


    def update_images_yaml(self, datacenter='local', **kwdic):
        """
        Updates the image meta information in yml file and uploads to stroage
        :param datacenter:
        :param kwdic:
        :return:
        """
        fnamelatest = os.path.join(self.app_main, 'infrastructure', 'images_version',
                                   'images_{}.yml'.format(datacenter))
        with open(fnamelatest) as f:
            newdct = yaml.load(f)

        if not newdct:
            newdct = {}

        newdct[kwdic['image']] = kwdic

        with open(fnamelatest, "w") as f:
            yaml.dump(newdct, f, default_flow_style=False)

        if datacenter != 'local':
            fnamelatest = os.path.join(self.app_main, 'infrastructure',  'images_version')
            cmd = "az storage blob upload -f {}/images_{datacenter}.yml -c imagesversion -n images_{datacenter}.yml".format(
                fnamelatest, datacenter=datacenter)
            run(cmd, echo=True)
            self.logger.info("Update to images version yml completed for datacenter {datacenter}".format(datacenter=datacenter))

    def get_images_list(self, datacenter='local'):
        """
        Return the list of images in datacenter
        :param datacenter:
        :return: list of images and meta details
        """
        try:
            ifolderpath = os.path.join(self.app_main, 'infrastructure', 'images_version')
            fnamelatest = os.path.join(ifolderpath, 'images_{}.yml'.format(datacenter))
            with open(fnamelatest) as f:
                dict = yaml.load(f)
            if dict:
                for key in dict.keys():
                    yield key
        except Exception as err:
            self.logger.exception(
                "ERROR: Unable to get image details, {error}".format(error=err))
            sys.exit(1)

    def get_latest_image_sync_dict(self, image, datacenter='local'):
        """
        Returns the image meta details for an image
        :param image: image name
        :param datacenter:
        :return: dict with images meta details
        """
        ifolderpath = os.path.join(self.app_main, 'infrastructure', 'images_version')
        self.fnamelatest = os.path.join(ifolderpath, 'images_{}.yml'.format(datacenter))
        with open(self.fnamelatest) as f:
            imagedict = yaml.load(f)
        try:
            if imagedict and image in imagedict:
                imgdic = imagedict[image]
                return imgdic
            else:
                dic = {}
                dicitem = {}
                dicitem["branch"] = "{{ branch }}"
                dicitem["build_hostname"] = "{{ build_hostname }}"
                dicitem["build_ip_address"] = "{{ build_ip_address }}"
                dicitem["commit"] = "{{ commit }}"
                dicitem["environment"] = "{{ environment }}"
                dicitem["image"] = self.attributes['image']
                dicitem["registry"] = self.app_docker_registry
                dicitem["user"] = self.attributes['user']
                dicitem["version"] = "{{ version }}"
                dic[image] = dict()
                dic[image].update(dicitem)
                with   open(self.fnamelatest, 'a') as f:
                    yaml.dump(dic, f, default_flow_style=False)
                return dicitem
        except Exception as err:
            self.logger.error('ERROR: Image {} not exist, Exception: {}'.format(image,err))
            return {}
