# TestCraft API

TestCraft API provides a REST API to generate test ideas and automation code for different frameworks and languages using the OpenAI models.

## Running the server

Here you will find instructions to run the API in your infrastructure. 
The instructions are for GCP using Google Cloud Run service, but you could deploy the API to any cloud provider that supports running Docker images. 
For example:
- Azure Container Instances (ACI)
- AWS Fargate

### Prerequisites  

Before you begin, ensure you have met the following requirements:

- You have a Google Cloud account.
- You have created a project in Google Cloud
- You have installed the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install).
- You have authenticated the Google Cloud SDK with your Google account and set the project ID (run `gcloud auth login` and `gcloud config set project PROJECT_ID`).  

### Building the Docker Image  

1. Open your preferred Terminal application.
2. Run the following command to submit a build to Google Cloud Build (replace `PROJECT_ID` with your Google Cloud Project ID):

    ```bash
    gcloud builds submit --tag gcr.io/PROJECT_ID/openai-api-proxy
    ```

    This command builds a Docker image using the Dockerfile in the current directory and pushes it to the Google Container Registry of your Google Cloud Project.  

### Deploying the API  

After building the Docker image, you can deploy it to Google Cloud Run with the following command (replace `PROJECT_ID` with your Google Cloud Project ID):

```bash
gcloud run deploy --image gcr.io/PROJECT_ID/openai-api-proxy --platform managed
```

This command creates a new service on Google Cloud Run using the Docker image from the previous step. 
It will request two details, enter the following:
- Service name: testcraft-api
- Region: us-Central1 (29)  

After deploying the service, Google Cloud Run will provide a URL to access the API.

## Contributing
Contributions to this project are welcome! If you find any issues or have suggestions for improvements, please open an issue or submit a pull request on the project's repository.

## License
TestCraft API is licensed under MIT License, and its use is subject to the terms and conditions stated in the license agreement.
