from fastapi import HTTPException
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from ..models.slide import SlideData
from ..config import settings
from typing import List
import os
import hashlib
from ..logging_config import ppt_parser_logger as logger
from PIL import Image
import io
import re

def clean_text(text: str) -> str:
    """Remove special characters and normalize quotes."""
    if not text:
        return text
    # Remove vertical tabs and control characters
    text = re.sub(r'[\u000b\x00-\x1F\x7F-\x9F]', '', text)
    # Normalize quotes
    text = text.replace('’', "'").replace('“', '"').replace('”', '"')
    return text.strip()

def parse_ppt(file_path: str) -> List[SlideData]:
    try:
        logger.debug(f"Parsing PPT file: {file_path}")
        prs = Presentation(file_path)
        slides_data = []
        slide_width = prs.slide_width
        slide_height = prs.slide_height
        image_hashes = set()
        
        for slide_idx, slide in enumerate(prs.slides):
            slide_data = SlideData(
                title=f"Slide {slide_idx + 1}",
                text="",
                images=[],
                tables=[]
            )
            # Extract title
            title_set = False
            if slide.slide_layout.name and slide.slide_layout.name != "Blank":
                for shape in slide.shapes:
                    if shape.is_placeholder and shape.placeholder_format.type == 1:
                        if shape.has_text_frame and shape.text.strip():
                            slide_data.title = clean_text(shape.text)
                            title_set = True
                            logger.debug(f"Slide {slide_idx + 1} title set from placeholder: {slide_data.title}")
                            break
            if not title_set:
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        slide_data.title = clean_text(shape.text)
                        title_set = True
                        logger.debug(f"Slide {slide_idx + 1} title set from shape: {slide_data.title}")
                        break

            # Extract other content
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    cleaned_text = clean_text(shape.text)
                    # Skip if text matches title exactly
                    if cleaned_text.lower() != slide_data.title.lower():
                        slide_data.text += cleaned_text + "\n"
                elif shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    try:
                        image = shape.image
                        blob_hash = hashlib.sha1(image.blob).hexdigest()
                        if blob_hash in image_hashes:
                            logger.warning(f"Duplicate image detected for Slide {slide_idx + 1}, Shape {shape.name}")
                            continue
                        image_hashes.add(blob_hash)
                        
                        img_ext = image.ext.lower() if image.ext else None
                        if not img_ext:
                            try:
                                img = Image.open(io.BytesIO(image.blob))
                                img_ext = img.format.lower()
                            except Exception as e:
                                logger.warning(f"Could not determine image format for Slide {slide_idx + 1}, Shape {shape.name}: {str(e)}")
                                continue
                        if img_ext not in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']:
                            logger.warning(f"Unsupported image format {img_ext} for Slide {slide_idx + 1}, Shape {shape.name}")
                            continue
                        
                        image_hash = hashlib.md5(f"{slide_idx}_{shape.name}_{image.sha1}".encode()).hexdigest()
                        image_filename = f"slide_{slide_idx}_{image_hash}.{img_ext}"
                        image_path = os.path.join(settings.image_dir, image_filename)
                        
                        os.makedirs(settings.image_dir, exist_ok=True)
                        with open(image_path, "wb") as f:
                            f.write(image.blob)
                        
                        file_size = os.path.getsize(image_path)
                        if file_size < 100:
                            logger.warning(f"Invalid image {image_path}: File too small ({file_size} bytes)")
                            os.remove(image_path)
                            continue
                        
                        try:
                            with open(image_path, "rb") as f:
                                Image.open(io.BytesIO(f.read())).verify()
                        except Exception as e:
                            logger.warning(f"Invalid image content for {image_path}: {str(e)}")
                            os.remove(image_path)
                            continue
                        
                        relative_image_path = os.path.join("generated_images", image_filename)
                        logger.debug(f"Saved image: {image_path}, Format: {img_ext}, Size: {file_size} bytes")
                        
                        width_pixels = shape.width / 9144
                        height_pixels = shape.height / 9144
                        aspect_ratio = width_pixels / height_pixels if height_pixels > 0 else 1.0
                        is_logo = (
                            (width_pixels < 1000 and height_pixels < 300 and 0.1 < aspect_ratio < 10.0) and
                            (
                                (shape.left < slide_width * 0.3 and shape.top < slide_height * 0.2) or
                                (shape.left > slide_width * 0.7 and shape.top < slide_height * 0.2) or
                                (shape.left < slide_width * 0.3 and shape.top > slide_height * 0.8) or
                                (shape.left > slide_width * 0.7 and shape.top > slide_height * 0.8)
                            )
                        )
                        slide_data.images.append({
                            "path": relative_image_path,
                            "is_logo": is_logo,
                            "format": img_ext,
                            "size": file_size
                        })
                        logger.debug(f"Image detected as {'logo' if is_logo else 'non-logo'}: {relative_image_path}, Format: {img_ext}, Size: {file_size}")
                    except Exception as e:
                        logger.warning(f"Failed to process image for Slide {slide_idx + 1}, Shape {shape.name}: {str(e)}")
                        continue
                elif shape.shape_type == MSO_SHAPE_TYPE.TABLE:
                    table_data = [[clean_text(cell.text) for cell in row.cells] for row in shape.table.rows]
                    slide_data.tables.append(table_data)
                    logger.debug(f"Extracted table for Slide {slide_idx + 1}: {table_data}")
            slide_data.text = slide_data.text.strip()
            slides_data.append(slide_data)
            logger.debug(f"Processed Slide {slide_idx + 1}: {slide_data.title}")
        logger.info(f"Successfully parsed PPT: {file_path}, {len(slides_data)} slides")
        return slides_data
    except Exception as e:
        logger.error(f"Error parsing PPT: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Error parsing PPT: {str(e)}")