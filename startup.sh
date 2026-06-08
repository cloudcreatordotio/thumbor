#!/bin/bash
# Copyright (c) 2025-2026 Matthew Williams
# SPDX-License-Identifier: MIT
#
# This file is released under the MIT License.
# See the LICENSE file in the project root for the full license text.

set -e

echo "Starting Thumbor container services..."
echo "======================================="

# Azure Web App provides PORT environment variable
export NGINX_PORT=${PORT:-80}
echo "Nginx will listen on port $NGINX_PORT"

# Initialize Redis data directory with proper permissions
echo "Initializing Redis data directory..."
mkdir -p /data/redis
chown -R redis:redis /data/redis
chmod 750 /data/redis

# Initialize Thumbor storage directories
echo "Initializing storage directories..."
mkdir -p /data/thumbor/storage
mkdir -p /data/thumbor/result_storage
mkdir -p /data/thumbor/cache
mkdir -p /var/cache/nginx
mkdir -p /app/logs

# Set permissions
chmod 755 /data/thumbor/storage
chmod 755 /data/thumbor/result_storage
chmod 755 /data/thumbor/cache
chmod 755 /var/cache/nginx
chmod 755 /app/logs

# Note: Redis connectivity will be handled by supervisord
echo "Redis will be managed by supervisord..."

# Environment variable processing
echo "Processing environment variables..."

# Set default values if not provided
export THUMBOR_NUM_PROCESSES=${THUMBOR_NUM_PROCESSES:-4}
export SECURITY_KEY=${SECURITY_KEY:-MY_SECURE_KEY_CHANGE_THIS_IN_PRODUCTION}
export ALLOW_UNSAFE_URL=${ALLOW_UNSAFE_URL:-True}
export AUTO_WEBP=${AUTO_WEBP:-True}
export CORS_ALLOW_ORIGIN=${CORS_ALLOW_ORIGIN:-*}

# Redis configuration
export REDIS_SERVER_HOST=${REDIS_SERVER_HOST:-localhost}
export REDIS_SERVER_PORT=${REDIS_SERVER_PORT:-6379}
export REDIS_SERVER_DB=${REDIS_SERVER_DB:-0}

# Cache configuration
export THUMBOR_PROXY_CACHE_SIZE=${THUMBOR_PROXY_CACHE_SIZE:-100g}
export THUMBOR_PROXY_CACHE_MEMORY_SIZE=${THUMBOR_PROXY_CACHE_MEMORY_SIZE:-1024m}
export THUMBOR_PROXY_CACHE_INACTIVE=${THUMBOR_PROXY_CACHE_INACTIVE:-512m}
export THUMBOR_PROXY_CACHE_DURATION=${THUMBOR_PROXY_CACHE_DURATION:-1m}

# Nginx log destinations (stdout/stderr in production, files in development;
# see ENABLE_FILE_LOGGING handling below for the other services)
if [ "$ENABLE_FILE_LOGGING" = "false" ]; then
    export NGINX_ACCESS_LOG=/dev/stdout
    export NGINX_ERROR_LOG=/dev/stderr
else
    export NGINX_ACCESS_LOG=/app/logs/nginx-access.log
    export NGINX_ERROR_LOG=/app/logs/nginx-error.log
fi

# Render nginx configuration from template.
# The variable list is explicit so nginx's own $variables
# ($remote_addr, $host, ...) are left untouched.
echo "Rendering Nginx configuration from template..."
envsubst '${NGINX_PORT} ${NGINX_ACCESS_LOG} ${NGINX_ERROR_LOG} ${THUMBOR_PROXY_CACHE_SIZE} ${THUMBOR_PROXY_CACHE_MEMORY_SIZE} ${THUMBOR_PROXY_CACHE_INACTIVE} ${THUMBOR_PROXY_CACHE_DURATION}' \
    < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf

# Update Thumbor configuration with environment variables
if [ -n "$SECURITY_KEY" ]; then
    sed -i "s/Config.SECURITY_KEY = .*/Config.SECURITY_KEY = '$SECURITY_KEY'/" /app/thumbor/thumbor.conf
fi

# Configure logging based on ENABLE_FILE_LOGGING environment variable
echo "Configuring logging (ENABLE_FILE_LOGGING=$ENABLE_FILE_LOGGING)..."
if [ "$ENABLE_FILE_LOGGING" = "false" ]; then
    echo "Production mode: Configuring stdout/stderr logging only..."

    # Update supervisord.conf for stdout logging
    # Thumbor workers - already configured for stdout in our previous changes

    # Redis
    sed -i 's|stdout_logfile=/app/logs/redis.log|stdout_logfile=/dev/stdout|' /etc/supervisor/conf.d/supervisord.conf
    sed -i 's|stderr_logfile=/app/logs/redis-error.log|stderr_logfile=/dev/stderr|' /etc/supervisor/conf.d/supervisord.conf
    sed -i 's|stdout_logfile_maxbytes=10MB|stdout_logfile_maxbytes=0|' /etc/supervisor/conf.d/supervisord.conf
    sed -i 's|stderr_logfile_maxbytes=10MB|stderr_logfile_maxbytes=0|' /etc/supervisor/conf.d/supervisord.conf

    # RemoteCV
    sed -i 's|stdout_logfile=/app/logs/remotecv.log|stdout_logfile=/dev/stdout|' /etc/supervisor/conf.d/supervisord.conf
    sed -i 's|stderr_logfile=/app/logs/remotecv-error.log|stderr_logfile=/dev/stderr|' /etc/supervisor/conf.d/supervisord.conf

    # Redis-admin
    sed -i 's|stdout_logfile=/app/logs/redis-admin.log|stdout_logfile=/dev/stdout|' /etc/supervisor/conf.d/supervisord.conf
    sed -i 's|stderr_logfile=/app/logs/redis-admin-error.log|stderr_logfile=/dev/stderr|' /etc/supervisor/conf.d/supervisord.conf

    # Nginx (supervisor logs)
    sed -i 's|stdout_logfile=/app/logs/nginx.log|stdout_logfile=/dev/stdout|' /etc/supervisor/conf.d/supervisord.conf
    sed -i 's|stderr_logfile=/app/logs/nginx-error.log|stderr_logfile=/dev/stderr|' /etc/supervisor/conf.d/supervisord.conf

    # Nginx access and error logs are handled via NGINX_ACCESS_LOG/NGINX_ERROR_LOG
    # in the rendered nginx.conf template above

    echo "Logging configured for stdout/stderr only (no file accumulation)"
else
    echo "Development mode: File logging enabled"

    # Restore file logging for Thumbor workers if they were changed
    sed -i 's|stdout_logfile=/dev/stdout|stdout_logfile=/app/logs/thumbor-%(process_num)d.log|' /etc/supervisor/conf.d/supervisord.conf
    sed -i 's|stderr_logfile=/dev/stderr|stderr_logfile=/app/logs/thumbor-%(process_num)d-error.log|' /etc/supervisor/conf.d/supervisord.conf
    sed -i 's|stdout_logfile_maxbytes=0|stdout_logfile_maxbytes=10MB|' /etc/supervisor/conf.d/supervisord.conf
    sed -i 's|stderr_logfile_maxbytes=0|stderr_logfile_maxbytes=10MB|' /etc/supervisor/conf.d/supervisord.conf
fi

# Test nginx configuration
echo "Testing Nginx configuration..."
nginx -t || {
    echo "Nginx configuration test failed!"
    exit 1
}

# Azure specific: Handle SSH for debugging (port 2222)
if [ "$ENABLE_SSH" = "true" ]; then
    echo "Enabling SSH on port 2222 for Azure debugging..."
    mkdir -p /run/sshd
    /usr/sbin/sshd -D -p 2222 &
fi

# Clean up any stale pid files
rm -f /var/run/supervisord.pid
rm -f /var/run/nginx.pid

# Start supervisord
echo "Starting supervisord..."
echo "======================================="
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf