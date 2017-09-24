FROM node:4

RUN mkdir /app
WORKDIR /app

ENV PATH /app/node_modules/.bin:$PATH

ADD files/package.json /app
RUN npm install

COPY files/* /app/

EXPOSE 3000
CMD ["node","test.js"]