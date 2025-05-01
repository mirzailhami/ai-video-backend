import boto3
import copy
from botocore.exceptions import ClientError
from fastapi import HTTPException
from ..config import settings
from ..models.slide import SlideData, Scene
from .image_service import get_image_service
from typing import List
import json
from ..logging_config import llm_service_logger as logger
import os
import asyncio
from datetime import datetime

BASE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

class VisionLLMService:
    def __init__(self):
        """Initialize the Vision LLM service with AWS Bedrock client."""
        self.client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        self.image_service = get_image_service("stability")

    async def generate_scenes(self, slides: List[SlideData]) -> List[Scene]:
        """Generate scenes from slides using AWS Bedrock for script and image prompts."""
        model_id = settings.bedrock_claude_model_id
        start_time = datetime.now()
        logger.debug("Starting scene generation for slides")
        try:
            # Build prompt
            has_images = any(slide.images for slide in slides)
            prompt = (
                "You are a Vision-capable LLM for a PowerPoint-to-video conversion tool. Based on the provided slide data, generate exactly one scene per slide. "
                "Each scene must include:\n"
                "- A 'script' (1–2 sentences, 20–50 words) for narration, summarizing the slide's title, text, and key table data (if present) in a professional, engaging tone.\n"
                "- An 'image_prompt' (20–50 words) that will be used with Stable-Diffusion-XL to create a visually appealing background image that directly represents the slide's content"
                f"{', incorporating visual elements from content images (e.g., charts, icons) and logos (branding elements, if present, anywhere on the slide)' if has_images else ''}.\n"
                f"{'Analyze the provided images and logos (via metadata and attached images). Use logos for branding context and content images for narrative alignment.' if has_images else ''}\n"
                "Return the scenes as a JSON array of objects with exactly two fields: 'script' and 'image_prompt'. "
                "Ensure the response is valid JSON, enclosed in square brackets, with no additional text, markdown, or code fences. "
                "Example: [{\"script\": \"Narrator: Welcome to our AI strategy...\", \"image_prompt\": \"A futuristic tech office with a logo...\"}]"
                "\n\nSlides:\n"
            )
            for idx, slide in enumerate(slides):
                images_info = [f"{'Logo' if img['is_logo'] else 'Image'} at {img['path']} (Format: {img['format']}, Size: {img['size']} bytes)" for img in slide.images] if has_images else []
                prompt += (
                    f"Slide {idx + 1}:\n"
                    f"Title: {slide.title}\n"
                    f"Text: {slide.text.strip() or 'None'}\n"
                    f"Images/Logos: {images_info or 'None'}\n"
                    f"Tables: {json.dumps(slide.tables) if slide.tables else 'None'}\n\n"
                )

            # Build messages
            logger.debug("Building messages")
            try:
                messages = [{"role": "user", "content": [{"text": prompt}]}]
                images_processed = False
                for slide_idx, slide in enumerate(slides):
                    for img in slide.images:
                        img_path = os.path.join(BASE_PATH, img["path"])
                        if not os.path.exists(img_path):
                            logger.warning(f"Image file not found: {img_path}")
                            continue
                        try:
                            with open(img_path, "rb") as f:
                                img_data = f.read()
                            # Use format and size from ppt_parser
                            file_ext = img_path.split('.')[-1].lower()
                            image_content = {
                                "image": {
                                    "format": self._normalize_image_format(file_ext),
                                    "source": {"bytes": img_data}
                                }
                            }
                            messages[0]["content"].append(image_content)
                            images_processed = True
                            logger.debug(f"Appended image {img_path}: Format {img['format']}, Size {img['size']} bytes, Slide {slide_idx + 1}")
                        except Exception as e:
                            logger.warning(f"Failed to process image {img_path}: {str(e)} (type: {type(e).__name__})")
                            continue
                # Fallback prompt if no images processed
                if not images_processed and has_images:
                    logger.warning("No images were successfully processed; rebuilding prompt without image references")
                    prompt = (
                        "You are a Vision-capable LLM for a PowerPoint-to-video conversion tool. Based on the provided slide data, generate exactly one scene per slide. "
                        "Each scene must include:\n"
                        "- A 'script' (1–2 sentences, 20–50 words) for narration, summarizing the slide's title, text, and key table data (if present) in a professional, engaging tone.\n"
                        "- An 'image_prompt' (20–50 words) for a visually appealing background image that reflects the slide's content.\n"
                        "Return the scenes as a JSON array of objects with exactly two fields: 'script' and 'image_prompt'. "
                        "Example: [{\"script\": \"Narrator: Welcome to our AI strategy...\", \"image_prompt\": \"A futuristic tech office...\"}]"
                        "\n\nSlides:\n"
                    )
                    for idx, slide in enumerate(slides):
                        prompt += (
                            f"Slide {idx + 1}:\n"
                            f"Title: {slide.title}\n"
                            f"Text: {slide.text.strip() or 'None'}\n"
                            f"Images/Logos: None\n"
                            f"Tables: {json.dumps(slide.tables) if slide.tables else 'None'}\n\n"
                        )
                    messages = [{"role": "user", "content": [{"text": prompt}]}]
                # Log messages safely
                try:
                    log_messages = [
                        {
                            "role": m["role"],
                            "content": [
                                {"text": c["text"]} if "text" in c else
                                {"image": {"format": c["image"]["format"], "source": {"bytes": "<bytes>"}}}
                                for c in m["content"]
                            ]
                        }
                        for m in messages
                    ]
                    logger.debug(f"Constructed messages: {json.dumps(log_messages, indent=2)}")
                except Exception as e:
                    logger.error(f"Failed to serialize messages for logging: {str(e)} (type: {type(e).__name__})")
            except Exception as e:
                logger.error(f"Failed to construct messages: {str(e)} (type: {type(e).__name__})")
                raise HTTPException(status_code=500, detail=f"LLM error: Failed to construct messages: {str(e)}")

            # Build payload
            logger.debug("Building payload")
            try:
                payload = {
                    "modelId": model_id,
                    "messages": messages,
                    "inferenceConfig": {"maxTokens": 1024, "temperature": 0.7, "topP": 0.9}
                }
                log_payload = copy.deepcopy(payload)
                for msg in log_payload["messages"]:
                    for content in msg["content"]:
                        if "image" in content and "source" in content["image"] and "bytes" in content["image"]["source"]:
                            content["image"]["source"]["bytes"] = "<image_bytes>"
                logger.debug(f"Sending payload to Bedrock: {json.dumps(log_payload, indent=2)}")
            except Exception as e:
                logger.error(f"Failed to construct payload: {str(e)} (type: {type(e).__name__})")
                raise HTTPException(status_code=500, detail=f"LLM error: Failed to construct payload: {str(e)}")

            # Call Bedrock
            logger.debug("Calling Bedrock")
            response = self.client.converse(**payload)
            response_text = response["output"]["message"]["content"][0]["text"]
            logger.debug(f"Received response from Bedrock: {response_text}")

            if not response_text:
                logger.error("LLM error: Empty response from Bedrock")
                raise HTTPException(status_code=500, detail="LLM error: Empty response from Bedrock")

            try:
                scenes_data = json.loads(response_text)
                if not isinstance(scenes_data, list):
                    logger.error("Expected a JSON array of scenes")
                    raise ValueError("Expected a JSON array of scenes")
                logger.debug(f"Parsed scenes data: {scenes_data}")
                scenes = []
                image_tasks = [self.image_service.generate_image(scene["image_prompt"]) for scene in scenes_data]
                image_paths = await asyncio.gather(*image_tasks, return_exceptions=True)
                for idx, (scene, image_path) in enumerate(zip(scenes_data, image_paths)):
                    if isinstance(image_path, Exception):
                        logger.warning(f"Image generation failed for Slide {idx + 1}: {str(image_path)}")
                        image_path = slides[idx].images[0]["path"] if idx < len(slides) and slides[idx].images else "assets/generated_image_default.png"
                        logger.debug(f"Using fallback for Slide {idx + 1}: {image_path}")
                    full_image_url = f"{settings.backend_url}/{image_path.lstrip('/')}"
                    scenes.append(
                        Scene(
                            script=scene["script"],
                            image_prompt=scene["image_prompt"],
                            image_path=full_image_url
                        )
                    )
                
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                logger.info(f"Scene generation completed. Model: {model_id}. Took {duration:.2f} seconds")
                return scenes
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error: {str(e)}")
                scenes_data = []
                slide_count = len(slides)
                sections = re.split(r'\n\s*\n', response_text.strip())
                for i in range(min(slide_count, len(sections))):
                    section = sections[i]
                    script_match = re.search(r'^(.*?)(?:Image Prompt:|\Z)', section, re.DOTALL)
                    script = script_match.group(1).strip() if script_match else f"Scene for slide {i + 1}"
                    image_prompt_match = re.search(r'Image Prompt:\s*(.*)', section, re.DOTALL)
                    image_prompt = image_prompt_match.group(1).strip() if image_prompt_match else f"Background for slide {i + 1}"
                    scenes_data.append({"script": script[:50], "image_prompt": image_prompt[:50]})
                if not scenes_data:
                    logger.error(f"Fallback parsing failed: {response_text}")
                    raise HTTPException(status_code=500, detail="LLM error: Could not parse scenes from text")
                logger.debug(f"Fallback scenes data: {scenes_data}")
                scenes = []
                image_tasks = [self.image_service.generate_image(scene["image_prompt"]) for scene in scenes_data]
                image_paths = await asyncio.gather(*image_tasks, return_exceptions=True)
                for idx, (scene, image_path) in enumerate(zip(scenes_data, image_paths)):
                    if isinstance(image_path, Exception):
                        logger.warning(f"Image generation failed for Slide {idx + 1}: {str(image_path)}")
                        image_path = slides[idx].images[0]["path"] if idx < len(slides) and slides[idx].images else "assets/generated_image_default.png"
                        logger.debug(f"Using fallback for Slide {idx + 1}: {image_path}")
                    scenes.append(
                        Scene(
                            script=scene["script"],
                            image_prompt=scene["image_prompt"],
                            image_path=image_path
                        )
                    )
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                logger.info(f"Fallback scene generation completed. Model: {model_id}. Took {duration:.2f} seconds")
                return scenes

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"]["Message"]
            logger.error(f"Bedrock ClientError: {error_code} - {error_message}")
            raise HTTPException(status_code=500, detail=f"LLM error: {error_code} - {error_message}")
        except Exception as e:
            logger.error(f"Unexpected LLM error: {str(e)} (type: {type(e).__name__})")
            raise HTTPException(status_code=500, detail=f"LLM error: {str(e)}")

    def _normalize_image_format(self, file_ext: str) -> str:
        # Normalize image format to match Bedrock's expected enum
        format_map = {
            "jpg": "jpeg",  # Convert "jpg" to "jpeg"
            "jpeg": "jpeg",
            "png": "png",
            "gif": "gif",
            "webp": "webp"
        }
        normalized_format = format_map.get(file_ext.lower(), "jpeg")  # Default to "jpeg" if unknown
        return normalized_format
def get_llm_service() -> VisionLLMService:
    """Get the Vision LLM service instance."""
    try:
        return VisionLLMService()
    except Exception as e:
        logger.error(f"Failed to initialize LLM service: {str(e)} (type: {type(e).__name__})")
        raise HTTPException(status_code=500, detail=f"Failed to initialize LLM service: {str(e)}")