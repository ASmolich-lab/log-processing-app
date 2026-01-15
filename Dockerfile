FROM node:18-slim

WORKDIR /app

COPY package.json package-lock.json* ./

RUN npm install

COPY . .

# Clean-up logs
RUN rm -f agent/inputs/events.log splitter/events.log target/events.log events.log

# Unzip the log file. Compressed to avoid storing large files in the repo.
RUN if [ -f agent/inputs/large_1M_events.log.gz ]; then \
    gunzip -f agent/inputs/large_1M_events.log.gz; \
    fi