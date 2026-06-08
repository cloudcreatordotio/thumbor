# Copyright (c) 2025-2026 Matthew Williams
# SPDX-License-Identifier: MIT
#
# This file is released under the MIT License.
# See the LICENSE file in the project root for the full license text.

FROM ubuntu:24.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Add deadsnakes PPA for Python 3.11
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update

# Install system dependencies
RUN apt-get install -y \
    # Python 3.11 and related packages
    python3.11 \
    python3.11-dev \
    python3.11-distutils \
    python3.11-venv \
    python3-pip \
    build-essential \
    # Image processing libraries
    libcurl4-openssl-dev \
    libssl-dev \
    libjpeg-dev \
    libjpeg-turbo-progs \
    libpng-dev \
    libwebp-dev \
    libgif-dev \
    libexif-dev \
    libboost-python-dev \
    libboost-system-dev \
    libboost-thread-dev \
    webp \
    # OpenCV dependencies
    libopencv-dev \
    python3-opencv \
    # OpenCV runtime dependencies for RemoteCV
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    # Video processing
    ffmpeg \
    gifsicle \
    # Redis
    redis-server \
    # Nginx with cache purge module
    nginx \
    libnginx-mod-http-cache-purge \
    # Process management
    supervisor \
    # Utilities
    curl \
    wget \
    vim \
    net-tools \
    apache2-utils \
    # envsubst (for rendering nginx config template)
    gettext-base \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN python3.11 -m pip install --break-system-packages --ignore-installed pip setuptools wheel

# Install Python packages
COPY requirements.txt /tmp/requirements.txt
RUN python3.11 -m pip install --break-system-packages --no-cache-dir --ignore-installed -r /tmp/requirements.txt

# Create application directories
RUN mkdir -p /app/thumbor \
    && mkdir -p /app/logs \
    && mkdir -p /data/thumbor/storage \
    && mkdir -p /data/thumbor/result_storage \
    && mkdir -p /data/thumbor/cache \
    && mkdir -p /var/cache/nginx \
    && mkdir -p /var/log/supervisor \
    && mkdir -p /run/nginx

# Copy configuration files
# nginx.conf is rendered from this template at container startup (see startup.sh)
COPY nginx-cache.conf.template /etc/nginx/nginx.conf.template
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY thumbor.conf /app/thumbor/thumbor.conf
COPY request_logger.py /app/thumbor/request_logger.py
COPY remotecv_azure_loader.py /app/thumbor/remotecv_azure_loader.py
COPY azure_blob_loader.py /app/azure_blob_loader.py
COPY startup.sh /app/startup.sh
COPY redis_admin.py /app/redis_admin.py
COPY setup_redis_admin_auth.sh /app/setup_redis_admin_auth.sh

# Make startup script executable
RUN chmod +x /app/startup.sh && chmod +x /app/setup_redis_admin_auth.sh

# Configure Redis for container environment (cache mode - no persistence)
RUN sed -i 's/^bind 127.0.0.1/bind 0.0.0.0/' /etc/redis/redis.conf \
    && sed -i 's/^protected-mode yes/protected-mode no/' /etc/redis/redis.conf \
    && sed -i 's/^# maxmemory <bytes>/maxmemory 512mb/' /etc/redis/redis.conf \
    && sed -i 's/^# maxmemory-policy noeviction/maxmemory-policy allkeys-lru/' /etc/redis/redis.conf \
    && sed -i 's/^dir \/var\/lib\/redis/dir \/data\/redis/' /etc/redis/redis.conf \
    && sed -i 's/^daemonize yes/daemonize no/' /etc/redis/redis.conf \
    && sed -i 's/^save 900 1/#save 900 1/' /etc/redis/redis.conf \
    && sed -i 's/^save 300 10/#save 300 10/' /etc/redis/redis.conf \
    && sed -i 's/^save 60 10000/#save 60 10000/' /etc/redis/redis.conf \
    && echo "save \"\"" >> /etc/redis/redis.conf \
    && sed -i 's/^stop-writes-on-bgsave-error yes/stop-writes-on-bgsave-error no/' /etc/redis/redis.conf

# Create redis data directory
RUN mkdir -p /data/redis && chown redis:redis /data/redis

# Set working directory
WORKDIR /app

# Azure Web App uses PORT environment variable, default to 80
ENV PORT=80

# Expose port (Azure will override this with PORT env var)
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/healthcheck || exit 1

# Start services via startup script
ENTRYPOINT ["/app/startup.sh"]