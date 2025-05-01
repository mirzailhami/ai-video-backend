import boto3
from ..logging_config import s3_service_logger as logger
from fastapi import HTTPException
from ..config import settings

class S3Service:
    def __init__(self, bucket: str):
        """Initialize S3 service with the specified bucket.

        Args:
            bucket (str): The S3 bucket name.
        """
        self.bucket = bucket
        self.client = boto3.client("s3", region_name=settings.aws_region)

    async def upload_image_to_s3(self, file_path: str, object_name: str) -> str:
        """Upload an image to S3 and return its public URL.

        Args:
            file_path (str): Local path to the image file.
            object_name (str): S3 object key.

        Returns:
            str: Public URL of the uploaded image.

        Raises:
            HTTPException: If the upload fails.
        """
        try:
            self.client.upload_file(
                file_path,
                self.bucket,
                object_name,
                ExtraArgs={"ContentType": "image/png"}
            )
            url = f"https://{self.bucket}.s3.amazonaws.com/{object_name}"
            logger.debug(f"Uploaded image to S3: {url}")
            return url
        except Exception as e:
            logger.error(f"S3 upload error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"S3 upload error: {str(e)}")

    async def upload_file(self, file_path: str, object_name: str) -> str:
        """Upload a file (e.g., video) to S3 and return its public URL.

        Args:
            file_path (str): Local path to the file.
            object_name (str): S3 object key.

        Returns:
            str: Public URL of the uploaded file.

        Raises:
            HTTPException: If the upload fails.
        """
        try:
            content_type = "video/mp4" if object_name.endswith(".mp4") else "application/octet-stream"
            self.client.upload_file(
                file_path,
                self.bucket,
                object_name,
                ExtraArgs={"ContentType": content_type}
            )
            url = f"https://{self.bucket}.s3.amazonaws.com/{object_name}"
            logger.debug(f"Uploaded file to S3: {url}")
            return url
        except Exception as e:
            logger.error(f"S3 upload error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"S3 upload error: {str(e)}")

    async def delete_file(self, object_name: str) -> None:
        """Delete a file from S3.

        Args:
            object_name (str): S3 object key.

        Raises:
            HTTPException: If the deletion fails.
        """
        try:
            self.client.delete_object(Bucket=self.bucket, Key=object_name)
            logger.debug(f"Deleted file from S3: {object_name}")
        except Exception as e:
            logger.error(f"S3 delete error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"S3 delete error: {str(e)}")

    async def object_exists(self, object_name: str) -> bool:
        """Check if an object exists in the S3 bucket.

        Args:
            object_name (str): S3 object key.

        Returns:
            bool: True if the object exists, False otherwise.
        """
        try:
            self.client.head_object(Bucket=self.bucket, Key=object_name)
            logger.debug(f"Object exists in S3: {object_name}")
            return True
        except self.client.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "404":
                logger.debug(f"Object does not exist in S3: {object_name}")
                return False
            logger.error(f"S3 head object error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"S3 head object error: {str(e)}")