import boto3
import os
import base64
import json
import asyncio
from fastapi import HTTPException
from .base_service import ImageGenerationService
from ..config import settings
from ..logging_config import image_service_logger as logger

class StabilityImageService(ImageGenerationService):
    def __init__(self):
        self.client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        self.output_dir = settings.image_dir

    async def generate_image(self, prompt: str) -> str:
        """Generate an image using AWS Bedrock Stability model and save locally.

        Args:
            prompt (str): The prompt for image generation.

        Returns:
            str: Relative path to the generated image (e.g., 'generated_images/image_...png').

        Raises:
            HTTPException: If image generation fails after retries.
        """
        # Retry image generation up to 3 times
        for attempt in range(3):
            try:
                prompt = (
                    f"Create a cinematic background scene based on: '{prompt}'. "
                    f"Style: photorealistic, high definition, cinematic lighting, professional composition. "
                    f"Optimize for 16:9 aspect ratio with balanced visual weight. "
                    f"Keep text minimal and ensure any branded elements appear natural within the scene."
                )
                
                # Ensure output directory exists
                os.makedirs(self.output_dir, exist_ok=True)
                logger.debug(f"Generating image for prompt (attempt {attempt + 1}): {prompt}")
                response = self.client.invoke_model(
                    modelId=settings.bedrock_stability_model_id,
                    body=json.dumps({
                        "text_prompts": [{"text": prompt, "weight": 1.0}],
                        "cfg_scale": 10,
                        "steps": 50,
                        "seed": 0,
                        "width": 1280,
                        "height": 768
                    })
                )
                image_data = json.loads(response["body"].read())["artifacts"][0]["base64"]
                # Use a unique filename based on prompt hash
                image_filename = f"image_{hash(prompt)}_{os.urandom(4).hex()}.png"
                image_path = os.path.join(self.output_dir, image_filename)
                with open(image_path, "wb") as f:
                    f.write(base64.b64decode(image_data))
                relative_path = os.path.join("generated_images", image_filename)
                logger.debug(f"Saved image: {image_path}, Relative path: {relative_path}")
                return relative_path
            except Exception as e:
                logger.warning(f"Image generation attempt {attempt + 1} failed: {str(e)}")
                if attempt == 2:
                    logger.error(f"Image generation failed after 3 attempts: {str(e)}")
                    return "assets/generated_image_default.png"
                await asyncio.sleep(1)
        return "assets/generated_image_default.png"

    async def regenerate_image(self, prompt: str, image_path: str) -> str:
        """Regenerate an image with a new prompt.

        Args:
            prompt (str): The new prompt for image generation.
            image_path (str): Path to the existing image (ignored in this implementation).

        Returns:
            str: Relative path to the regenerated image.

        Raises:
            HTTPException: If image generation fails (handled in generate_image).
        """
        
        logger.debug(f"Regenerating image with prompt: {prompt}")
        return await self.generate_image(prompt)

def get_image_service(provider: str = "stability") -> ImageGenerationService:
    """Get the image generation service instance.

    Args:
        provider (str): The image provider name (default: "stability").

    Returns:
        ImageGenerationService: The image service instance.

    Raises:
        ValueError: If the provider is unsupported.
    """
    try:
        if provider == "stability":
            logger.debug("Initializing StabilityImageService")
            return StabilityImageService()
        logger.error(f"Unsupported image provider: {provider}")
        raise ValueError(f"Unsupported image provider: {provider}")
    except Exception as e:
        logger.error(f"Failed to initialize image service: {str(e)}")
        raise