#!/usr/bin/env python
from os.path import join, dirname, exists, realpath
from ..python_libs.utils import find_app_main
from configparser import ConfigParser
import sys
import os


def get_clusters_ini_path():
    # directory = os.getcwd().split(os.sep)
    directory = os.path.dirname(os.path.realpath(__file__)).split(os.sep)

    filename = 'clusters.ini'
    path = os.path.join(os.sep.join(directory), filename)

    paths_tried = [path]
    while not os.path.exists(path):
        if len(directory) == 0:
            raise RuntimeError("Failed to find {}, paths tried:\n{}".format(filename, "\n\t".join(paths_tried)))

        directory = directory[:-1]
        path = os.path.join(os.sep.join(directory), filename)
        paths_tried.append(path)
    return path


def read_cluster_config(clusters_ini_path, datacenter):
    if not os.path.exists(clusters_ini_path):
        raise Exception("File 'clusters.ini' does not exist. Looking at path {}".format(clusters_ini_path))

    config = ConfigParser()

    config.read(clusters_ini_path)
    merged_dict = {k.upper(): v for k, v in config.items('common')}
    config_dict = {k.upper(): v for k, v in config.items(datacenter)}
    if 'APP_MAIN' not in os.environ and not 'APP_MAIN' in config_dict:
        config_dict['APP_MAIN'] = find_app_main()
        os.environ['APP_MAIN'] = config_dict['APP_MAIN']

    if 'APP_MAIN' in os.environ:
        config_dict['APP_MAIN'] = os.environ.get('APP_MAIN')

    merged_dict.update(config_dict)

    return merged_dict


def get_cluster_config(datacenter):
    return read_cluster_config(get_clusters_ini_path(), datacenter)


if __name__ == "__main__":
    print(get_cluster_config())
