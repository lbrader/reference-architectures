from setuptools import setup

setup(
    name="joara-app-provision",
    version="0.0.1",
    maintainer="Krishna",
    maintainer_email="krishnas@snapanalytx.com",
    description="Provides a `joaraapp` command that manages deployment of the various parts of the joara APP cluster",
    packages=[
        'joara_app_provision',
        'joara_app_provision.commands',
        'joara_app_provision.env',
        'joara_app_provision.python_libs',
        'joara_app_provision.log',
        'joara_app_provision.invoke_libs',
    ],
    entry_points={
        'console_scripts': [
            'joara=joara_app_provision.command_joaraapp:main',
        ]
    },
    install_requires=[
        'docker-py',
        'invoke',
        'pytz',
        'GitPython',
        'colorama',
        'azure-cli',
        'pyopenssl',
        'pyasn1',
        'httplib2',
        'semantic_version',
        'ipdb',
        'ndg-httpsclient',
        'pygments',
        'requests',
        'jinja2',
        'kubernetes',
        'websocket-client===0.40.0',
        'paramiko',
        'PyGithub',
        'dnspython',
        'smtplib'


    ]
)
