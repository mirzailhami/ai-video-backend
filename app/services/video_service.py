import aiohttp
import os
import asyncio
import re
import time
import hashlib
from fastapi import HTTPException
from .base_service import VideoGenerationService
from .logo_service import LogoService
from .s3_service import S3Service
from ..config import settings
from ..models.slide import Scene
from typing import List, Tuple, Optional
from ..logging_config import video_service_logger as logger
from datetime import datetime
import traceback
from urllib.parse import urlparse, parse_qs
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Dynamic base path (backend/ directory)
BASE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

def log_before_sleep(retry_state):
    """Custom before_sleep callback for tenacity to log retries using loguru."""
    logger.debug(
        f"Retrying due to {retry_state.outcome.exception()}. "
        f"Attempt {retry_state.attempt_number}. "
        f"Waiting {retry_state.next_action.sleep} seconds before next attempt."
    )

class HeyGenVideoService(VideoGenerationService):
    def __init__(self):
        self.s3_service = S3Service(bucket=settings.s3_bucket)
        self.logo_service = LogoService()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(aiohttp.ClientResponseError),
        before_sleep=log_before_sleep
    )
    async def _fetch_video_status(self, session: aiohttp.ClientSession, video_id: str) -> dict:
        """Fetch video status with retry logic for transient errors."""
        async with session.get(
            f"https://api.heygen.com/v1/video_status.get?video_id={video_id}",
            headers={"X-Api-Key": settings.heygen_api_key}
        ) as response:
            if response.status != 200:
                error_detail = await response.text()
                logger.error(f"Video status check failed: {error_detail}")
                raise aiohttp.ClientResponseError(
                    status=response.status,
                    message=error_detail,
                    request_info=response.request_info,
                    history=response.history
                )
            result = await response.json()
            logger.debug(f"HeyGen video status response for video {video_id}: {result}")
            return result

    async def poll_video_status(self, video_id: str, timeout: int = 1200) -> Tuple[str, float, str, Optional[str], str, Optional[float]]:
        """Poll HeyGen API until video generation is complete, with timeout. Returns status, video_id, and created_at."""
        start_time = time.time()
        async with aiohttp.ClientSession() as session:
            while True:
                elapsed_time = time.time() - start_time
                if elapsed_time > timeout:
                    logger.error(f"Polling timeout after {timeout} seconds for video {video_id}")
                    raise HTTPException(status_code=504, detail=f"Video generation timed out after {timeout} seconds")

                try:
                    result = await self._fetch_video_status(session, video_id)
                except aiohttp.ClientResponseError as e:
                    logger.error(f"Failed to fetch video status after retries: {str(e)}")
                    raise HTTPException(status_code=500, detail=f"Video status check failed after retries: {str(e)}")

                status = result.get("data", {}).get("status")
                created_at = result.get("data", {}).get("created_at")  # Get the created_at timestamp
                progress = result.get("data", {}).get("progress", None)
                if status == "completed":
                    video_url = result.get("data", {}).get("video_url_caption")
                    duration = result.get("data", {}).get("duration")
                    thumbnail_url = result.get("data", {}).get("thumbnail_url")
                    if not video_url:
                        logger.error("No video_url_caption in completed status response")
                        raise HTTPException(status_code=500, detail="No video_url_caption returned")
                    if duration is None:
                        logger.error("No duration in completed status response")
                        raise HTTPException(status_code=500, detail="No duration returned")
                    if not thumbnail_url:
                        logger.warning("No thumbnail_url in completed status response")
                        thumbnail_url = ""
                    logger.debug(f"Video {video_id} completed: URL={video_url}, Duration={duration}, Thumbnail={thumbnail_url}")
                    return video_url, duration, thumbnail_url, "completed", video_id, created_at
                elif status in ["failed", "error"]:
                    error_msg = result.get("data", {}).get("error", "Unknown error")
                    logger.error(f"Video generation failed: {error_msg}")
                    raise HTTPException(status_code=500, detail=f"Video generation failed: {error_msg}")
                logger.debug(f"Video {video_id} status: {status}" + (f", Progress: {progress}%" if progress is not None else ""))
                return "", 0, "", status, video_id, created_at  # Return created_at even if not completed
                await asyncio.sleep(5)

    async def process_image_with_logo(self, scene: Scene, logo_path: str, index: int) -> tuple[str, str]:
        """Process a scene's image by adding a logo and uploading to S3, return URL and S3 key."""
        start_time = time.time()
        
        if not scene.image_path:
            logger.error(f"No image_path provided for scene {index}")
            raise HTTPException(status_code=400, detail=f"No image_path provided for scene {index}")

        parsed_url = urlparse(scene.image_path)
        path = parsed_url.path
        
        expected_prefix = "/generated_images/"
        if not path.startswith(expected_prefix):
            logger.error(f"Invalid image_path for scene {index}: {scene.image_path}. Must point to /generated_images/")
            raise HTTPException(status_code=400, detail=f"Invalid image_path for scene {index}: Must point to /generated_images/")

        file_name = path[len(expected_prefix):]
        if not file_name:
            logger.error(f"Invalid image_path for scene {index}: {scene.image_path}. No file name found")
            raise HTTPException(status_code=400, detail=f"Invalid image_path for scene {index}: No file name found")

        generated_images_dir = os.path.join(BASE_PATH, "generated_images")
        image_path = os.path.join(generated_images_dir, file_name)

        if not os.path.exists(image_path):
            logger.error(f"Image not found for scene {index}: {image_path}")
            raise HTTPException(status_code=500, detail=f"Image not found: {image_path}")

        with open(image_path, "rb") as f:
            image_hash = hashlib.md5(f.read()).hexdigest()
        with open(logo_path, "rb") as f:
            logo_hash = hashlib.md5(f.read()).hexdigest()
        original_name = os.path.splitext(os.path.basename(file_name))[0]
        s3_key = f"images/{image_hash}_{logo_hash}_logo_added.png"

        if await self.s3_service.object_exists(s3_key):
            s3_url = f"https://{settings.s3_bucket}.s3.amazonaws.com/{s3_key}"
            logger.debug(f"Reusing existing S3 image: {s3_url}")
            return s3_url, s3_key

        output_path = os.path.join("/tmp", f"{original_name}_logo_added.png")
        await self.logo_service.add_logo_to_image(image_path, logo_path, output_path)

        s3_url = await self.s3_service.upload_image_to_s3(output_path, s3_key)
        logger.debug(f"Uploaded image {output_path} to S3: {s3_url}")

        try:
            os.remove(output_path)
            logger.debug(f"Deleted temporary file: {output_path}")
        except Exception as e:
            logger.warning(f"Failed to delete temporary file {output_path}: {str(e)}")

        logger.info(f"Image processing for scene {index} took {time.time() - start_time:.2f} seconds")
        return s3_url, s3_key

    async def generate_video(self, scenes: List[Scene], logo_path: str, voice_id: str = "0a82bb7441ca46eb8ec3f20b88249ebe", avatar_id: str = "Abigail_expressive_2024112501", title: str = "") -> Tuple[str, float, str, Optional[str], str]:
        """Generate a video from a list of scenes using HeyGen API, return video URL, duration, thumbnail URL, status, and video_id."""
        start_time = datetime.now()
        logger.debug("Starting video generation")
        async with aiohttp.ClientSession() as session:
            try:
                if not scenes:
                    logger.error("No scenes provided for video generation")
                    raise HTTPException(status_code=400, detail="No scenes provided")
                for i, scene in enumerate(scenes[:5]):
                    if not isinstance(scene.script, str) or not scene.script.strip():
                        logger.error(f"Invalid or empty script for scene {i}: {scene.script}")
                        raise HTTPException(status_code=400, detail=f"Invalid or empty script for scene {i}")

                image_urls = {}
                image_s3_keys = []
                tasks = [self.process_image_with_logo(scene, logo_path, i) for i, scene in enumerate(scenes[:5])]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"Failed to process image for scene {i}: {str(result)}")
                        raise HTTPException(status_code=500, detail=f"Image processing error: {str(result)}")
                    image_urls[i], s3_key = result
                    image_s3_keys.append(s3_key)

                video_inputs = []
                for i, scene in enumerate(scenes[:5]):
                    video_input = {
                        "character": {
                            "type": "avatar",
                            "avatar_id": avatar_id,
                            "avatar_style": "normal"
                        },
                        "voice": {
                            "type": "text",
                            "input_text": scene.script,
                            "voice_id": voice_id,
                            "speed": 1.0,
                            "locale": "en-US",
                            "emotion": "Friendly"
                        },
                        "background": {
                            "type": "image",
                            "url": image_urls.get(i, "https://images.unsplash.com/photo-1567974772901-1365e616baa9")
                        }
                    }
                    video_inputs.append(video_input)
                logger.debug(f"Constructed video inputs: {video_inputs}")

                payload = {
                    "caption": True,
                    "video_inputs": video_inputs,
                    "dimension": {
                        "width": 1280,
                        "height": 720
                    },
                    "title": title
                }
                logger.debug(f"Payload sent to HeyGen: {payload}")

                async with session.post(
                    "https://api.heygen.com/v2/video/generate",
                    json=payload,
                    headers={
                        "X-Api-Key": settings.heygen_api_key,
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    }
                ) as response:
                    response_text = await response.text()
                    logger.debug(f"HeyGen API response: {response_text}")
                    if response.status != 200:
                        logger.error(f"HeyGen API error: Status {response.status}, Response: {response_text}")
                        raise HTTPException(status_code=500, detail=f"Video generation failed: {response_text}")
                    result = await response.json()
                    if result.get("error"):
                        error_code = result.get("error", {}).get("code", "Unknown")
                        error_msg = result.get("error", {}).get("message", "Unknown error")
                        logger.error(f"HeyGen API error: Code {error_code}, Message: {error_msg}")
                        raise HTTPException(status_code=500, detail=f"Video generation failed: {error_msg}")
                    video_id = result.get("data", {}).get("video_id")
                    if not video_id:
                        logger.error("No video_id returned from HeyGen API")
                        raise HTTPException(status_code=500, detail="No video_id returned from HeyGen API")

                    video_url, duration, thumbnail_url, status, _, created_at = await self.poll_video_status(video_id)

                    if status != "completed":
                        return video_url, duration, thumbnail_url, status, video_id

                    for s3_key in image_s3_keys:
                        await self.s3_service.delete_file(s3_key)
                        logger.debug(f"Deleted image from S3: {s3_key}")

                    end_time = datetime.now()
                    generation_duration = (end_time - start_time).total_seconds()
                    logger.info(f"Video generation completed: {video_url}. Duration: {duration} seconds. Took {generation_duration:.2f} seconds")
                    return video_url, duration, thumbnail_url, status, video_id
            except Exception as e:
                error_details = f"Video generation error: {str(e)}\nStack trace: {traceback.format_exc()}\nScenes: {scenes}\nVideo inputs: {locals().get('video_inputs', 'N/A')}"
                logger.error(error_details)
                raise HTTPException(status_code=500, detail=f"Video generation error: {str(e)}")

def get_video_service(provider: str = "heygen") -> VideoGenerationService:
    """Get the video generation service instance."""
    if provider == "heygen":
        return HeyGenVideoService()
    raise ValueError(f"Unsupported video provider: {provider}")