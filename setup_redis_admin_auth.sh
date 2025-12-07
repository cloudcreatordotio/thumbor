#!/bin/bash
# Copyright (c) 2025-2026 Matthew Williams
# SPDX-License-Identifier: MIT
#
# This file is released under the MIT License.
# See the LICENSE file in the project root for the full license text.

# Setup script for Redis Admin basic authentication
# This script helps configure HTTP basic auth for the Redis Admin interface

set -e

echo "Redis Admin Basic Authentication Setup"
echo "======================================="

# Check if htpasswd is available
if ! command -v htpasswd &> /dev/null; then
    echo "Installing apache2-utils for htpasswd command..."
    apt-get update && apt-get install -y apache2-utils
fi

# Default values
HTPASSWD_FILE="/etc/nginx/.htpasswd"
DEFAULT_USER="admin"

# Get username
read -p "Enter username (default: $DEFAULT_USER): " USERNAME
USERNAME=${USERNAME:-$DEFAULT_USER}

# Get password
while true; do
    read -s -p "Enter password: " PASSWORD
    echo
    read -s -p "Confirm password: " PASSWORD_CONFIRM
    echo

    if [ "$PASSWORD" = "$PASSWORD_CONFIRM" ]; then
        break
    else
        echo "Passwords don't match. Please try again."
    fi
done

# Create htpasswd file
echo "Creating htpasswd file at $HTPASSWD_FILE..."
htpasswd -bc "$HTPASSWD_FILE" "$USERNAME" "$PASSWORD"

# Set proper permissions
chmod 644 "$HTPASSWD_FILE"
chown www-data:www-data "$HTPASSWD_FILE"

# Enable basic auth in nginx config
echo "Enabling basic authentication in nginx configuration..."
sed -i 's/# auth_basic "Redis Admin Access";/auth_basic "Redis Admin Access";/' /etc/nginx/nginx.conf
sed -i 's|# auth_basic_user_file /etc/nginx/.htpasswd;|auth_basic_user_file /etc/nginx/.htpasswd;|' /etc/nginx/nginx.conf

# Test nginx configuration
echo "Testing nginx configuration..."
nginx -t

if [ $? -eq 0 ]; then
    echo "✓ Nginx configuration is valid"
    echo ""
    echo "Basic authentication has been configured successfully!"
    echo "Username: $USERNAME"
    echo "Password: [hidden]"
    echo ""
    echo "To apply changes, restart nginx:"
    echo "  supervisorctl restart nginx"
    echo ""
    echo "Access Redis Admin at: http://your-server/redis-admin"
else
    echo "✗ Nginx configuration test failed"
    echo "Please check the configuration and try again"
    exit 1
fi

# Optional: Add more users
echo ""
read -p "Would you like to add another user? (y/n): " ADD_MORE
if [ "$ADD_MORE" = "y" ] || [ "$ADD_MORE" = "Y" ]; then
    read -p "Enter additional username: " ADD_USERNAME
    htpasswd -b "$HTPASSWD_FILE" "$ADD_USERNAME"
    echo "User $ADD_USERNAME added successfully"
fi

echo ""
echo "Setup complete! Remember to restart nginx to apply changes."