FROM node:18-slim

WORKDIR /app

COPY package.json package-lock.json* ./

RUN npm install

COPY . .

# Unzip the log file. Compressed to avoid storing large files in the repo.
RUN gunzip -f agent/inputs/large_1M_events.log.gz