FROM node:4

RUN mkdir /app
WORKDIR /app

ENV PATH /app/node_modules/.bin:$PATH

ARG GIT_COMMIT
ARG VERSION
ARG DATETIME

LABEL git-commit=$GIT_COMMIT
LABEL version=$VERSION
LABEL datetime=$DATETIME

ADD files/package.json /app
RUN npm install

COPY files/* /app/

EXPOSE 3000
CMD ["node","test.js"]