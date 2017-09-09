from paramiko import client
from scp import SCPClient
import zipfile
from os import walk
import os
import sys
from ..log import logging

class sshclient(object):
    client = None

    def __init__(self, address, username):
        self.logger = logging.get_joara_logger(self.__class__.__name__)
        self.logger.info("### Connecting to server. ###".format(self))
        self.client = client.SSHClient()
        self.client.set_missing_host_key_policy(client.AutoAddPolicy())
        self.client.connect(address, username=username, key_filename='{user}/.ssh/id_rsa'.format(user=os.path.expanduser("~")))

    def sendCommand(self, command):
        if(self.client):
            stdin, stdout, stderr = self.client.exec_command(command)
            while not stdout.channel.exit_status_ready():
                if stdout.channel.recv_ready():
                    alldata = stdout.channel.recv(1024)
                    prevdata = b"1"
                    while prevdata:
                        prevdata = stdout.channel.recv(1024)
                        alldata += prevdata

                    self.logger.info(str(alldata, "utf8"))
                    return str(alldata, "utf8")
        else:
            self.logger.info("### Connection not opened. ###".format(self))

    def copyFile(self,path):
        with SCPClient(self.client.get_transport()) as scp:
            scp.put(path,  "/tmp")

    def zipdir(self,path, ziph):
        for root, dirs, files in os.walk(path):
            for file in files:
                ziph.write(os.path.join(root, file))

    def zip(self,src, dst):
        zf = zipfile.ZipFile("%s.zip" % (dst), "w", zipfile.ZIP_DEFLATED)
        abs_src = os.path.abspath(src)
        for dirname, subdirs, files in os.walk(src):
            for filename in files:
                absname = os.path.abspath(os.path.join(dirname, filename))
                arcname = absname[len(abs_src) + 1:]
                self.logger.debug('zipping {} as {}'.format (os.path.join(dirname, filename),arcname))
                zf.write(absname, arcname)
        zf.close()


