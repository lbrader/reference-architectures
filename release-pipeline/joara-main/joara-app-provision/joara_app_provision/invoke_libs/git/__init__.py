from __future__ import absolute_import, print_function
from ...log import logging
from github import Github
from .. import render
from git import *
import os
import time
import json, requests, subprocess
from jinja2 import Environment, FileSystemLoader
try:
    from itertools import imap
except ImportError:
    # Python 3...
    imap=map


class GitHubApi(object):
    """
    GitHub API to manage repository and its permissions
    """

    def __init__(self, **kwargs):
        """
        Init Github API
        :param kwargs: param reponame, github details
        """
        self.logger = logging.get_logger(self.__class__.__name__)
        self.token = kwargs['git_hub_token']
        self.orgid = kwargs['cluster_config']['GIT_HUB_ORG_ID']
        self.username = kwargs['cluster_config']['GIT_HUB_USER_NAME']
        self.jenkinshost = kwargs['jenkins_host']
        self.image = kwargs['image']
        self.repo = kwargs['repo']
        self.attributes = {
            "jenkins_hook_url": "http://{host}/github-webhook/".format(host=self.jenkinshost),
            "webhook_hook": webhook_hook,
            "branch_protect": branch_protect
        }
        self.attributes.update(kwargs)
        self.attrs = {}
        self.attrs['git_main_repo_name'] = kwargs['cluster_config']['REPOSITORY_NAME']
        self.attrs['git_org_id'] = kwargs['cluster_config']['GIT_HUB_ORG_ID']
        self.attrs['jenkins_github_credential'] = kwargs['cluster_config']['JENKINS_GITHUB_CREDENTIALS_ID']
        self.attrs['jenkins_azure_credential'] = kwargs['cluster_config']['JENKINS_AZURE_CREDENTIALS_ID']
        self.attrs['notification_email'] = kwargs['cluster_config']['NOTIFICATION_EMAIL']
        self.attrs['git_repo_name'] = self.repo


        self.app_render()

        self.json_webhook_hook = render(self.attributes['webhook_hook'], self.attributes)
        self.json_branch_protect = render(self.attributes['branch_protect'], self.attributes)
        self.github = Github(self.token)

    def app_render(self):
        """
        Replaces templates with github repo details
        :return:
        """
        list_files = ['Jenkinsfile','conf.yml','backend.yml']
        for files in list_files:
            self.app_render_template(self.find(files), files)

    def app_render_template(self, path, file):
        """
        Replaces templates with github repo details
        :param path: Path of template
        :param file: Path of file to replace the template values
        :return:
        """
        if path and os.path.exists(os.path.join(path, file)):
            env = Environment(loader=FileSystemLoader(os.path.join(path)))
            template = env.get_template(file)
            output_from_parsed_template = template.render(self.attrs)
            with open(os.path.join(path, file), "w") as fh:
                fh.write(output_from_parsed_template)

    def find(self,name):
        """
        Finds the file path and returns the path of template file
        :param name:
        :return: file path of template
        """
        for root, dirs, files in os.walk(os.getcwd()):
            if name in files:
                return os.path.join(root)

    def create_repo(self,name, dir=""):
      """
      Creates github repo, adds branch, adds jenkins webhook and protects the branch
      :param name: name of the repo
      :param dir: code directory to be used for repo
      :return: status of git configuration
      """
      try:

        repo_exist = False
        repo_detail = ""

        for gitrepo in self.github.get_organization( self.orgid).get_repos():
            if gitrepo.name == name:
                repo_exist = True
                repo_detail = gitrepo
        if not repo_exist:
            repogit = self.github.get_organization( self.orgid).create_repo(name,private=True)
            time.sleep(60)
            repo_exist = True
            repo_detail = repogit

        branches_list = []
        for branch in repo_detail.get_branches():
            branches_list.append(branch.name)

        base_branches = ['master', 'dev', 'test']

        count = 0
        for branch in base_branches:
            if branch in branches_list:
                count = count + 1

        self.logger.info("No of branches found:{}".format(count))
        if repo_exist and repo_detail and count < 3:
            self.logger.info("Creating Git Repository {}".format(name))
            os.chdir(dir)
            repo = Repo.init(".")
            repo = Repo(".")
            try:
                repo.create_remote("origin", url="https://{username}:{token}@github.com/{orgid}/{name}.git".format(name=name, username=self.username,orgid=self.orgid, token=self.token))
            except GitCommandError as err:
                self.logger.error("Github exception:".format(err))
                pass
            repo.git.add(A=True)
            repo.git.commit(m='base code')

            if str(repo.active_branch) == 'master':
                repo.git.push("origin", "master")

            try:
                repo.git.checkout('HEAD', b="dev")
            except GitCommandError  as err:
                self.logger.error("Github exception:".format(err))
                pass

            repo.git.push("origin", "dev", force=True)

            try:
                repo.git.checkout('HEAD', b="test")
            except GitCommandError as err:
                self.logger.error("Github exception:".format(err))
                pass
            repo.git.push("origin", "test", force=True)
            self.logger.info("Repository {} created successfully".format(name))
        else:
            self.logger.info("Repository {} pre-condition already met".format(name))
      except Exception as err:
            self.logger.exception("Error: Creating github repo got an Exception: {0}".format(err))
            sys.exit(1)



    def delete_repo(self, name):
        """
        Deletes github repo
        :param name: repo name
        :return:
        """
        try:
            self.logger.info("Deleting repository:{}".format(name))
            self.github.get_organization(self.orgid).get_repo(name).delete()
            self.logger.info("Completed deleting repository:{}".format(name))
        except Exception as err:
            self.logger.error('ERROR: Deleting git repo got an Exception: {}'.format(err))

    def create_repo_hook(self, name):
        """
        Creates jenkins webhook for github repo
        :param name: repo name
        :return:
        """
        try:
            self.logger.info("Creating webhook for repository:{}".format(name))
            self.github.get_organization(self.orgid).get_repo(name).create_hook("jenkins", {"jenkins_hook_url": "http://{host}/github-webhook/".format(host=self.jenkinshost)})
            self.logger.info("Completed creating webhook for repository:{}".format(name))
        except Exception as err:
            self.logger.error('ERROR: Creating git hub webhook got an Exception: {}'.format(err))

    def make_api_headers(self):
        """
        Returns a dict representing the headers needed to access the GH API.
        """
        APPLICATION_HEADER_VALUE = 'application/vnd.github.loki-preview+json'

        return {
            'Authorization': 'token {:s}'.format(self.token),
            'Accept': APPLICATION_HEADER_VALUE,
        }

    def make_api_url(self,*args):
        """
        Concatenates *args to make a path to access the GitHub API.
        """
        return '/'.join(('https://api.github.com',*args))

    def set_protection(self,name):
        """
        Sets branch protection for the github repo
        :param name:
        :return:
        """
        try:
            base_branches = ['master', 'dev', 'test']
            for branch in base_branches:
                url = self.make_api_url('repos', self.orgid, name, 'branches', branch, 'protection')
                self.logger.debug(self.json_branch_protect)
                self.logger.info("Protecting branch:{}".format(branch))
                self.logger.info(str(requests.put(url, headers=self.make_api_headers(), json=json.loads(self.json_branch_protect))))
        except Exception as err:
            self.logger.error('ERROR: Setting github branch protection got an Exception: {}'.format(err))

    def create_org_hook(self):
        """
        Creates jenkins webhook for organization
        :return:
        """
        try:
            url = self.make_api_url('orgs', self.orgid, 'hooks')
            self.logger.info("giturl:{}".format(url))
            self.logger.info("jenkinsurl:{}".format(self.attributes["jenkins_hook_url"]))
            self.logger.debug(self.json_webhook_hook)
            self.logger.info(str(requests.post(url, headers=self.make_api_headers(), json=json.loads(self.json_webhook_hook))))
        except Exception as err:
            self.logger.error('ERROR: Creating org web hook got an Exception: {}'.format(err))

branch_protect="""{
  "required_status_checks": null,
  "required_pull_request_reviews": {
  },
  "enforce_admins": false,
  "restrictions": null
}"""

webhook_hook="""{
  "name": "web",
  "active": true,
  "events": [
    "push"
  ],
  "config": {
    "url": "{{ jenkins_hook_url }}",
    "content_type": "json"
  }
}"""