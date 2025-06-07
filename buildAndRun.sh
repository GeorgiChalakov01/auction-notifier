#!/bin/sh

docker buildx build -t auction-notifier-backend .

docker stop auction-notifier
docker rm auction-notifier

docker run -d --name auction-notifier -p 5000:5000 \
    -e VIRTUAL_HOST=auction.gchalakov.com \
    -e LETSENCRYPT_HOST=auction.gchalakov.com \
    --network net \
    auction-notifier-backend
