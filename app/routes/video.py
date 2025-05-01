from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import List
import json
import time
import tempfile
import os
import aiohttp
from ..services.video_service import get_video_service, VideoGenerationService
from ..models.slide import Scene
from ..logging_config import video_logger as logger
from ..config import settings  # Import settings to access heygen_api_key

router = APIRouter()

@router.post("/generate")
async def generate_video(
    scenes: str = Form(...),
    logo: UploadFile = File(...),
    voice_id: str = Form(...),
    avatar_id: str = Form(...),
    title: str = Form(...)
):
    """Generate a video from scenes using HeyGen API."""
    start_time = time.time()  # Use time.time() to record the start time
    logo_path = None
    try:
        # Parse and validate scenes
        scenes_list = json.loads(scenes)
        if not isinstance(scenes_list, list):
            raise ValueError("Scenes must be a list")
        validated_scenes = [Scene(**scene) for scene in scenes_list]
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Invalid scenes data: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid scenes data: {str(e)}")

    # Save the uploaded logo to a temporary file
    try:
        # Create a temporary file to store the logo
        suffix = os.path.splitext(logo.filename or 'logo.png')[1] or '.png'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            logo_path = temp_file.name
            # Read the uploaded file and write to the temporary file
            content = await logo.read()
            temp_file.write(content)
        logger.debug(f"Saved logo to temporary file: {logo_path}")
    except Exception as e:
        logger.error(f"Failed to save logo to temporary file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save logo: {str(e)}")

    video_service = get_video_service()
    try:
        video_url, duration, thumbnail_url, status, video_id = await video_service.generate_video(
            validated_scenes, logo_path, voice_id, avatar_id, title
        )
        return {"video_url": video_url, "duration": duration, "thumbnail_url": thumbnail_url, "status": status, "video_id": video_id}
    except Exception as e:
        logger.error(f"Video generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Video generation failed: {str(e)}")
    finally:
        # Clean up the temporary logo file
        if logo_path and os.path.exists(logo_path):
            try:
                os.remove(logo_path)
                logger.debug(f"Cleaned up temporary logo file: {logo_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary logo file {logo_path}: {str(e)}")
        logger.info(f"Video generation endpoint completed in {time.time() - start_time:.2f} seconds")

@router.get("/status/{video_id}")
async def get_video_status(video_id: str):
    """Get the current status of a video by its video_id."""
    video_service = get_video_service()
    try:
        video_url, duration, thumbnail_url, status, video_id, created_at = await video_service.poll_video_status(video_id)
        return {
            "video_url": video_url,
            "duration": duration,
            "thumbnail_url": thumbnail_url,
            "status": status,
            "video_id": video_id,
            "created_at": created_at
        }
    except Exception as e:
        logger.error(f"Failed to fetch video status for video_id {video_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch video status: {str(e)}")

@router.get("/list")
async def list_videos():
    """Fetch the list of videos from HeyGen API."""
    url = "https://api.heygen.com/v1/video.list?limit=50"
    headers = {
        "accept": "application/json",
        "x-api-key": settings.heygen_api_key
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch video list from HeyGen: {response.status} - {await response.text()}")
                    raise HTTPException(status_code=response.status, detail="Failed to fetch video list from HeyGen")
                data = await response.json()
                return data
    except Exception as e:
        logger.error(f"Failed to fetch video list from HeyGen: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch video list from HeyGen: {str(e)}")
    
@router.get("/voices")
async def list_voices():
    """Fetch the list of voices from HeyGen API."""
    url = "https://api.heygen.com/v2/voices"
    headers = {
        "accept": "application/json",
        "x-api-key": settings.heygen_api_key
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch voices list from HeyGen: {response.status} - {await response.text()}")
                    raise HTTPException(status_code=response.status, detail="Failed to fetch voices list from HeyGen")
                data = await response.json()
                return data
    except Exception as e:
        logger.error(f"Failed to fetch voices list from HeyGen: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch voices list from HeyGen: {str(e)}")
    
@router.get("/avatars")
async def list_avatars():
    """Fetch the list of avatar from HeyGen API."""
    url = "https://api.heygen.com/v2/avatars"
    headers = {
        "accept": "application/json",
        "x-api-key": settings.heygen_api_key
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch avatar list from HeyGen: {response.status} - {await response.text()}")
                    raise HTTPException(status_code=response.status, detail="Failed to fetch avatar list from HeyGen")
                data = await response.json()
                return data
    except Exception as e:
        logger.error(f"Failed to fetch avatar list from HeyGen: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch avatar list from HeyGen: {str(e)}")