from fastapi import APIRouter, HTTPException
from ..services.ppt_parser import parse_ppt
from ..models.slide import SlideData
from typing import List

router = APIRouter()

@router.post("/parse")
async def extract_content(file_path: str) -> List[SlideData]:
    try:
        slides_data = parse_ppt(file_path)
        return slides_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))