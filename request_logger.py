# Copyright (c) 2025-2026 Matthew Williams
# SPDX-License-Identifier: MIT
#
# This file is released under the MIT License.
# See the LICENSE file in the project root for the full license text.

"""
Custom Request Logger for Thumbor
Provides detailed request logging with automatic format switching between JSON (Azure) and human-readable (local)
"""

import logging
import time
import uuid
import os
import sys
from typing import Any, Dict, Optional
import json

try:
    from pythonjsonlogger import jsonlogger
    JSON_LOGGER_AVAILABLE = True
except ImportError:
    JSON_LOGGER_AVAILABLE = False

from thumbor.handlers import BaseHandler
from thumbor.context import Context


class RequestLoggerMixin:
    """
    Mixin to add detailed request logging to Thumbor handlers.
    Captures request/response metadata, image operations, timing, and more.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._request_start_time = None
        self._correlation_id = None

    def prepare(self):
        """Called at the beginning of a request before the HTTP method handler."""
        self._request_start_time = time.time()
        self._correlation_id = str(uuid.uuid4())

        # Call parent prepare if it exists
        if hasattr(super(), 'prepare'):
            super().prepare()

        # Log request start
        log_request_start(
            handler=self,
            correlation_id=self._correlation_id,
            context=getattr(self, 'context', None)
        )

    def on_finish(self):
        """Called after the end of a request."""
        processing_time = None
        if self._request_start_time:
            processing_time = (time.time() - self._request_start_time) * 1000  # Convert to ms

        # Log request completion
        log_request_completion(
            handler=self,
            correlation_id=self._correlation_id,
            processing_time_ms=processing_time,
            context=getattr(self, 'context', None)
        )

        # Call parent on_finish if it exists
        if hasattr(super(), 'on_finish'):
            super().on_finish()

    def log_exception(self, typ, value, tb):
        """Called for uncaught exceptions."""
        processing_time = None
        if self._request_start_time:
            processing_time = (time.time() - self._request_start_time) * 1000

        # Log exception
        log_request_exception(
            handler=self,
            correlation_id=self._correlation_id,
            processing_time_ms=processing_time,
            exc_type=typ,
            exc_value=value,
            context=getattr(self, 'context', None)
        )

        # Call parent log_exception
        if hasattr(super(), 'log_exception'):
            super().log_exception(typ, value, tb)


def is_azure_environment():
    """Detect if running in Azure App Service or Container."""
    return any([
        os.getenv('WEBSITE_INSTANCE_ID'),
        os.getenv('WEBSITE_SITE_NAME'),
        os.getenv('AZURE_ENVIRONMENT')
    ])


def setup_request_logger():
    """
    Set up the request logger with appropriate formatter based on environment.
    Returns the configured logger instance.
    """
    logger = logging.getLogger('thumbor.request')

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Create console handler (stdout)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)

    # Choose formatter based on environment
    if is_azure_environment() and JSON_LOGGER_AVAILABLE:
        # JSON format for Azure
        formatter = jsonlogger.JsonFormatter(
            '%(timestamp)s %(level)s %(correlation_id)s %(message)s',
            rename_fields={
                'levelname': 'level',
                'asctime': 'timestamp'
            },
            timestamp=True
        )
    else:
        # Human-readable format for local development
        formatter = logging.Formatter(
            '%(asctime)s %(levelname)s [%(correlation_id)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


# Initialize the logger
request_logger = setup_request_logger()


def extract_request_data(handler: Any, correlation_id: str, context: Optional[Context] = None) -> Dict[str, Any]:
    """Extract comprehensive request data from the handler."""
    request = handler.request

    data = {
        'correlation_id': correlation_id,
        'request': {
            'method': request.method,
            'uri': request.uri,
            'path': request.path,
            'query': request.query,
            'protocol': request.version,
            'host': request.host,
        },
        'client': {
            'ip': request.remote_ip,
            'user_agent': request.headers.get('User-Agent', ''),
        },
        'headers': dict(request.headers),
        'worker_id': os.getenv('SUPERVISOR_PROCESS_NAME', 'unknown'),
    }

    # Extract Thumbor-specific context information if available
    if context:
        thumbor_data = {}

        # Request context
        if hasattr(context, 'request') and context.request:
            req_ctx = context.request

            # Image operations
            if hasattr(req_ctx, 'width') or hasattr(req_ctx, 'height'):
                thumbor_data['operations'] = {
                    'width': getattr(req_ctx, 'width', None),
                    'height': getattr(req_ctx, 'height', None),
                    'smart': getattr(req_ctx, 'smart', False),
                    'fit_in': getattr(req_ctx, 'fit_in', False),
                    'adaptive': getattr(req_ctx, 'adaptive', False),
                    'full': getattr(req_ctx, 'full', False),
                    'horizontal_flip': getattr(req_ctx, 'horizontal_flip', False),
                    'vertical_flip': getattr(req_ctx, 'vertical_flip', False),
                }

            # Filters
            if hasattr(req_ctx, 'filters') and req_ctx.filters:
                thumbor_data['filters'] = req_ctx.filters

            # Crop coordinates
            if hasattr(req_ctx, 'crop') and req_ctx.crop:
                thumbor_data['crop'] = {
                    'left': req_ctx.crop.get('left'),
                    'top': req_ctx.crop.get('top'),
                    'right': req_ctx.crop.get('right'),
                    'bottom': req_ctx.crop.get('bottom'),
                }

            # Image URL/path
            if hasattr(req_ctx, 'image_url'):
                thumbor_data['source_image'] = req_ctx.image_url

            # Unsafe/safe mode
            if hasattr(req_ctx, 'unsafe'):
                thumbor_data['unsafe_mode'] = req_ctx.unsafe

        # Add thumbor data if any was extracted
        if thumbor_data:
            data['thumbor'] = thumbor_data

    return data


def log_request_start(handler: Any, correlation_id: str, context: Optional[Context] = None):
    """Log the start of a request."""
    try:
        data = extract_request_data(handler, correlation_id, context)

        if is_azure_environment() and JSON_LOGGER_AVAILABLE:
            # JSON format - log as structured data
            request_logger.info(
                'Request started',
                extra={
                    **data,
                    'event': 'request_start',
                }
            )
        else:
            # Human-readable format
            req = data['request']
            thumbor_info = ''
            if 'thumbor' in data and 'source_image' in data['thumbor']:
                source = data['thumbor']['source_image']
                thumbor_info = f" source={source[:80]}{'...' if len(source) > 80 else ''}"

            request_logger.info(
                f"→ {req['method']} {req['path']}{thumbor_info}",
                extra={'correlation_id': correlation_id}
            )
    except Exception as e:
        request_logger.error(f"Error logging request start: {e}", extra={'correlation_id': correlation_id})


def log_request_completion(
    handler: Any,
    correlation_id: str,
    processing_time_ms: Optional[float],
    context: Optional[Context] = None
):
    """Log the completion of a request."""
    try:
        data = extract_request_data(handler, correlation_id, context)

        # Add response data
        data['response'] = {
            'status': handler.get_status(),
            'size_bytes': len(handler._write_buffer) if hasattr(handler, '_write_buffer') else 0,
            'processing_time_ms': round(processing_time_ms, 2) if processing_time_ms else None,
        }

        if is_azure_environment() and JSON_LOGGER_AVAILABLE:
            # JSON format
            request_logger.info(
                'Request completed',
                extra={
                    **data,
                    'event': 'request_complete',
                }
            )
        else:
            # Human-readable format
            req = data['request']
            resp = data['response']
            status = resp['status']
            time_str = f"{resp['processing_time_ms']:.0f}ms" if resp['processing_time_ms'] else "?ms"
            size_kb = resp['size_bytes'] / 1024

            # Get operations summary
            ops_summary = ''
            if 'thumbor' in data:
                ops = data['thumbor'].get('operations', {})
                filters = data['thumbor'].get('filters', '')

                ops_parts = []
                if ops.get('width') or ops.get('height'):
                    ops_parts.append(f"resize:{ops.get('width', 'auto')}x{ops.get('height', 'auto')}")
                if ops.get('smart'):
                    ops_parts.append('smart')
                if ops.get('fit_in'):
                    ops_parts.append('fit-in')
                if filters:
                    ops_parts.append(f"filters:{filters}")

                if ops_parts:
                    ops_summary = f" ops=[{','.join(ops_parts)}]"

            # Color code by status
            status_indicator = '✓' if status < 400 else '✗'

            request_logger.info(
                f"{status_indicator} {req['method']} {req['path']} → {status} ({time_str}, {size_kb:.1f}KB){ops_summary}",
                extra={'correlation_id': correlation_id}
            )
    except Exception as e:
        request_logger.error(f"Error logging request completion: {e}", extra={'correlation_id': correlation_id})


def log_request_exception(
    handler: Any,
    correlation_id: str,
    processing_time_ms: Optional[float],
    exc_type: type,
    exc_value: Exception,
    context: Optional[Context] = None
):
    """Log an exception during request processing."""
    try:
        data = extract_request_data(handler, correlation_id, context)

        # Add exception data
        data['exception'] = {
            'type': exc_type.__name__ if exc_type else 'Unknown',
            'message': str(exc_value),
            'processing_time_ms': round(processing_time_ms, 2) if processing_time_ms else None,
        }

        data['response'] = {
            'status': handler.get_status(),
            'processing_time_ms': round(processing_time_ms, 2) if processing_time_ms else None,
        }

        if is_azure_environment() and JSON_LOGGER_AVAILABLE:
            # JSON format
            request_logger.error(
                'Request exception',
                extra={
                    **data,
                    'event': 'request_exception',
                }
            )
        else:
            # Human-readable format
            req = data['request']
            exc = data['exception']
            time_str = f"{exc['processing_time_ms']:.0f}ms" if exc['processing_time_ms'] else "?ms"

            request_logger.error(
                f"✗ {req['method']} {req['path']} → EXCEPTION {exc['type']}: {exc['message']} ({time_str})",
                extra={'correlation_id': correlation_id}
            )
    except Exception as e:
        request_logger.error(f"Error logging exception: {e}", extra={'correlation_id': correlation_id})


def wrap_handler(handler_class):
    """
    Wrap a Thumbor handler class to add request logging.
    Returns a new class that inherits from both the mixin and the original handler.
    """
    class LoggingHandler(RequestLoggerMixin, handler_class):
        pass

    LoggingHandler.__name__ = f"Logging{handler_class.__name__}"
    return LoggingHandler


def patch_thumbor_handlers():
    """
    Patch Thumbor's BaseHandler to add request logging to all handlers.
    This should be called once during application initialization.
    """
    try:
        from thumbor.handlers import BaseHandler

        # Store original methods
        original_prepare = BaseHandler.prepare if hasattr(BaseHandler, 'prepare') else None
        original_on_finish = BaseHandler.on_finish if hasattr(BaseHandler, 'on_finish') else None
        original_log_exception = BaseHandler.log_exception if hasattr(BaseHandler, 'log_exception') else None

        # Create new methods that include logging
        def new_prepare(self):
            self._request_start_time = time.time()
            self._correlation_id = str(uuid.uuid4())

            log_request_start(
                handler=self,
                correlation_id=self._correlation_id,
                context=getattr(self, 'context', None)
            )

            if original_prepare:
                return original_prepare(self)

        def new_on_finish(self):
            processing_time = None
            if hasattr(self, '_request_start_time') and self._request_start_time:
                processing_time = (time.time() - self._request_start_time) * 1000

            correlation_id = getattr(self, '_correlation_id', 'unknown')

            log_request_completion(
                handler=self,
                correlation_id=correlation_id,
                processing_time_ms=processing_time,
                context=getattr(self, 'context', None)
            )

            if original_on_finish:
                return original_on_finish(self)

        def new_log_exception(self, typ, value, tb):
            processing_time = None
            if hasattr(self, '_request_start_time') and self._request_start_time:
                processing_time = (time.time() - self._request_start_time) * 1000

            correlation_id = getattr(self, '_correlation_id', 'unknown')

            log_request_exception(
                handler=self,
                correlation_id=correlation_id,
                processing_time_ms=processing_time,
                exc_type=typ,
                exc_value=value,
                context=getattr(self, 'context', None)
            )

            if original_log_exception:
                return original_log_exception(self, typ, value, tb)

        # Patch the BaseHandler
        BaseHandler.prepare = new_prepare
        BaseHandler.on_finish = new_on_finish
        BaseHandler.log_exception = new_log_exception

        request_logger.info("Thumbor request logging enabled", extra={'correlation_id': 'system'})
        return True

    except ImportError as e:
        request_logger.error(f"Failed to patch Thumbor handlers: {e}", extra={'correlation_id': 'system'})
        return False
    except Exception as e:
        request_logger.error(f"Unexpected error patching handlers: {e}", extra={'correlation_id': 'system'})
        return False
