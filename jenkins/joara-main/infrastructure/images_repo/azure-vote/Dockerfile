FROM    tiangolo/uwsgi-nginx-flask:python3.6

RUN     pip install redis
 
ADD     /azure-vote /app

ARG GIT_COMMIT
ARG VERSION
ARG DATETIME

LABEL git-commit=$GIT_COMMIT
LABEL version=$VERSION
LABEL datetime=$DATETIME