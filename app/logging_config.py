from loguru import logger
import sys
import os

# Ensure logs directory exists
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOGS_DIR, exist_ok=True)

# Remove default logger
logger.remove()

# Filter to exclude main, upload, scenes, video services
def log_filter(record):
    excluded_services = {"main", "upload", "scenes", "video"}
    service = record["extra"].get("service", "")
    return service not in excluded_services

# Debug logger to capture logs from allowed services
logger.add(
    os.path.join(LOGS_DIR, "debug.log"),
    filter=log_filter,
    format="{time:YYYY-MM-DD HH:mm:ss} - {name} - {level} - {message} - {extra}",
    level="DEBUG",
    backtrace=True,
    diagnose=True
)

# Add console logging
logger.add(
    sys.stderr,
    format="{time:YYYY-MM-DD HH:mm:ss} - {name} - {level} - {message}",
    level="INFO"
)

# Bind loggers with service context
main_logger = logger.bind(service="main")
ppt_parser_logger = logger.bind(service="ppt_parser")
llm_service_logger = logger.bind(service="llm_service")
video_service_logger = logger.bind(service="video_service")
image_service_logger = logger.bind(service="image_service")
s3_service_logger = logger.bind(service="s3_service")
logo_service_logger = logger.bind(service="logo_service")
upload_logger = logger.bind(service="upload")
scenes_logger = logger.bind(service="scenes")
video_logger = logger.bind(service="video")

# Debug logger initialization
logger.debug("Initialized logger with filter for allowed services", extra={"service": "init"})