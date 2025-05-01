from abc import ABC, abstractmethod
from typing import List
from ..models.slide import SlideData, Scene

class VisionLLMService(ABC):
    @abstractmethod
    async def generate_scenes(self, slides_data: List[SlideData]) -> List[Scene]:
        """Generate scenes with scripts and image prompts from slide data."""
        pass

class ImageGenerationService(ABC):
    @abstractmethod
    async def generate_image(self, prompt: str) -> str:
        """Generate an image from a prompt and return its path."""
        pass

    @abstractmethod
    async def regenerate_image(self, prompt: str, image_path: str) -> str:
        """Regenerate an image with a modified prompt."""
        pass

class VideoGenerationService(ABC):
    @abstractmethod
    async def generate_video(self, scenes: List[Scene], logo_path: str) -> str:
        """Generate a video from scenes and a logo, return video path."""
        pass