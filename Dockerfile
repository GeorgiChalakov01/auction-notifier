FROM alpine:latest

# Install dependencies
RUN apk update && \
    apk upgrade --no-cache && \
    apk add --no-cache python3 py3-pip git cronie

# Set working directory
WORKDIR /app

# Copy application files
COPY . .

# Install dependencies
RUN chmod +x setup.sh && ./setup.sh

# Set up cron
RUN chmod +x setup-cron.sh

# Expose container port
EXPOSE 5000

# Run application and cron
CMD ["sh", "-c", "./setup-cron.sh && /app/venv/bin/python app.py --host=0.0.0.0"]
