from pydantic import BaseModel
from typing import List, Dict, Any

class SlideData(BaseModel):
    title: str
    text: str
    images: List[Dict[str, Any]]  # List of {"path": str, "is_logo": bool}
    tables: List[List[List[str]]]

class Scene(BaseModel):
    script: str
    image_prompt: str
    image_path: str

class ScenesResponse(BaseModel):
    scenes: List[Scene]