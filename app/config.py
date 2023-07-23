import logging as dev_logging
import os

from google.cloud import logging, secretmanager

from dotenv import load_dotenv

load_dotenv()

class Config:

    @staticmethod
    def get_secret(project_id, secret_name):
        client = secretmanager.SecretManagerServiceClient()
        secret_version_path = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        secret_version = client.access_secret_version(
            request={"name": secret_version_path})
        secret_value = secret_version.payload.data.decode("UTF-8")
        return secret_value

    PROJECT_ID = os.environ.get("PROJECT_ID")
    ENVIRONMENT = os.environ.get("FLASK_ENV", "production")
    API_KEY = os.environ.get("OPENAI_API_KEY")
    LOG_NAME = "openai-api-proxy-log"

    if ENVIRONMENT != "local":
        API_KEY = get_secret(PROJECT_ID, "openai-api-key")
        logging_client = logging.Client()
        logger = logging_client.logger(LOG_NAME)
    
    if ENVIRONMENT != "production":
        LOG_LEVEL = dev_logging.DEBUG
        LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        LOG_FILENAME = 'app.log'
        logger = dev_logging.getLogger(LOG_NAME)
