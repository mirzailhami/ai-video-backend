from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import os
import shutil
from ..config import settings
from ..logging_config import upload_logger as logger

router = APIRouter()

@router.post("/ppt")
async def upload_ppt(file: UploadFile = File(...)):
    if not file.filename.endswith((".ppt", ".pptx")):
        logger.error(f"Invalid file format: {file.filename}")
        raise HTTPException(status_code=400, detail="Invalid file format. Only .ppt or .pptx allowed.")
    
    file_path = os.path.join(settings.upload_dir, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    logger.info(f"Uploaded file: {file_path}")
    return JSONResponse(content={"filename": file.filename, "path": file_path})