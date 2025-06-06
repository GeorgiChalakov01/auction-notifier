#!/bin/sh

docker buildx build -t auction-notifier-backend .
docker run -d --name auction-notifier -p 5000:5000 -e VIRTUAL_HOST=auction.gchalakov.com -e LETSENCRYPT_HOST=auction.gchalakov.com --network net -v /home/gchalakov/services/auction-notifier:/app auction-notifier-backend
