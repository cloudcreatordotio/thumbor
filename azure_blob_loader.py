#!/usr/bin/python
# -*- coding: utf-8 -*-
# Copyright (c) 2025-2026 Matthew Williams
# SPDX-License-Identifier: MIT
#
# This file is released under the MIT License.
# See the LICENSE file in the project root for the full license text.


# Custom Azure Blob Storage loader for Thumbor
# This loader handles Azure Blob Storage URLs with SAS tokens properly
# Updated for Thumbor 7.x with async/await and thread pool executor for Azure SDK

import re
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs, unquote
from thumbor.loaders import LoaderResult
from thumbor.utils import logger
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError, AzureError
from azure.identity import DefaultAzureCredential

# Thread pool executor for running synchronous Azure SDK calls
executor = ThreadPoolExecutor(max_workers=10)


def _get_blob_service_client(context):
    """Create and return Azure Blob Service Client based on configuration"""

    # Check for different authentication methods in order of preference

    # 1. Connection string (highest priority)
    connection_string = getattr(context.config, 'AZURE_STORAGE_CONNECTION_STRING', None)
    if connection_string:
        logger.debug("Using Azure connection string for authentication")
        return BlobServiceClient.from_connection_string(connection_string)

    # 2. Account key
    account_name = getattr(context.config, 'AZURE_STORAGE_ACCOUNT_NAME', None)
    account_key = getattr(context.config, 'AZURE_STORAGE_ACCOUNT_KEY', None)

    if account_name and account_key:
        logger.debug(f"Using Azure account key for authentication - Account: {account_name}")
        account_url = f"https://{account_name}.blob.core.windows.net"
        return BlobServiceClient(account_url=account_url, credential=account_key)

    # 3. SAS token
    sas_token = getattr(context.config, 'AZURE_STORAGE_SAS_TOKEN', None)
    if account_name and sas_token:
        logger.debug(f"Using Azure SAS token for authentication - Account: {account_name}")
        # Remove leading ? if present
        if sas_token.startswith('?'):
            sas_token = sas_token[1:]
        account_url = f"https://{account_name}.blob.core.windows.net?{sas_token}"
        return BlobServiceClient(account_url=account_url)

    # 4. Managed Identity (DefaultAzureCredential)
    use_managed_identity = getattr(context.config, 'AZURE_USE_MANAGED_IDENTITY', False)
    if use_managed_identity and account_name:
        logger.debug(f"Using Azure Managed Identity for authentication - Account: {account_name}")
        account_url = f"https://{account_name}.blob.core.windows.net"
        credential = DefaultAzureCredential()
        return BlobServiceClient(account_url=account_url, credential=credential)

    # 5. No authentication (public blobs only)
    if account_name:
        logger.warning(f"No Azure credentials configured, attempting public access - Account: {account_name}")
        account_url = f"https://{account_name}.blob.core.windows.net"
        return BlobServiceClient(account_url=account_url)

    # No configuration found
    logger.error("Azure Blob Storage configuration not found. Please configure AZURE_STORAGE_ACCOUNT_NAME and credentials")
    raise ValueError("Azure Blob Storage configuration not found. Please configure at least AZURE_STORAGE_ACCOUNT_NAME")


def _parse_azure_blob_url(url, context=None):
    """
    Parse Azure Blob Storage URL to extract container and blob path

    Supports formats:
    - Full Azure URL: https://account.blob.core.windows.net/container/path/to/blob.jpg?sas_token
    - Azure URL without protocol: account.blob.core.windows.net/container/path/to/blob.jpg
    - Container and path: container/path/to/blob.jpg
    - Just path (uses default container from config): path/to/blob.jpg

    Args:
        url: The URL or path to parse
        context: Optional Thumbor context for accessing configuration

    Returns:
        Tuple of (container, blob_path)
    """

    # URL decode the path in case Thumbor encoded it
    # e.g., "https%3A//domain.com" → "https://domain.com"
    url = unquote(url)
    
    # Fix single-slash protocol (https:/ -> https://)
    # This handles cases where path normalization collapsed // to /
    url = re.sub(r'^(https?:)/([^/])', r'\1//\2', url)
    
    logger.debug(f"URL after decoding and normalization: {url}")

    # Check if it's a full Azure URL (with or without protocol)
    # Pattern matches both:
    # - https://account.blob.core.windows.net/container/path
    # - account.blob.core.windows.net/container/path
    azure_pattern = r'^(?:https?://)?([^\.]+)\.blob\.core\.windows\.net/([^/?]+)/(.+)(?:\?.*)?$'
    match = re.match(azure_pattern, url)

    if match:
        account_name = match.group(1)
        container = match.group(2)
        blob_path = match.group(3)

        # Verify the account name matches our configuration (if context provided)
        if context:
            configured_account = getattr(context.config, 'AZURE_STORAGE_ACCOUNT_NAME', None)
            if configured_account and account_name != configured_account:
                logger.warning(f"Azure URL account '{account_name}' doesn't match configured account '{configured_account}'")

        logger.debug(f"Parsed Azure URL - Account: {account_name}, Container: {container}, Path: {blob_path}")
        # Note: We ignore the SAS token from the URL since we use SDK authentication
        return container, blob_path

    # Check if it starts with http/https but isn't an Azure URL
    # (This means it was meant for a different loader)
    if url.startswith(('http://', 'https://')):
        logger.debug(f"Non-Azure HTTP URL detected, will fall back to HTTP loader: {url}")
        return None, None

    # Get known path prefixes from config (default set if not provided)
    known_path_prefixes = ['perm', 'temp', 'cache', 'uploads', 'files', 'documents', 'images']
    if context:
        known_path_prefixes = getattr(context.config, 'AZURE_KNOWN_PATH_PREFIXES', known_path_prefixes)

    # Handle container/path format vs path-only
    parts = url.split('/', 1)

    if len(parts) >= 2:
        potential_container = parts[0]

        # If the first segment is a known path prefix, treat entire URL as path (no container)
        if potential_container in known_path_prefixes:
            logger.debug(f"Parsed as path with known prefix '{potential_container}' - Using default container for: {url}")
            return None, url
        else:
            # Otherwise, treat first segment as container
            logger.debug(f"Parsed as container/path - Container: {parts[0]}, Path: {parts[1]}")
            return parts[0], parts[1]

    # Single path segment - use default container from config
    logger.debug(f"Parsed as path only - Path: {url}")
    return None, url


def _normalize_blob_path(path):
    """Normalize the blob path by removing leading slashes and query parameters"""
    # Remove query parameters if any
    if '?' in path:
        path = path.split('?')[0]

    # Remove leading slash
    if path.startswith('/'):
        path = path[1:]

    return path


def _download_blob_sync(blob_service_client, container, blob_path):
    """Synchronous function to download blob - will be run in thread pool"""
    try:
        blob_client = blob_service_client.get_blob_client(
            container=container,
            blob=blob_path
        )

        # Download the blob
        blob_data = blob_client.download_blob()
        content = blob_data.readall()

        # Get properties for metadata
        properties = blob_client.get_blob_properties()

        return {
            'content': content,
            'properties': properties,
            'success': True,
            'error': None
        }
    except ResourceNotFoundError as e:
        return {
            'content': None,
            'properties': None,
            'success': False,
            'error': f"Blob not found: {str(e)}",
            'error_type': 'not_found'
        }
    except AzureError as e:
        return {
            'content': None,
            'properties': None,
            'success': False,
            'error': f"Azure error: {str(e)}",
            'error_type': 'azure_error'
        }
    except Exception as e:
        return {
            'content': None,
            'properties': None,
            'success': False,
            'error': f"Unexpected error: {str(e)}",
            'error_type': 'unknown'
        }


async def load(context, path):
    """
    Load image from Azure Blob Storage

    Args:
        context: Thumbor context
        path: The image path/URL to load

    Returns:
        LoaderResult: The result of the loading operation
    """

    result = LoaderResult()

    try:
        # Parse the Azure blob URL (pass context for config access)
        container, blob_path = _parse_azure_blob_url(path, context)

        # Add detailed logging for troubleshooting
        logger.debug(f"URL Parsing Result - Input: {path}")
        logger.debug(f"  Container: {container if container else '(using default)'}")
        logger.debug(f"  Blob Path: {blob_path if blob_path else '(none)'}")

        # If we couldn't parse it as an Azure URL and it's an HTTP URL,
        # fall back to HTTP loader
        if container is None and blob_path is None:
            logger.info(f"Not an Azure Blob URL, falling back to HTTP loader for: {path}")
            try:
                # Import here to avoid circular dependency
                from thumbor.loaders import http_loader
                result = await http_loader.load(context, path)
                logger.debug(f"HTTP loader result: successful={result.successful}")
                return result
            except AttributeError as e:
                logger.error(f"HTTP loader context error for {path}: {str(e)}", exc_info=True)
                # Context issue - return error
                result = LoaderResult()
                result.successful = False
                result.error = LoaderResult.ERROR_UPSTREAM
                return result
            except Exception as e:
                logger.error(f"HTTP loader failed for {path}: {str(e)}", exc_info=True)
                result = LoaderResult()
                result.successful = False
                result.error = LoaderResult.ERROR_UPSTREAM
                return result

        # Use default container if not specified
        if container is None:
            container = getattr(context.config, 'AZURE_STORAGE_DEFAULT_CONTAINER', 'media')
            logger.debug(f"Using default container: {container}")

        # Normalize the blob path
        blob_path = _normalize_blob_path(blob_path)

        logger.info(f"Loading from Azure Blob Storage - Container: {container}, Blob: {blob_path}")

        try:
            # Get the blob service client
            blob_service_client = _get_blob_service_client(context)
        except ValueError as e:
            logger.error(f"Failed to get Azure client: {str(e)}")
            result.successful = False
            result.error = LoaderResult.ERROR_UPSTREAM
            return result
        except Exception as e:
            logger.error(f"Unexpected error getting Azure client: {str(e)}")
            result.successful = False
            result.error = LoaderResult.ERROR_UPSTREAM
            return result

        # Download the blob using thread pool executor to avoid blocking
        loop = asyncio.get_event_loop()

        logger.debug(f"Downloading blob from Azure: {container}/{blob_path}")

        try:
            blob_result = await loop.run_in_executor(
                executor,
                _download_blob_sync,
                blob_service_client,
                container,
                blob_path
            )
        except Exception as e:
            logger.error(f"Failed to download blob in executor: {str(e)}")
            result.successful = False
            result.error = LoaderResult.ERROR_UPSTREAM
            return result

        if blob_result['success'] and blob_result['content']:
            result.successful = True
            result.buffer = blob_result['content']

            # Add metadata if available
            properties = blob_result['properties']
            if properties:
                result.metadata = {
                    'ContentType': properties.content_settings.content_type if properties.content_settings else None,
                    'ContentLength': properties.size,
                    'LastModified': properties.last_modified.isoformat() if properties.last_modified else None,
                    'ETag': properties.etag
                }
                logger.info(f"Successfully loaded blob: {container}/{blob_path}, Size: {properties.size} bytes")
        else:
            result.successful = False

            # Set appropriate error type with detailed logging
            if blob_result.get('error_type') == 'not_found':
                result.error = LoaderResult.ERROR_NOT_FOUND
                logger.warning(f"Blob not found: {container}/{blob_path}")
                logger.warning(f"  Original path: {path}")
                logger.warning(f"  Error details: {blob_result.get('error')}")
            else:
                result.error = LoaderResult.ERROR_UPSTREAM
                logger.error(f"Failed to load blob: {container}/{blob_path}")
                logger.error(f"  Original path: {path}")
                logger.error(f"  Error type: {blob_result.get('error_type')}")
                logger.error(f"  Error details: {blob_result.get('error')}")

    except Exception as e:
        result.successful = False
        result.error = LoaderResult.ERROR_UPSTREAM
        logger.error(f"Unexpected error in load function for path {path}: {str(e)}", exc_info=True)

    return result