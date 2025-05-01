from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    aws_region: str = "us-east-1"
    bedrock_claude_model_id: str
    bedrock_stability_model_id: str
    heygen_api_key: str
    openai_api_key: str = ""
    gemini_api_key: str = ""
    synthesia_api_key: str = ""
    upload_dir: str
    image_dir: str
    s3_bucket: str
    frontend_url: str = "http://localhost:3000"
    backend_url: str = "http://localhost:8000"

    class Config:
        env_file = Path(__file__).parent.parent / ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

settings = Settings()