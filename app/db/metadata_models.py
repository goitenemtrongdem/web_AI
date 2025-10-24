"""
Metadata Models - For inspection ZIP upload metadata.json
Defines the structure for metadata.json that tracks image information
"""

from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime


class ImageMetadata(BaseModel):
    """Individual image metadata in metadata.json"""
    image_id: str = Field(..., description="UUID of the image in database")
    surface: str = Field(..., description="Surface code: PS, LE, TE, SS")
    position_pct: Optional[float] = Field(None, description="Position as percentage (0-100)")
    position_meter: Optional[float] = Field(None, description="Position in meters from blade root")
    relative_path: str = Field(..., description="Relative path from inspection folder: BladeA/PS/image.jpg")
    filename: str = Field(..., description="Original filename")
    captured_at: Optional[datetime] = Field(None, description="When the image was captured")
    file_size: Optional[int] = Field(None, description="File size in bytes")
    
    class Config:
        json_schema_extra = {
            "example": {
                "image_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "surface": "PS",
                "position_pct": 25.5,
                "position_meter": 15.3,
                "relative_path": "BladeA/PS/IMG_001.jpg",
                "filename": "IMG_001.jpg",
                "captured_at": "2024-01-15T10:30:00Z",
                "file_size": 2048576
            }
        }


class BladeMetadata(BaseModel):
    """Metadata for a single blade (A, B, or C)"""
    blade_name: str = Field(..., description="Blade identifier: BladeA, BladeB, BladeC")
    images: List[ImageMetadata] = Field(default_factory=list, description="List of images for this blade")
    total_images: int = Field(0, description="Total number of images for this blade")
    
    class Config:
        json_schema_extra = {
            "example": {
                "blade_name": "BladeA",
                "total_images": 45,
                "images": [
                    {
                        "image_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        "surface": "PS",
                        "position_pct": 25.5,
                        "position_meter": 15.3,
                        "relative_path": "BladeA/PS/IMG_001.jpg",
                        "filename": "IMG_001.jpg"
                    }
                ]
            }
        }


class InspectionMetadata(BaseModel):
    """Complete metadata.json structure for inspection"""
    inspection_code: str = Field(..., description="Unique inspection code")
    inspection_id: str = Field(..., description="UUID of inspection in database")
    turbine_name: str = Field(..., description="Turbine identifier (e.g., WT01)")
    turbine_id: str = Field(..., description="UUID of turbine in database")
    operator: Optional[str] = Field(None, description="Operator who performed inspection")
    equipment: Optional[str] = Field(None, description="Equipment used for inspection")
    captured_at: datetime = Field(..., description="When inspection was performed")
    uploaded_at: datetime = Field(..., description="When ZIP was uploaded")
    uploaded_by: str = Field(..., description="User ID who uploaded")
    
    blades: List[BladeMetadata] = Field(default_factory=list, description="Metadata for each blade")
    
    total_images: int = Field(0, description="Total images across all blades")
    storage_path: str = Field(..., description="Base storage path for this inspection")
    
    # Additional metadata
    project_id: Optional[str] = Field(None, description="Project UUID")
    windfarm_id: Optional[str] = Field(None, description="Windfarm UUID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "inspection_code": "INSP-20240115-a1b2c3d4",
                "inspection_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "turbine_name": "WT01",
                "turbine_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
                "operator": "John Doe",
                "equipment": "DJI Mavic 3",
                "captured_at": "2024-01-15T10:00:00Z",
                "uploaded_at": "2024-01-15T14:30:00Z",
                "uploaded_by": "c3d4e5f6-a7b8-9012-cdef-123456789012",
                "total_images": 135,
                "storage_path": "storage/inspections/projects/proj-id/windfarms/wf-id/turbines/turb-id/insp-id",
                "blades": [
                    {
                        "blade_name": "BladeA",
                        "total_images": 45,
                        "images": []
                    }
                ]
            }
        }


class AIAnalysisRequest(BaseModel):
    """Request to run AI analysis on selected images"""
    image_ids: List[str] = Field(..., description="List of image UUIDs to analyze")
    reanalyze: bool = Field(False, description="If True, re-run AI even if already analyzed")
    
    class Config:
        json_schema_extra = {
            "example": {
                "image_ids": [
                    "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                    "b2c3d4e5-f6a7-8901-bcde-f12345678901"
                ],
                "reanalyze": False
            }
        }


class DeleteImagesRequest(BaseModel):
    """Request to delete images from inspection"""
    image_ids: List[str] = Field(..., description="List of image UUIDs to delete")
    delete_files: bool = Field(True, description="If True, also delete physical files")
    
    class Config:
        json_schema_extra = {
            "example": {
                "image_ids": [
                    "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
                ],
                "delete_files": True
            }
        }


class AddImageRequest(BaseModel):
    """Request to add a single image to inspection"""
    blade: str = Field(..., description="Blade: BladeA, BladeB, or BladeC")
    surface: str = Field(..., description="Surface: PS, LE, TE, SS")
    position_pct: Optional[float] = Field(None, description="Position percentage")
    position_meter: Optional[float] = Field(None, description="Position in meters")
    captured_at: Optional[datetime] = Field(None, description="When image was captured")
    
    class Config:
        json_schema_extra = {
            "example": {
                "blade": "BladeA",
                "surface": "PS",
                "position_pct": 50.0,
                "position_meter": 30.0,
                "captured_at": "2024-01-15T11:00:00Z"
            }
        }
