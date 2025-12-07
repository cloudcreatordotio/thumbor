# IMGMGR-THUMBOR image creation and deployment

## Login to Azure:

```
az login
```

## Login to the Container repository:

```
az acr login --name <your-registry>
```

## Build the docker image:

```
docker buildx build --no-cache --platform linux/amd64,linux/arm64 --push -t <your-registry>.azurecr.io/thumbor:latest .
```

(Running this for the first time might take a while, if you don't have buildx set up already)

This will deploy the image. You can check the repository in the Azure Portal (Container Registry -> your registry -> Repositories) to verify it is uploaded.

## To test locally:

```
docker compose --env-file .env.local up -d
```

## test request for Postman:

```
curl --location 'http://localhost:8080/unsafe/650x340/smart/filters:quality(90):format(jpeg):max_bytes(100000):strip_icc()/https%3A%2F%2Fmystorageaccount.blob.core.windows.net/media/path/to/image.jpg'

```

## To deploy the image:

1. Navigate to your Web App in the Azure Portal (App Services -> your app)

2. Navigate to **Deployment -> Deployment Center**

3. Click on **"main"**

4. Update the image tag to the tag of the image you just created.

5. Click **"Apply"**

6. Navigate to the **Overview** screen. For Container Image, you should see the updated image tag. Runtime status should say "Healthy"
