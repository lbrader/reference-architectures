import os
import os.path
from ..log import logging
import joara_app_provision.invoke_libs.core.keys as keys
import sys
logger = logging.get_joara_logger(__name__)

def validate_ssh_key(ssh_key_file):

    try:
        # file = (ssh_key_file or
        #                   os.path.join(os.path.expanduser('~'), '.ssh', 'id_rsa.pub'))

        file = (os.path.join(os.path.expanduser('~'), '.ssh', 'id_rsa.pub'))
        content = ""
        if os.path.exists(file):
            logger.info('Use existing SSH public key file: %s', file)
            with open(file, 'r') as f:
                content = f.read()

        if not content and not keys.is_valid_ssh_rsa_public_key(content):
            # figure out appropriate file names:
            # 'base_name'(with private keys), and 'base_name.pub'(with public keys)
            public_key_filepath = file
            if public_key_filepath[-4:].lower() == '.pub':
                private_key_filepath = public_key_filepath[:-4]
            else:
                private_key_filepath = public_key_filepath + '.private'
            content = keys.generate_ssh_keys(private_key_filepath, public_key_filepath)
            logger.warning("SSH key files '%s' and '%s' have been generated under ~/.ssh",
                           private_key_filepath, public_key_filepath)
            return True
    except Exception as err:
        logger.error("Error Generating or validating ssh keys at: {0}".format(err))
        sys.exit(1)

def validate_list_of_integers(string):
    # extract comma separated list of integers
    return list(map(int, string.split(',')))


def validate_create_parameters(namespace):
    if not namespace.name:
        raise logger.exception('--name has no value')
    if namespace.dns_name_prefix is not None and not namespace.dns_name_prefix:
        raise logger.exception('--dns-prefix has no value')