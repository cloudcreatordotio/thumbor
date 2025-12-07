# Copyright (c) 2025-2026 Matthew Williams
# SPDX-License-Identifier: MIT
#
# This file is released under the MIT License.
# See the LICENSE file in the project root for the full license text.

"""
Custom RemoteCV loader for Azure Blob Storage.

This loader uses the Azure SDK to fetch images directly from Azure Blob Storage,
matching the approach used in Thumbor's azure_blob_loader.py.

Falls back to HTTPS for non-Azure URLs.
"""

import os
import re
from urllib.parse import unquote
from urllib.request import urlopen
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError, AzureError

# RemoteCV imports
from remotecv.timing import get_time, get_interval
from remotecv.utils import context

try:
    from remotecv.utils import logger
except ImportError:
    import logging
    logger = logging.getLogger('remotecv.azure_loader')


def _parse_azure_blob_url(url):
    """
    Parse Azure Blob Storage URL to extract container and blob path.

    Handles various URL formats:
    - https://account.blob.core.windows.net/container/path/to/blob
    - account.blob.core.windows.net/container/path/to/blob
    - container/path/to/blob (uses default container if single segment)

    Returns:
        tuple: (container_name, blob_path) or (None, None) if not parseable
    """
    if not url:
        return None, None

    url = unquote(url)
    
    # Fix single-slash protocol (https:/ -> https://)
    # This handles cases where path normalization collapsed // to /
    url = re.sub(r'^(https?:)/([^/])', r'\1//\2', url)

    # Pattern 1: Full Azure Blob Storage URL with or without protocol
    # Matches: https://account.blob.core.windows.net/container/path or account.blob.core.windows.net/container/path
    azure_pattern = r'^(?:https?://)?([^\.]+)\.blob\.core\.windows\.net/([^/?]+)/(.+?)(?:\?.*)?$'
    match = re.match(azure_pattern, url)

    if match:
        account_name = match.group(1)
        container = match.group(2)
        blob_path = match.group(3)
        logger.debug(f"Parsed Azure URL - Account: {account_name}, Container: {container}, Blob: {blob_path}")
        return container, blob_path

    # Pattern 2: Path with container (e.g., "media/perm/sites/tw/2023/226/image.jpg")
    # First segment is container, rest is blob path
    if '/' in url and not url.startswith('http'):
        parts = url.split('/', 1)
        if len(parts) == 2:
            container = parts[0]
            blob_path = parts[1]
            logger.debug(f"Parsed path format - Container: {container}, Blob: {blob_path}")
            return container, blob_path

    logger.debug(f"Could not parse as Azure URL: {url}")
    return None, None


def _get_blob_service_client():
    """
    Create Azure Blob Service Client using environment credentials.

    Supports two authentication methods (in order of preference):
    1. Connection string (AZURE_STORAGE_CONNECTION_STRING)
    2. Account name + key (AZURE_STORAGE_ACCOUNT_NAME + AZURE_STORAGE_ACCOUNT_KEY)

    Returns:
        BlobServiceClient: Authenticated Azure Blob Service client

    Raises:
        ValueError: If credentials are not configured
    """
    connection_string = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')

    if connection_string:
        logger.debug("Using Azure connection string authentication")
        return BlobServiceClient.from_connection_string(connection_string)

    account_name = os.environ.get('AZURE_STORAGE_ACCOUNT_NAME')
    account_key = os.environ.get('AZURE_STORAGE_ACCOUNT_KEY')

    if account_name and account_key:
        account_url = f"https://{account_name}.blob.core.windows.net"
        logger.debug(f"Using Azure account key authentication for {account_name}")
        return BlobServiceClient(account_url=account_url, credential=account_key)

    raise ValueError(
        "Azure Blob Storage credentials not configured. "
        "Set AZURE_STORAGE_CONNECTION_STRING or (AZURE_STORAGE_ACCOUNT_NAME + AZURE_STORAGE_ACCOUNT_KEY)"
    )


def _load_from_azure(container, blob_path):
    """
    Load blob data from Azure Blob Storage using Azure SDK.

    Args:
        container (str): Azure Blob Storage container name
        blob_path (str): Path to blob within container

    Returns:
        bytes: Blob data

    Raises:
        ResourceNotFoundError: If blob doesn't exist
        AzureError: For other Azure-related errors
    """
    try:
        blob_service_client = _get_blob_service_client()
        blob_client = blob_service_client.get_blob_client(container=container, blob=blob_path)

        logger.info(f"Loading from Azure Blob Storage: {container}/{blob_path}")

        # Download blob data
        blob_data = blob_client.download_blob()
        result = blob_data.readall()

        logger.debug(f"Successfully loaded {len(result)} bytes from Azure")
        return result

    except ResourceNotFoundError:
        logger.error(f"Blob not found in Azure Storage: {container}/{blob_path}")
        raise
    except AzureError as e:
        logger.error(f"Azure error loading blob {container}/{blob_path}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error loading from Azure: {str(e)}")
        raise


def _load_from_http(url):
    """
    Load image from HTTP/HTTPS URL.

    Ensures HTTPS is used if no protocol is specified.

    Args:
        url (str): HTTP/HTTPS URL

    Returns:
        bytes: Image data
    """
    # If no protocol specified, default to HTTPS
    if not re.match(r'^https?://', url):
        url = f"https://{url}"

    logger.info(f"Loading from HTTP/HTTPS: {url}")

    url = unquote(url)
    response = urlopen(url)
    result = response.read()

    logger.debug(f"Successfully loaded {len(result)} bytes via HTTP")
    return result


def load_sync(path):
    """
    RemoteCV loader function that loads images from Azure Blob Storage or HTTP/HTTPS.

    This function is called by RemoteCV's detection tasks to load images for processing.

    Flow:
    1. Try to parse as Azure Blob Storage URL
    2. If successful, load via Azure SDK
    3. If not Azure URL, fall back to HTTPS

    Args:
        path (str): Image path/URL (various formats supported)

    Returns:
        bytes: Image data

    Raises:
        Exception: If image cannot be loaded
    """
    start_time = get_time()

    try:
        # Try to parse as Azure Blob Storage URL
        container, blob_path = _parse_azure_blob_url(path)

        if container and blob_path:
            # Load from Azure Blob Storage
            result = _load_from_azure(container, blob_path)

            # Record metrics
            context.metrics.incr("worker.original_image.response_bytes", len(result))
            context.metrics.timing(
                f"worker.original_image.fetch.azure.{container}",
                get_interval(start_time, get_time()),
            )
            context.metrics.incr(f"worker.original_image.fetch.azure")
            context.metrics.incr(f"worker.original_image.status.200")

            return result
        else:
            # Not an Azure URL, load via HTTP/HTTPS
            result = _load_from_http(path)

            # Record metrics
            context.metrics.incr("worker.original_image.response_bytes", len(result))
            context.metrics.timing(
                "worker.original_image.fetch.http",
                get_interval(start_time, get_time()),
            )
            context.metrics.incr("worker.original_image.fetch.http")
            context.metrics.incr("worker.original_image.status.200")

            return result

    except ResourceNotFoundError:
        logger.error(f"Image not found: {path}")
        context.metrics.incr("worker.original_image.status.404")
        raise
    except Exception as e:
        logger.error(f"Failed to load image from {path}: {str(e)}")
        context.metrics.incr("worker.original_image.error")
        context.metrics.incr("worker.original_image.status.500")
        raise


# For debugging/testing
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.DEBUG)

    if len(sys.argv) > 1:
        test_path = sys.argv[1]
        print(f"Testing load_sync with path: {test_path}")

        # Mock context for testing
        class MockMetrics:
            def incr(self, *args, **kwargs):
                print(f"  Metric incr: {args}")
            def timing(self, *args, **kwargs):
                print(f"  Metric timing: {args}")

        class MockContext:
            metrics = MockMetrics()

        context = MockContext()

        try:
            data = load_sync(test_path)
            print(f"Successfully loaded {len(data)} bytes")
        except Exception as e:
            print(f"Error: {e}")
    else:
        print("Usage: python remotecv_azure_loader.py <path>")
        print("\nExample paths:")
        print("  mystorageaccount.blob.core.windows.net/media/perm/sites/tw/2023/226/image.jpg")
        print("  https://mystorageaccount.blob.core.windows.net/media/perm/sites/tw/2023/226/image.jpg")
        print("  media/perm/sites/tw/2023/226/image.jpg")
        print("  https://example.com/image.jpg")
