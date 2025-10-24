from decouple import config
import os

# Database
DATABASE_URL = config("DATABASE_URL")
 

# JWT
SECRET_KEY = config("SECRET_KEY")
ALGORITHM = config("ALGORITHM", default="HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = config("ACCESS_TOKEN_EXPIRE_MINUTES", default=1440, cast=int)

# Email
SMTP_SERVER = config("SMTP_SERVER")
SMTP_PORT = config("SMTP_PORT", cast=int)
SMTP_USERNAME = config("SMTP_USERNAME")
SMTP_PASSWORD = config("SMTP_PASSWORD")
FROM_EMAIL = config("FROM_EMAIL")
ADMIN_EMAIL = config("ADMIN_EMAIL", default="admin@example.com")

# OTP
OTP_EXPIRE_MINUTES = config("OTP_EXPIRE_MINUTES", default=5, cast=int)
SESSION_EXPIRE_MINUTES = config("SESSION_EXPIRE_MINUTES", default=5, cast=int)
AUTH_SESSION_EXPIRE_MINUTES = config("AUTH_SESSION_EXPIRE_MINUTES", default=1440, cast=int)

# Environment
ENVIRONMENT = config("ENVIRONMENT", default="development")

FRONTEND_ORIGINS = [
    o.strip() for o in config(
        "FRONTEND_ORIGINS",
        default="http://localhost:3000,http://localhost:5173,http://127.0.0.1:5173"
    ).split(",") if o.strip()
]
# Thay 192.168.1.X bằng IP thật của máy chủ và máy client

# ==================================================================================
# INSPECTION & STORAGE CONFIG
# ==================================================================================
from pathlib import Path
import os

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Storage paths - default to local storage in project directory
STORAGE_ROOT = Path(config("STORAGE_ROOT", default=str(PROJECT_ROOT / "storage" / "inspections")))
TEMP_UPLOAD_DIR = Path(config("TEMP_UPLOAD_DIR", default=str(PROJECT_ROOT / "storage" / "temp")))
AI_MODEL_PATH = Path(config("AI_MODEL_PATH", default=str(PROJECT_ROOT / "models" / "blade_damage_detector.pt")))

# Upload limits
MAX_UPLOAD_SIZE = config("MAX_UPLOAD_SIZE", default=1024 * 1024 * 1024, cast=int)  # 1GB
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".bmp"}

# Note: Don't create directories on import - will be created on demand when needed
# This prevents permission errors during startup


def get_inspection_storage_path(project_id: str, windfarm_id: str, turbine_id: str, inspection_id: str) -> dict:
    """
    Generate storage paths for inspection
    Creates directories on demand
    """
    base_path = STORAGE_ROOT / "projects" / project_id / "windfarms" / windfarm_id / "turbines" / turbine_id / "inspections" / inspection_id
    
    paths = {
        "base_path": str(base_path),
        "raw_images_path": str(base_path / "raw"),
        "processed_images_path": str(base_path / "processed"),
        "results_path": str(base_path / "results")
    }
    
    return paths


def ensure_storage_directories():
    """
    Create storage directories if they don't exist
    Call this during application startup or before first use
    """
    try:
        STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        print(f"✓ Storage directories created: {STORAGE_ROOT}")
    except PermissionError as e:
        print(f"⚠ Warning: Could not create storage directories: {e}")
        print(f"  Please create manually or run with appropriate permissions")
    except Exception as e:
        print(f"✗ Error creating storage directories: {e}")
