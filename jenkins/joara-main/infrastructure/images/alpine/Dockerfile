FROM frolvlad/alpine-glibc:alpine-3.4

COPY VERSION /
COPY COMMIT  /

ENV SHELL /bin/bash
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

RUN apk --update add \
    bash \
    tini

ENTRYPOINT ["/sbin/tini", "--"]
