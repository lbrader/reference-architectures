from __future__ import absolute_import, print_function, division
import os
import sys
import subprocess


def find_app_main():
    """Find the path to the joara-app-main folder

    Looks for the folder along the path to the current working directory.
    Raises exception if the folder can not be found

    :return: Path to the joara-app-main folder
    """
    current_path = os.getcwd().split(os.sep)
    for i in range(len(current_path), 0, -1):
        path = os.sep.join(current_path[0:i])
        if os.path.exists(os.path.join(path, 'clusters.ini')):
            return path

    raise RuntimeError(
        "Could not find the app-main directory, please re-run this command in that directory."
        "CWD: " + os.getcwd()
    )
