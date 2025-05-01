from fastapi import APIRouter, Depends, Query, HTTPException, Body
from ..services.ppt_parser import parse_ppt
from ..services.llm_service import get_llm_service, VisionLLMService
from ..services.image_service import get_image_service, StabilityImageService
from ..models.slide import Scene
from typing import List
from pydantic import BaseModel
from ..logging_config import scenes_logger as logger
from ..config import settings

router = APIRouter()

class ImagePrompt(BaseModel):
    prompt: str

@router.post("/generate")
async def generate_scenes(file_path: str = Query(...), llm_service: VisionLLMService = Depends(get_llm_service)):
    logger.debug(f"Starting scene generation for file: {file_path}")
    try:
        slides_data = parse_ppt(file_path)
        logger.debug(f"Parsed slides: {len(slides_data)} slides")
        scenes = await llm_service.generate_scenes(slides_data)
        logger.info(f"Generated scenes for file: {file_path}")
        return {"scenes": [scene.dict() for scene in scenes]}
    except Exception as e:
        logger.error(f"Scene generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Scene generation error: {str(e)}")

@router.post("/generate_images")
async def generate_images(
    image_prompt: ImagePrompt = Body(...),
    image_service: StabilityImageService = Depends(get_image_service)
):
    logger.debug(f"Generating image for prompt: {image_prompt.prompt}")
    try:
        image_path = await image_service.generate_image(image_prompt.prompt)
        logger.info(f"Generated image for prompt: {image_prompt.prompt}")
        full_image_url = f"{settings.backend_url}/{image_path.lstrip('/')}"
        return {"image_path": full_image_url}
    except Exception as e:
        logger.error(f"Image generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Image generation error: {str(e)}")