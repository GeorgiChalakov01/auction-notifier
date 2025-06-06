FROM alpine:latest

# Install dependencies
RUN apk update && \
    apk upgrade --no-cache && \
    apk add --no-cache python3 py3-pip git

# Set working directory
WORKDIR /app

# Copy application files
COPY . .

# Install dependencies (assuming setup.sh handles virtual environment and pip installs)
RUN chmod +x setup.sh && ./setup.sh

# Expose container port (host mapping is done at runtime)
EXPOSE 5000

# Run application using virtual environment
CMD ["/app/venv/bin/python", "app.py", "--host=0.0.0.0"]
