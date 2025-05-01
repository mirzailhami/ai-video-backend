from ..logging_config import logo_service_logger as logger
from PIL import Image
from fastapi import HTTPException
import os
import asyncio
import tempfile

class LogoService:
    def _resize_with_aspect_ratio(self, image: Image.Image, target_size: tuple = (1280, 720), width_only: bool = False, target_width: int = None) -> Image.Image:
        """Resize an image to fit within target dimensions or by width, preserving aspect ratio.

        Args:
            image (Image.Image): The PIL Image object to resize.
            target_size (tuple): Target dimensions (width, height) for background images.
            width_only (bool): If True, resize by target_width only, ignoring target_size height.
            target_width (int): Target width for width-only resizing (used if width_only is True).

        Returns:
            Image.Image: Resized image with transparent padding (if applicable).

        Raises:
            HTTPException: If resizing fails.
        """
        try:
            img_width, img_height = image.size
            if width_only and target_width:
                # Resize by width, preserving aspect ratio
                scale = target_width / img_width
                new_width = target_width
                new_height = int(img_height * scale)
                return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            else:
                # Resize to fit within target dimensions
                target_width, target_height = target_size
                img_aspect = img_width / img_height
                target_aspect = target_width / target_height
                if img_aspect > target_aspect:
                    scale = target_width / img_width
                else:
                    scale = target_height / img_height
                new_width = int(img_width * scale)
                new_height = int(img_height * scale)
                resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                canvas = Image.new("RGBA", target_size, (0, 0, 0, 0))
                paste_x = (target_width - new_width) // 2
                paste_y = (target_height - new_height) // 2
                canvas.paste(resized_image, (paste_x, paste_y))
                return canvas
        except Exception as e:
            logger.error(f"Error resizing image: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error resizing image: {str(e)}")

    async def save_logo(self, logo: "UploadFile") -> str:
        """Save an uploaded logo file to a temporary location and return its path.

        Args:
            logo (UploadFile): The uploaded logo file.

        Returns:
            str: Path to the saved logo file.

        Raises:
            HTTPException: If saving the file fails.
        """
        try:
            suffix = os.path.splitext(logo.filename or 'logo.png')[1] or '.png'
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                logo_path = temp_file.name
                content = await logo.read()
                temp_file.write(content)
            logger.debug(f"Saved logo to temporary file: {logo_path}")
            return logo_path
        except Exception as e:
            logger.error(f"Failed to save logo: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to save logo: {str(e)}")

    async def cleanup_logo(self, logo_path: str) -> None:
        """Clean up a temporary logo file.

        Args:
            logo_path (str): Path to the logo file to clean up.

        Raises:
            HTTPException: If cleanup fails.
        """
        try:
            if logo_path and os.path.exists(logo_path):
                os.remove(logo_path)
                logger.debug(f"Cleaned up temporary logo file: {logo_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up temporary logo file {logo_path}: {str(e)}")

    async def add_logo_to_image(self, image_path: str, logo_path: str, output_path: str, position: tuple = (10, 10), logo_width: int = 185) -> None:
        """Add a logo to a background image and save the result, resizing logo by width.

        Args:
            image_path (str): Path to the background image.
            logo_path (str): Path to the logo image.
            output_path (str): Path to save the output image.
            position (tuple): (x, y) coordinates for logo placement.
            logo_width (int): Target width for the logo (default: 185 pixels).

        Raises:
            HTTPException: If image or logo file is missing or processing fails.
        """
        try:
            if not os.path.exists(image_path):
                logger.error(f"Background image not found: {image_path}")
                raise HTTPException(status_code=500, detail=f"Background image not found: {image_path}")
            if not os.path.exists(logo_path):
                logger.error(f"Logo image not found: {logo_path}")
                raise HTTPException(status_code=500, detail=f"Logo image not found: {logo_path}")

            # Run image processing in a thread to avoid blocking
            loop = asyncio.get_event_loop()
            background = await loop.run_in_executor(None, Image.open, image_path)
            background = background.convert("RGBA")
            logo = await loop.run_in_executor(None, Image.open, logo_path)
            logo = logo.convert("RGBA")

            background = await loop.run_in_executor(None, self._resize_with_aspect_ratio, background, (1280, 720), False, None)
            logo = await loop.run_in_executor(None, self._resize_with_aspect_ratio, logo, (1280, 720), True, logo_width)
            background.paste(logo, position, logo)
            await loop.run_in_executor(None, background.save, output_path, "PNG")
            logger.debug(f"Logo added to {image_path}, saved as {output_path}, logo width: {logo_width}")
        except Exception as e:
            logger.error(f"Error adding logo to {image_path}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error adding logo: {str(e)}")