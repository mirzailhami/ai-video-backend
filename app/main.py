from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .routes import upload, extract, scenes, video
from .config import settings
from .logging_config import main_logger as logger
import uuid
import os

app = FastAPI(title="PPT to Video API")

# Create directories before mounting
os.makedirs(settings.upload_dir, exist_ok=True)
os.makedirs(settings.image_dir, exist_ok=True)
assets_dir = os.path.join(os.path.dirname(__file__), "assets")
os.makedirs(assets_dir, exist_ok=True)

# Serve static files
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")
app.mount("/generated_images", StaticFiles(directory=settings.image_dir), name="generated_images")
app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request ID middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Add a unique request ID to each HTTP request for tracing."""
    request_id = str(uuid.uuid4())
    with logger.contextualize(request_id=request_id):
        logger.info(f"Received request: {request.method} {request.url}")
        response = await call_next(request)
        logger.info(f"Completed request: {request.method} {request.url}")
        response.headers["X-Request-ID"] = request_id
        return response

# Include routes
app.include_router(upload.router, prefix="/api/upload")
app.include_router(extract.router, prefix="/api/extract")
app.include_router(scenes.router, prefix="/api/scenes")
app.include_router(video.router, prefix="/api/video")

@app.get("/")
async def root():
    """Root endpoint for the PPT to Video API."""
    logger.info("Root endpoint accessed")
    return {"message": "PPT to Video API"}