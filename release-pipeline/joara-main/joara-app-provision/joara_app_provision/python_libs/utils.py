from __future__ import absolute_import, print_function, division
import os
import sys
import subprocess


def find_joara_app_main():
    path = os.getcwd().split(os.sep)
    if not any("joara-main" in s for s in path):
        raise RuntimeError("Could not find the joara-main directory, please re-run this command in that directory."
                           "CWD: " + os.getcwd())

    matchpath = [s for s in path if "joara-main" in s]

    path = os.sep.join(path[:path.index(str(matchpath[0])) + 1])
    return path
