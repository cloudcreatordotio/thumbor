# Thumbor Azure Web App Container

This is a single-container implementation of Thumbor image processing service optimized for Azure Web App deployment. It combines Thumbor 7.8.0, Nginx caching proxy, Redis, and RemoteCV into a single container managed by Supervisord.

## Features

- **Thumbor 7.8.0**: Latest stable version with security fixes, improved performance and features
- **Azure Blob Storage Integration**: Native support for loading images from Azure Blob Storage with SAS tokens
- **Nginx Caching Proxy**: High-performance caching layer with configurable cache sizes
- **Redis**: Internal Redis server for storage and queueing
- **RemoteCV**: Computer vision service for smart cropping and face detection
- **Supervisord**: Process management ensuring all services run reliably
- **Azure Web App Ready**: Configured for Azure's PORT environment variable
- **Auto-WebP**: Automatic WebP conversion for supported browsers
- **CORS Support**: Configurable CORS headers for cross-domain requests
- **Multiplatform Support**: Build for linux/amd64 and linux/arm64 architectures

## Architecture

```
┌─────────────────────────────────────────────┐
│           Azure Web App Container           │
├─────────────────────────────────────────────┤
│                 Supervisord                 │
├──────┬──────────┬─────────┬────────────────┤
│ Nginx│ Thumbor  │  Redis  │   RemoteCV     │
│ :80  │ :8001-4  │  :6379  │                │
└──────┴──────────┴─────────┴────────────────┘
```

## Azure Blob Storage Integration

This Thumbor implementation includes native Azure Blob Storage support, allowing you to process images stored in Azure Blob Storage without exposing SAS tokens in URLs.

### Key Features

- **Direct SDK Integration**: Uses Azure Storage SDK instead of HTTP requests
- **Multiple URL Formats**: Supports full Azure URLs, container/path format, and simple paths
- **SAS Token Handling**: Properly handles Azure URLs with SAS token query parameters
- **Authentication Methods**: Supports Connection String, Account Key, SAS Token, and Managed Identity
- **Smart Container Detection**: Configurable path prefixes for intelligent container resolution
- **HTTP Fallback**: Automatic fallback to HTTP loader for non-Azure URLs
- **Production Ready**: Tested with async/await and ThreadPoolExecutor for non-blocking performance

### Quick Example

```bash
# Process an image from Azure Blob Storage (using simple path)
curl "http://localhost:8080/unsafe/300x200/perm/rue/o/2020/366/image.jpg"

# Or with explicit container
curl "http://localhost:8080/unsafe/300x200/media/perm/rue/o/2020/366/image.jpg"

# Or with full Azure URL
curl "http://localhost:8080/unsafe/300x200/https://account.blob.core.windows.net/media/path/to/image.jpg"

# Regular HTTP URLs still work (automatic fallback)
curl "http://localhost:8080/unsafe/300x200/https://example.com/image.jpg"
```

## Quick Start

### Building the Container

```bash
# Build the Docker image (current platform only)
docker build -t thumbor:latest .

# Build for specific platform (e.g., linux/amd64 for Azure)
docker buildx build --platform linux/amd64 -t thumbor:latest --load .

# Build multiplatform and push to registry
docker buildx build --platform linux/amd64,linux/arm64 --push -t myregistry.azurecr.io/thumbor:v1.0.0 .
```

### Testing Locally

```bash
# Run the container locally
docker run -d \
  --name thumbor \
  -p 8080:80 \
  -e THUMBOR_NUM_PROCESSES=4 \
  -e SECURITY_KEY=your-secure-key \
  -e ALLOW_UNSAFE_URL=False \
  thumbor:latest

# Test the health endpoint
curl http://localhost:8080/healthcheck

# Process an image (unsafe URL for testing only)
curl http://localhost:8080/unsafe/300x200/smart/https://via.placeholder.com/600x400
```

## Multiplatform Build Support

Multiplatform Docker images are built using Docker buildx, enabling seamless development on ARM-based Macs while deploying to linux/amd64 Azure environments.

### Prerequisites

- Docker Desktop with buildx support (included in Docker Desktop 19.03+)
- Azure CLI (for pushing to ACR)

### Common Use Cases

#### Development on ARM Mac for Azure Deployment

When developing on an ARM-based Mac (Apple Silicon) but deploying to Azure (linux/amd64):

```bash
# For local development (builds for ARM, fast)
docker build -t thumbor:latest .

# For testing Azure compatibility locally
docker buildx build --platform linux/amd64 -t thumbor:latest --load .

# For deployment to Azure
docker buildx build --platform linux/amd64,linux/arm64 --push -t myregistry.azurecr.io/thumbor:production .
```

#### Building for Multiple Platforms

```bash
# Build for both ARM and x86_64
# Note: Multiplatform images can only be pushed to a registry, not loaded into local Docker
docker buildx build --platform linux/amd64,linux/arm64 --push -t myregistry.azurecr.io/thumbor:latest .
```

#### CI/CD Pipeline Example

```bash
# In your Azure DevOps or GitHub Actions pipeline
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --push \
  --no-cache \
  -t $ACR_NAME.azurecr.io/thumbor:$BUILD_NUMBER .
```

### Docker Buildx Builder Management

Use a dedicated buildx builder for multiplatform builds:

```bash
# Create and use the builder (one-time setup)
docker buildx create --name thumbor-multiplatform --use

# View the builder status
docker buildx ls | grep thumbor-multiplatform

# Remove the builder if needed
docker buildx rm thumbor-multiplatform
```

### Platform-Specific Considerations

#### ARM Development (Apple Silicon Macs)
- Local builds are fast and native
- Use `--platform linux/amd64` to test Azure compatibility
- Container may run slower when emulating x86_64

#### Azure Deployment (linux/amd64)
- Azure Web Apps typically run on linux/amd64
- Use a multiplatform `docker buildx build --push` for production deployments
- Images built on ARM will work seamlessly on Azure

#### Docker Compose Support

For docker-compose deployments, specify the platform in your `docker-compose.yml`:

```yaml
services:
  thumbor:
    build:
      context: .
      dockerfile: Dockerfile
      platform: linux/amd64  # For Azure compatibility
```

## Azure Deployment

### Prerequisites

1. Azure CLI installed and logged in
2. Azure Container Registry (ACR) created
3. Azure Web App for Containers created

### Step 1: Build and Push to ACR

```bash
# Set your ACR name
ACR_NAME=mycontainerregistry

# Login to ACR
az acr login --name $ACR_NAME

# Option 1: Build multiplatform image and push directly (RECOMMENDED)
# This ensures compatibility with Azure's linux/amd64 architecture
docker buildx build --platform linux/amd64,linux/arm64 --push -t $ACR_NAME.azurecr.io/thumbor:latest .

# Option 2: Build specific platform and push
docker buildx build --platform linux/amd64 --push -t $ACR_NAME.azurecr.io/thumbor:latest .

# Option 3: Build and push single platform (current architecture)
docker build -t thumbor:latest .
docker tag thumbor:latest $ACR_NAME.azurecr.io/thumbor:latest
docker push $ACR_NAME.azurecr.io/thumbor:latest
```

#### Cross-Platform Development Note

If you're developing on an ARM-based Mac (Apple Silicon) and deploying to Azure:
- Use a multiplatform `docker buildx build --push` to ensure the image works on Azure's linux/amd64 architecture
- Or explicitly specify `--platform linux/amd64` when building for Azure
- The multiplatform approach ensures compatibility across different architectures

### Step 2: Deploy to Azure Web App

```bash
# Set variables
RESOURCE_GROUP=myresourcegroup
WEBAPP_NAME=my-thumbor-app
ACR_NAME=mycontainerregistry

# Create Web App (if not exists)
az webapp create \
  --resource-group $RESOURCE_GROUP \
  --plan myappserviceplan \
  --name $WEBAPP_NAME \
  --deployment-container-image-name $ACR_NAME.azurecr.io/thumbor:latest

# Configure ACR credentials
az webapp config container set \
  --name $WEBAPP_NAME \
  --resource-group $RESOURCE_GROUP \
  --docker-custom-image-name $ACR_NAME.azurecr.io/thumbor:latest \
  --docker-registry-server-url https://$ACR_NAME.azurecr.io \
  --docker-registry-server-user $(az acr credential show --name $ACR_NAME --query username -o tsv) \
  --docker-registry-server-password $(az acr credential show --name $ACR_NAME --query passwords[0].value -o tsv)

# Set environment variables
az webapp config appsettings set \
  --resource-group $RESOURCE_GROUP \
  --name $WEBAPP_NAME \
  --settings \
    SECURITY_KEY="your-very-secure-random-key" \
    ALLOW_UNSAFE_URL="False" \
    THUMBOR_NUM_PROCESSES="4" \
    AUTO_WEBP="True" \
    CORS_ALLOW_ORIGIN="*" \
    THUMBOR_PROXY_CACHE_SIZE="100g" \
    THUMBOR_PROXY_CACHE_MEMORY_SIZE="1024m" \
    AZURE_STORAGE_ACCOUNT_NAME="mystorageaccount" \
    AZURE_USE_MANAGED_IDENTITY="True" \
    AZURE_STORAGE_DEFAULT_CONTAINER="media" \
    AZURE_KNOWN_PATH_PREFIXES="perm,temp,cache,uploads,files,documents,images"

# Note: For Azure Blob Storage authentication, use Managed Identity (recommended for production)
# or configure AZURE_STORAGE_ACCOUNT_KEY or AZURE_STORAGE_SAS_TOKEN
```

### Step 3: Configure Persistent Storage (Optional)

For persistent cache storage, mount Azure Storage:

```bash
# Create storage account
az storage account create \
  --name mythumborstorage \
  --resource-group $RESOURCE_GROUP \
  --sku Standard_LRS

# Create file share
az storage share create \
  --name thumbor-cache \
  --account-name mythumborstorage

# Mount to Web App
az webapp config storage-account add \
  --resource-group $RESOURCE_GROUP \
  --name $WEBAPP_NAME \
  --custom-id ThumboreCache \
  --storage-type AzureFiles \
  --share-name thumbor-cache \
  --account-name mythumborstorage \
  --mount-path /var/cache/nginx \
  --access-key $(az storage account keys list --account-name mythumborstorage --query [0].value -o tsv)
```

## Configuration

### Environment Variables

All configuration is done through environment variables. See `.env.azure` for the complete list.

Key variables:

#### General Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SECURITY_KEY` | Secret key for URL signing | CHANGE_THIS |
| `ALLOW_UNSAFE_URL` | Allow unsigned URLs | False |
| `THUMBOR_NUM_PROCESSES` | Number of Thumbor workers | 4 |
| `AUTO_WEBP` | Auto-convert to WebP | True |
| `CORS_ALLOW_ORIGIN` | CORS allowed origins | * |
| `THUMBOR_PROXY_CACHE_SIZE` | Nginx cache size | 100g |

#### Azure Blob Storage Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `AZURE_STORAGE_ACCOUNT_NAME` | Azure Storage account name | - |
| `AZURE_STORAGE_CONNECTION_STRING` | Connection string (highest priority) | - |
| `AZURE_STORAGE_ACCOUNT_KEY` | Account key for authentication | - |
| `AZURE_STORAGE_SAS_TOKEN` | SAS token for authentication | - |
| `AZURE_USE_MANAGED_IDENTITY` | Use Managed Identity (recommended for Azure) | False |
| `AZURE_STORAGE_DEFAULT_CONTAINER` | Default container for blob paths | media |
| `AZURE_KNOWN_PATH_PREFIXES` | Comma-separated known path prefixes | perm,temp,cache,uploads,files,documents,images |

### URL Signing

For production, always use signed URLs:

```python
import hashlib
import base64

def generate_thumbor_url(security_key, image_url, width, height):
    # Example URL generator
    path = f"{width}x{height}/smart/{image_url}"
    hash = hashlib.md5((security_key + path).encode()).digest()
    signature = base64.urlsafe_b64encode(hash).decode().strip("=")
    return f"/{signature}/{path}"
```

## Performance Tuning

### For High Traffic

```bash
# Increase workers and cache
az webapp config appsettings set \
  --resource-group $RESOURCE_GROUP \
  --name $WEBAPP_NAME \
  --settings \
    THUMBOR_NUM_PROCESSES="8" \
    ENGINE_THREADPOOL_SIZE="20" \
    HTTP_LOADER_MAX_CONN_PER_HOST="50" \
    THUMBOR_PROXY_CACHE_MEMORY_SIZE="2048m"
```

### Scaling

```bash
# Enable autoscaling
az monitor autoscale create \
  --resource-group $RESOURCE_GROUP \
  --resource $WEBAPP_NAME \
  --resource-type Microsoft.Web/serverFarms \
  --min-count 1 \
  --max-count 10 \
  --count 2

# Add CPU-based rule
az monitor autoscale rule create \
  --resource-group $RESOURCE_GROUP \
  --autoscale-name my-autoscale \
  --condition "Percentage CPU > 70 avg 5m" \
  --scale out 1
```

## Monitoring

### Application Insights

```bash
# Enable Application Insights
az webapp config appsettings set \
  --resource-group $RESOURCE_GROUP \
  --name $WEBAPP_NAME \
  --settings APPINSIGHTS_INSTRUMENTATIONKEY="your-key"
```

### View Logs

```bash
# Stream logs
az webapp log tail \
  --resource-group $RESOURCE_GROUP \
  --name $WEBAPP_NAME

# Download logs
az webapp log download \
  --resource-group $RESOURCE_GROUP \
  --name $WEBAPP_NAME \
  --log-file logs.zip
```

### Health Checks

- Health endpoint: `https://your-app.azurewebsites.net/healthcheck`
- Nginx status: `https://your-app.azurewebsites.net/nginx-status`

## Redis Admin Interface

The container includes a built-in web-based Redis administration interface for managing and monitoring the Redis instance.

### Accessing Redis Admin

| Environment | URL |
|-------------|-----|
| **Local Development** | `http://localhost:8080/redis-admin` |
| **Azure Web App** | `https://your-app.azurewebsites.net/redis-admin` |
| **Docker (Custom Port)** | `http://localhost:[PORT]/redis-admin` |

### Features

- **Dashboard**: Real-time Redis statistics, memory usage, and connected clients
- **Key Browser**: Search and manage keys with pattern matching
- **Command Executor**: Execute Redis commands directly from the web interface
- **Key Editor**: Create and modify keys with JSON support
- **TTL Management**: Set and modify key expiration times
- **Danger Zone**: Database flush operations (use with caution!)

### Security

For production environments, enable basic authentication:

```bash
# SSH into Azure Web App
az webapp ssh --name $WEBAPP_NAME --resource-group $RESOURCE_GROUP

# Run authentication setup
/app/setup_redis_admin_auth.sh

# Follow prompts to set username and password
# Restart nginx to apply changes
supervisorctl restart nginx
```

For Azure deployments, also consider:
- Using App Service access restrictions to limit Redis Admin access
- Implementing Azure Private Endpoints for network isolation
- Setting up Azure AD authentication for the Web App

## Redis Storage Configuration

### Understanding Redis Usage in Thumbor

This Thumbor implementation uses a **mixed storage** approach where Redis is used selectively for specific operations:

#### Storage Types by Operation

| Operation Type | Storage Location | Redis Activity |
|---------------|-----------------|----------------|
| **Regular Image Operations** | File Storage | ❌ No |
| **Detection Results** | Redis | ✅ Yes |
| **Processed Images Cache** | None (generated on-demand) | ❌ No |

#### Operations That DO NOT Use Redis

Regular image transformations are processed on-the-fly and don't interact with Redis:
- `/unsafe/fit-in/...` - Basic resize operations
- `/unsafe/300x200/...` - Fixed dimension resizing
- `/unsafe/crop/...` - Manual cropping
- Standard filters (blur, brightness, contrast, etc.)

#### Operations That USE Redis

Detection-based operations store their results in Redis for caching:
- `/unsafe/.../smart/...` - Smart cropping (face/feature detection)
- `/unsafe/.../filters:face()/...` - Face detection
- `/unsafe/.../filters:focal()/...` - Focal point detection

#### Example Redis Detection Storage

When requesting a smart crop:
```
http://localhost:8080/unsafe/300x300/smart/media.example.com/path/to/image.png
```

Redis stores the detection results with key:
```
thumbor-detector-media.example.com/path/to/image.png
```

Containing focal points and regions data:
```json
[
  {"x": 284.5, "y": 142.5, "height": 285, "width": 285, "z": 81225},
  {"x": 246.0, "y": 111.0, "height": 46, "width": 46, "z": 2116}
]
```

#### Monitoring Redis Activity

To see Redis activity in real-time:

```bash
# Terminal 1 - Monitor Redis
docker exec thumbor-dev redis-cli monitor

# Terminal 2 - Make a SMART request (will show Redis activity)
curl "http://localhost:8080/unsafe/300x300/smart/your-image-url"

# Terminal 2 - Make a FIT-IN request (won't show Redis activity)
curl "http://localhost:8080/unsafe/fit-in/300x300/your-image-url"
```

#### Configuration Details

The storage configuration in `thumbor.conf`:
```python
# Mixed storage configuration
Config.STORAGE = 'thumbor.storages.mixed_storage'
Config.MIXED_STORAGE_FILE_STORAGE = 'thumbor.storages.file_storage'
Config.MIXED_STORAGE_DETECTOR_STORAGE = 'tc_redis.storages.redis_storage'

# No result caching (images generated on-demand)
Config.RESULT_STORAGE = 'thumbor.result_storages.no_storage'
```

This configuration optimizes performance by:
- Caching expensive detection operations in Redis
- Serving regular transformations directly without Redis overhead
- Reducing Redis memory usage by not storing processed images

## CDN Integration

For better performance, use Azure CDN:

```bash
# Create CDN profile
az cdn profile create \
  --resource-group $RESOURCE_GROUP \
  --name mycdnprofile \
  --sku Standard_Microsoft

# Create CDN endpoint
az cdn endpoint create \
  --resource-group $RESOURCE_GROUP \
  --profile-name mycdnprofile \
  --name mycdnendpoint \
  --origin $WEBAPP_NAME.azurewebsites.net \
  --origin-host-header $WEBAPP_NAME.azurewebsites.net
```

## Troubleshooting

### Container won't start

1. Check logs: `az webapp log tail --resource-group $RESOURCE_GROUP --name $WEBAPP_NAME`
2. Verify environment variables are set correctly
3. Ensure the container image is accessible from ACR

### Images not loading

1. Check ALLOWED_SOURCES configuration
2. Verify CORS settings if loading from different domain
3. Check Nginx cache permissions

### Performance issues

1. Increase THUMBOR_NUM_PROCESSES
2. Scale up the App Service Plan
3. Enable Application Insights for detailed metrics

### Multiplatform build issues

#### "Cannot load multiple platforms locally" error
- This occurs when trying to load multiple platforms to local Docker
- Solution: Use `--push` to push to a registry instead, or build for a single platform

#### Build fails on different architecture
- Ensure all base images support your target platforms
- The Ubuntu 22.04 base image supports both linux/amd64 and linux/arm64

#### Slow performance when emulating different architecture
- Running linux/amd64 containers on ARM Macs uses emulation
- This is normal and only affects local testing, not production performance

#### Buildx builder not found
- The script automatically creates the builder if it doesn't exist
- To manually create: `docker buildx create --name thumbor-multiplatform --use`
- To remove and recreate: `docker buildx rm thumbor-multiplatform`

## Migration from Multi-Container Setup

This single container replaces the previous multi-container setup with these mappings:

| Old Service | New Implementation | Notes |
|-------------|-------------------|-------|
| thumbor:7.7.7 | thumbor:7.8.0 | Upgraded version |
| nginx-proxy | Internal Nginx | Integrated caching |
| remotecv | Internal RemoteCV | Same functionality |
| External Redis | Internal Redis | No external dependency |

### Host Mappings

The previous `extra_hosts` entries should be handled via:
1. Azure Private Endpoints for internal resources
2. Azure DNS for custom domain resolution
3. Application Gateway for advanced routing

## Security Best Practices

1. **Always use signed URLs in production** - Set `ALLOW_UNSAFE_URL=False`
2. **Use strong security keys** - Generate with `openssl rand -hex 32`
3. **Restrict ALLOWED_SOURCES** - Only allow your domains
4. **Enable HTTPS only** - Configure in Azure Portal
5. **Use managed identity** - For ACR authentication
6. **Regular updates** - Rebuild container with latest security patches

## Support

For issues or questions:
1. Check container logs: `docker logs <container-id>`
2. Review Azure Web App diagnostics
3. Check Thumbor documentation: https://thumbor.readthedocs.io
4. Review Azure documentation: https://docs.microsoft.com/azure/app-service/

## License

Copyright (c) 2025-2026 Matthew Williams

This project is licensed under the MIT License — see the [LICENSE](./LICENSE)
file for the full text (SPDX: `MIT`).

This implementation uses open-source components, each under its own license:
- Thumbor: MIT License
- Nginx: 2-clause BSD License
- Redis: BSD License
- RemoteCV: MIT License