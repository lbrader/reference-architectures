from jinja2 import Environment
from os import environ
from json import dumps
import sys
from os import walk
import os
import socket
import dns.resolver
from ..log import logging

logger = logging.get_logger(__name__)
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


def is_valid_ipv4_address(address):
    try:
        socket.inet_pton(socket.AF_INET, address)
    except AttributeError:  # no inet_pton here, sorry
        try:
            socket.inet_aton(address)
        except socket.error:
            return False
        return address.count('.') == 3
    except socket.error:  # not a valid address
        return False

    return True

def resolvedns(dnshost):
    try:
        logger.info("Checking DNS: {}".format(dnshost))
        answers = dns.resolver.query(dnshost, 'A')
        for rdata in answers:
            if is_valid_ipv4_address(str(rdata)):
                logger.debug("DNS exist: {}".format(str(rdata)))
                return True
        return True
    except Exception as err:
        logger.debug("DNS Error: {}".format(err))
        return False

class Attributes(object):
    def __init__(self, *initial_data, **kwargs):
        for dictionary in initial_data:
            for key in dictionary:
                setattr(self, key, dictionary[key])
        for key in kwargs:
            setattr(self, key, kwargs[key])