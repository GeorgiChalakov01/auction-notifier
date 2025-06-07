#!/bin/sh

# Create crontab file
echo "0 8 * * * /app/venv/bin/python /app/scraper.py >> /app/scraper.log 2>&1" > /etc/crontab

# Apply cron job
crond -b -L /app/cron.log

echo "Cron job set up successfully"
