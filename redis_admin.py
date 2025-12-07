#!/usr/bin/env python3.11
# Copyright (c) 2025-2026 Matthew Williams
# SPDX-License-Identifier: MIT
#
# This file is released under the MIT License.
# See the LICENSE file in the project root for the full license text.

"""
Lightweight Redis Admin Interface for Thumbor Container
Provides web-based Redis management without external dependencies
"""

import os
import json
import redis
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS
from datetime import datetime
import traceback

app = Flask(__name__)
CORS(app)

# Redis connection settings from environment
REDIS_HOST = os.environ.get('REDIS_SERVER_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_SERVER_PORT', 6379))
REDIS_DB = int(os.environ.get('REDIS_SERVER_DB', 0))

# Create Redis connection pool
redis_pool = redis.ConnectionPool(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True
)

def get_redis_connection():
    """Get Redis connection from pool"""
    return redis.Redis(connection_pool=redis_pool)

# HTML template for the web interface
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Redis Admin - Thumbor</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f5f5f5;
            color: #333;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .header h1 { font-size: 2em; margin-bottom: 10px; }
        .header p { opacity: 0.9; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            border-left: 4px solid #667eea;
        }
        .stat-card h3 {
            font-size: 0.9em;
            color: #666;
            margin-bottom: 8px;
            text-transform: uppercase;
        }
        .stat-card .value {
            font-size: 1.8em;
            font-weight: bold;
            color: #333;
        }
        .section {
            background: white;
            padding: 25px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }
        .section h2 {
            margin-bottom: 20px;
            color: #667eea;
            border-bottom: 2px solid #f0f0f0;
            padding-bottom: 10px;
        }
        .search-box {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
        }
        input[type="text"], textarea {
            flex: 1;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 14px;
        }
        textarea { min-height: 100px; font-family: 'Courier New', monospace; }
        button {
            background: #667eea;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            transition: background 0.3s;
        }
        button:hover { background: #5a67d8; }
        button.danger {
            background: #e53e3e;
        }
        button.danger:hover { background: #c53030; }
        .keys-list {
            max-height: 400px;
            overflow-y: auto;
            border: 1px solid #e0e0e0;
            border-radius: 4px;
            padding: 10px;
        }
        .key-item {
            padding: 8px;
            margin-bottom: 5px;
            background: #f8f8f8;
            border-radius: 4px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: background 0.2s;
        }
        .key-item:hover { background: #e8e8e8; }
        .key-name {
            font-family: 'Courier New', monospace;
            font-size: 13px;
            word-break: break-all;
        }
        .key-type {
            font-size: 11px;
            padding: 2px 8px;
            background: #667eea;
            color: white;
            border-radius: 3px;
        }
        .result-box {
            background: #f8f8f8;
            padding: 15px;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-size: 13px;
            margin-top: 15px;
            white-space: pre-wrap;
            word-break: break-all;
            max-height: 300px;
            overflow-y: auto;
        }
        .error { color: #e53e3e; }
        .success { color: #38a169; }
        .loading { opacity: 0.5; }
        @media (max-width: 768px) {
            .stats-grid { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔧 Redis Admin</h1>
            <p>Thumbor Redis Management Interface</p>
        </div>

        <div id="stats" class="stats-grid">
            <div class="stat-card">
                <h3>Status</h3>
                <div class="value" id="status">Connecting...</div>
            </div>
            <div class="stat-card">
                <h3>Memory Usage</h3>
                <div class="value" id="memory">-</div>
            </div>
            <div class="stat-card">
                <h3>Total Keys</h3>
                <div class="value" id="keys">-</div>
            </div>
            <div class="stat-card">
                <h3>Connected Clients</h3>
                <div class="value" id="clients">-</div>
            </div>
        </div>

        <div class="section">
            <h2>🔍 Browse Keys</h2>
            <div class="search-box">
                <input type="text" id="keyPattern" placeholder="Enter pattern (e.g., *, user:*, *cache*)" value="*">
                <button onclick="searchKeys()">Search</button>
                <button onclick="refreshKeys()">Refresh</button>
            </div>
            <div id="keysResult" class="keys-list">
                <p>Enter a pattern and click Search to list keys</p>
            </div>
        </div>

        <div class="section">
            <h2>📝 Execute Command</h2>
            <div class="search-box">
                <input type="text" id="command" placeholder="Enter Redis command (e.g., GET mykey, INFO server)">
                <button onclick="executeCommand()">Execute</button>
            </div>
            <div id="commandResult"></div>
        </div>

        <div class="section">
            <h2>✏️ Set Key Value</h2>
            <div style="margin-bottom: 10px;">
                <input type="text" id="setKey" placeholder="Key name" style="width: 100%; margin-bottom: 10px;">
                <textarea id="setValue" placeholder="Value (JSON supported)"></textarea>
            </div>
            <button onclick="setKeyValue()">Set Value</button>
            <div id="setResult"></div>
        </div>

        <div class="section">
            <h2>⚠️ Danger Zone</h2>
            <p style="margin-bottom: 15px; color: #666;">Use these operations with caution</p>
            <button class="danger" onclick="flushDB()">Flush Current DB</button>
            <button class="danger" onclick="flushAll()">Flush All DBs</button>
            <div id="dangerResult"></div>
        </div>
    </div>

    <script>
        const API_BASE = '/redis-admin/api';

        async function fetchAPI(endpoint, method = 'GET', body = null) {
            try {
                const options = {
                    method,
                    headers: { 'Content-Type': 'application/json' }
                };
                if (body) options.body = JSON.stringify(body);

                const response = await fetch(API_BASE + endpoint, options);
                return await response.json();
            } catch (error) {
                console.error('API Error:', error);
                return { error: error.message };
            }
        }

        async function loadStats() {
            const stats = await fetchAPI('/stats');
            if (!stats.error) {
                document.getElementById('status').textContent = 'Connected';
                document.getElementById('status').style.color = '#38a169';
                document.getElementById('memory').textContent = stats.memory_human;
                document.getElementById('keys').textContent = stats.db_keys;
                document.getElementById('clients').textContent = stats.connected_clients;
            } else {
                document.getElementById('status').textContent = 'Error';
                document.getElementById('status').style.color = '#e53e3e';
            }
        }

        async function searchKeys() {
            const pattern = document.getElementById('keyPattern').value || '*';
            const result = document.getElementById('keysResult');
            result.innerHTML = '<p class="loading">Searching...</p>';

            const response = await fetchAPI('/keys?pattern=' + encodeURIComponent(pattern));

            if (!response.error) {
                if (response.keys.length === 0) {
                    result.innerHTML = '<p>No keys found</p>';
                } else {
                    result.innerHTML = response.keys.map(key => `
                        <div class="key-item">
                            <span class="key-name">${key.key}</span>
                            <div>
                                <span class="key-type">${key.type}</span>
                                <button onclick="getKey('${key.key}')">View</button>
                                <button class="danger" onclick="deleteKey('${key.key}')">Delete</button>
                            </div>
                        </div>
                    `).join('');
                }
            } else {
                result.innerHTML = `<p class="error">Error: ${response.error}</p>`;
            }
        }

        async function refreshKeys() {
            searchKeys();
        }

        async function getKey(key) {
            const response = await fetchAPI('/key/' + encodeURIComponent(key));
            if (!response.error) {
                const result = document.getElementById('commandResult');
                result.innerHTML = `<div class="result-box">${JSON.stringify(response, null, 2)}</div>`;
            }
        }

        async function deleteKey(key) {
            if (!confirm(`Delete key: ${key}?`)) return;

            const response = await fetchAPI('/key/' + encodeURIComponent(key), 'DELETE');
            if (!response.error) {
                alert('Key deleted successfully');
                searchKeys();
            }
        }

        async function executeCommand() {
            const command = document.getElementById('command').value;
            if (!command) return;

            const result = document.getElementById('commandResult');
            result.innerHTML = '<p class="loading">Executing...</p>';

            const response = await fetchAPI('/execute', 'POST', { command });

            if (!response.error) {
                result.innerHTML = `<div class="result-box">${JSON.stringify(response.result, null, 2)}</div>`;
            } else {
                result.innerHTML = `<p class="error">Error: ${response.error}</p>`;
            }
        }

        async function setKeyValue() {
            const key = document.getElementById('setKey').value;
            const value = document.getElementById('setValue').value;

            if (!key || !value) {
                alert('Please enter both key and value');
                return;
            }

            const result = document.getElementById('setResult');
            result.innerHTML = '<p class="loading">Setting...</p>';

            const response = await fetchAPI('/key', 'POST', { key, value });

            if (!response.error) {
                result.innerHTML = '<p class="success">Value set successfully</p>';
                document.getElementById('setKey').value = '';
                document.getElementById('setValue').value = '';
            } else {
                result.innerHTML = `<p class="error">Error: ${response.error}</p>`;
            }
        }

        async function flushDB() {
            if (!confirm('Are you sure you want to flush the current database? This cannot be undone!')) return;

            const result = document.getElementById('dangerResult');
            const response = await fetchAPI('/flush-db', 'POST');

            if (!response.error) {
                result.innerHTML = '<p class="success">Database flushed successfully</p>';
                loadStats();
            } else {
                result.innerHTML = `<p class="error">Error: ${response.error}</p>`;
            }
        }

        async function flushAll() {
            if (!confirm('Are you sure you want to flush ALL databases? This cannot be undone!')) return;
            if (!confirm('This will delete ALL data in ALL Redis databases. Are you REALLY sure?')) return;

            const result = document.getElementById('dangerResult');
            const response = await fetchAPI('/flush-all', 'POST');

            if (!response.error) {
                result.innerHTML = '<p class="success">All databases flushed successfully</p>';
                loadStats();
            } else {
                result.innerHTML = `<p class="error">Error: ${response.error}</p>`;
            }
        }

        // Load stats on page load and refresh every 5 seconds
        loadStats();
        setInterval(loadStats, 5000);
    </script>
</body>
</html>
"""

@app.route('/')
@app.route('/redis-admin')
def index():
    """Serve the main HTML interface"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/redis-admin/api/stats')
def get_stats():
    """Get Redis server statistics"""
    try:
        r = get_redis_connection()
        info = r.info()

        # Extract key statistics
        stats = {
            'redis_version': info.get('redis_version', 'Unknown'),
            'uptime_days': info.get('uptime_in_days', 0),
            'connected_clients': info.get('connected_clients', 0),
            'used_memory': info.get('used_memory', 0),
            'used_memory_human': info.get('used_memory_human', '0B'),
            'memory_human': info.get('used_memory_human', '0B'),
            'db_keys': r.dbsize(),
            'total_commands_processed': info.get('total_commands_processed', 0),
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/redis-admin/api/keys')
def get_keys():
    """Get list of keys matching pattern"""
    try:
        pattern = request.args.get('pattern', '*')
        limit = int(request.args.get('limit', 100))

        r = get_redis_connection()
        keys = []

        # Use SCAN for better performance with large datasets
        cursor = 0
        count = 0
        while True:
            cursor, partial_keys = r.scan(cursor, match=pattern, count=100)
            for key in partial_keys:
                if count >= limit:
                    break
                key_type = r.type(key)
                keys.append({
                    'key': key,
                    'type': key_type
                })
                count += 1
            if cursor == 0 or count >= limit:
                break

        return jsonify({'keys': keys, 'total': len(keys)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/redis-admin/api/key/<path:key>')
def get_key_value(key):
    """Get value of a specific key"""
    try:
        r = get_redis_connection()
        key_type = r.type(key)

        if key_type == 'string':
            value = r.get(key)
        elif key_type == 'list':
            value = r.lrange(key, 0, -1)
        elif key_type == 'set':
            value = list(r.smembers(key))
        elif key_type == 'zset':
            value = r.zrange(key, 0, -1, withscores=True)
        elif key_type == 'hash':
            value = r.hgetall(key)
        else:
            value = None

        ttl = r.ttl(key)

        return jsonify({
            'key': key,
            'type': key_type,
            'value': value,
            'ttl': ttl
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/redis-admin/api/key', methods=['POST'])
def set_key_value():
    """Set value for a key"""
    try:
        data = request.json
        key = data.get('key')
        value = data.get('value')
        ttl = data.get('ttl', None)

        r = get_redis_connection()

        # Try to parse as JSON for complex types
        try:
            parsed_value = json.loads(value)
            if isinstance(parsed_value, dict):
                # Set as hash
                r.hset(key, mapping=parsed_value)
            elif isinstance(parsed_value, list):
                # Set as list
                r.delete(key)
                r.rpush(key, *parsed_value)
            else:
                # Set as string
                r.set(key, value)
        except (json.JSONDecodeError, TypeError):
            # Set as plain string
            r.set(key, value)

        if ttl:
            r.expire(key, int(ttl))

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/redis-admin/api/key/<path:key>', methods=['DELETE'])
def delete_key(key):
    """Delete a key"""
    try:
        r = get_redis_connection()
        result = r.delete(key)
        return jsonify({'success': True, 'deleted': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/redis-admin/api/execute', methods=['POST'])
def execute_command():
    """Execute a Redis command"""
    try:
        data = request.json
        command = data.get('command', '').strip()

        if not command:
            return jsonify({'error': 'No command provided'}), 400

        # Parse command and arguments
        parts = command.split()
        cmd = parts[0].upper()
        args = parts[1:] if len(parts) > 1 else []

        # Block dangerous commands in production
        dangerous_commands = ['FLUSHALL', 'FLUSHDB', 'CONFIG', 'SHUTDOWN', 'BGREWRITEAOF', 'BGSAVE', 'SAVE']
        if cmd in dangerous_commands and os.environ.get('REDIS_ADMIN_SAFE_MODE', 'false').lower() == 'true':
            return jsonify({'error': f'Command {cmd} is blocked in safe mode'}), 403

        r = get_redis_connection()

        # Execute command
        result = r.execute_command(cmd, *args)

        # Format result for display
        if isinstance(result, bytes):
            result = result.decode('utf-8')

        return jsonify({'result': result, 'command': command})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/redis-admin/api/flush-db', methods=['POST'])
def flush_db():
    """Flush current database"""
    try:
        r = get_redis_connection()
        r.flushdb()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/redis-admin/api/flush-all', methods=['POST'])
def flush_all():
    """Flush all databases"""
    try:
        r = get_redis_connection()
        r.flushall()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/redis-admin/health')
def health_check():
    """Health check endpoint"""
    try:
        r = get_redis_connection()
        r.ping()
        return jsonify({'status': 'healthy', 'redis': 'connected'})
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('REDIS_ADMIN_PORT', 8888))
    debug = os.environ.get('REDIS_ADMIN_DEBUG', 'false').lower() == 'true'

    print(f"Starting Redis Admin on port {port}")
    print(f"Redis connection: {REDIS_HOST}:{REDIS_PORT} DB:{REDIS_DB}")

    app.run(host='0.0.0.0', port=port, debug=debug)