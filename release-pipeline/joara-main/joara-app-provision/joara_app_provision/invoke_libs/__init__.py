from jinja2 import Environment
from os import environ
from pygments import highlight, lexers, formatters
from json import dumps
import sys
import zipfile
from os import walk
import os


def render(template_string, dictionary):
    """
    recursively render a jinja2 template until all variable are resolved
    """
    environment = Environment()
    environment.filters['jsonify'] = dumps
    previous = template_string
    while True:
        template = environment.from_string(previous)
        output = template.render(dictionary)
        if previous == output:
            return output
        else:
            previous = output


class Struct:
    """
    helper class
    "{0['key']}".format(dict) -> "{0.key}".format(Struct(**dict))
    """
    def __init__(self, **entries):
        self.__dict__.update(entries)


def zipfile(zipfile,folder):
    zf = zipfile.ZipFile("{}.zip".format(zipfile), "w")

    for dirname, subdirs, files in walk(folder):
        zf.write(dirname)
        filepath = os.path.join(dirname, filename)
        for filename in files:
            zf.write(os.path.join(dirname, filename))
    zf.close()
    return filepath