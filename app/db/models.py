from datetime import datetime
from uuid import UUID
from typing import Optional, List, Dict, Any
from enum import Enum

from pydantic import BaseModel, EmailStr, Field

# Common models
class CreatedByInfo(BaseModel):
    """Information about who created a resource"""
    id: UUID | str
    name: str
    email: str

# Registration models


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone: str = Field(..., pattern=r'^[0-9]{10,11}$')
    password: str = Field(..., min_length=6)
    confirm_password: str = Field(..., min_length=6)


class VerifyRegistrationRequest(BaseModel):
    otp: str = Field(..., pattern=r'^[0-9]{6}$')

# Login models


class LoginRequest(BaseModel):
    identifier: str  # email or phone
    password: str


class VerifyOTPRequest(BaseModel):
    otp: str = Field(..., pattern=r'^[0-9]{6}$')

# Response models


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: str
    role: str
    is_approved: bool = False


class RegisterSuccessResponse(BaseModel):
    status: str
    message: str
    user: Optional[UserResponse] = None


class RegisterResponse(BaseModel):
    status: str
    message: str


class LoginPendingResponse(BaseModel):
    status: str
    message: str


class LoginSuccessResponse(BaseModel):
    status: str
    message: str
    user: UserResponse


class ErrorResponse(BaseModel):
    status: str
    message: str


class SuccessResponse(BaseModel):
    status: str
    message: str

# Admin models


class UserListResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: str
    role: str
    is_approved: bool
    is_active: bool
    created_at: datetime


class ApproveUserRequest(BaseModel):
    user_id: str


class AdminResponse(BaseModel):
    status: str
    message: str
    data: Optional[dict] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class VerifyResetOTPRequest(BaseModel):
    otp: str


class ResetPasswordRequest(BaseModel):
    password: str
    confirm_password: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str
# ===============================
# ENUMS FOR PROJECT MANAGEMENT
# ===============================

class ProjectRole(str, Enum):
    """User roles within a project"""
    OWNER = "owner"      # Full control, can delete project
    EDITOR = "editor"    # Can edit project, windfarms, turbines
    VIEWER = "viewer"    # Read-only access


class TurbineStatus(str, Enum):
    """Turbine status options"""
    PLANNED = "planned"
    UNDER_CONSTRUCTION = "under_construction"
    OPERATIONAL = "operational"
    MAINTENANCE = "maintenance"
    DECOMMISSIONED = "decommissioned"
    CANCELLED = "cancelled"


class AuditAction(str, Enum):
    """Audit log action types"""
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    STATUS_CHANGE = "STATUS_CHANGE"
    MEMBER_ADDED = "MEMBER_ADDED"
    MEMBER_REMOVED = "MEMBER_REMOVED"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    PASSWORD_CHANGE = "PASSWORD_CHANGE"


class EntityType(str, Enum):
    """Entity types for audit logging"""
    USER = "USER"
    PROJECT = "PROJECT"
    WINDFARM = "WINDFARM"
    TURBINE = "TURBINE"
    PROJECT_MEMBER = "PROJECT_MEMBER"
    INSPECTION = "INSPECTION"
    INSPECTION_IMAGE = "INSPECTION_IMAGE"


# ==================================================================================
# PROJECT MODELS
# ==================================================================================

class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)


class ProjectResponse(BaseModel):
    id: UUID | str
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime
    created_by: CreatedByInfo

    member_count: Optional[int] = 0
    windfarm_count: Optional[int] = 0


class ProjectListResponse(BaseModel):
    projects: List[Dict[str, Any]]
    total: int
    limit: int
    offset: int


# ==================================================================================
# PROJECT MEMBER MODELS
# ==================================================================================

class ProjectMemberResponse(BaseModel):
    project_id: str
    user_id: str
    user_name: str
    user_email: str
    role: ProjectRole
    can_invite: bool
    joined_at: datetime


class UpdateMemberRequest(BaseModel):
    role: Optional[ProjectRole] = None
    can_invite: Optional[bool] = None


class AddMemberRequest(BaseModel):
    email: EmailStr
    role: ProjectRole = ProjectRole.EDITOR
    can_invite: bool = False


class ProjectMemberListResponse(BaseModel):
    members: List[ProjectMemberResponse]
    total: int
    limit: int
    offset: int


# ==================================================================================
# WINDFARM MODELS
# ==================================================================================

class WindfarmCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    own_company: Optional[str] = Field(None, max_length=255)
    location: Optional[str] = Field(None, max_length=500)


class WindfarmUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    own_company: Optional[str] = Field(None, max_length=255)
    location: Optional[str] = Field(None, max_length=500)


class WindfarmResponse(BaseModel):
    id: UUID | str
    name: str
    description: Optional[str]
    own_company: Optional[str]
    location: Optional[str]
    project_id: UUID | str
    project_name: Optional[str]
    created_at: datetime
    updated_at: datetime
    created_by: CreatedByInfo
    turbine_count: Optional[int] = 0


class WindfarmListResponse(BaseModel):
    windfarms: List[WindfarmResponse]
    total: int
    limit: int
    offset: int


# ==================================================================================
# TURBINE MODELS
# ==================================================================================

class TurbineCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    capacity_mw: Optional[float] = Field(None, ge=0)
    serial_no: Optional[str] = Field(None, max_length=100)
    coordinates: Optional[str] = None  # Will store as "lat,lng"


class TurbineUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    capacity_mw: Optional[float] = Field(None, ge=0)
    serial_no: Optional[str] = Field(None, max_length=100)
    coordinates: Optional[str] = None


class TurbineResponse(BaseModel):
    id: UUID | str
    name: str
    description: Optional[str]
    windfarm_id: UUID | str
    windfarm_name: Optional[str]
    capacity_mw: Optional[float]
    coordinates: Optional[str]
    serial_no: Optional[str]
    created_at: datetime
    updated_at: datetime
    created_by: CreatedByInfo


class TurbineListResponse(BaseModel):
    turbines: List[TurbineResponse]
    total: int
    limit: int
    offset: int


class AutoCoordinates(BaseModel):
    start_lat: float = Field(..., ge=-90, le=90)
    start_lng: float = Field(..., ge=-180, le=180)
    spacing_m: int = Field(500, ge=50, le=5000)
    grid_cols: int = Field(10, ge=1, le=50)


# ==================================================================================
# AUDIT LOG MODELS
# ==================================================================================

class AuditLogResponse(BaseModel):
    id: str
    project_id: Optional[str]
    actor_id: str
    actor_name: str
    action: AuditAction
    entity_type: EntityType
    entity_id: str
    before_data: Optional[Dict[str, Any]]
    after_data: Optional[Dict[str, Any]]
    metadata: Optional[Dict[str, Any]]
    timestamp: datetime
    ip_address: Optional[str]


class AuditLogFilterRequest(BaseModel):
    project_id: Optional[str] = None
    actor_id: Optional[str] = None
    action: Optional[AuditAction] = None
    entity_type: Optional[EntityType] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: int = Field(50, ge=1, le=1000)
    offset: int = Field(0, ge=0)


# ==================================================================================
# COMMON RESPONSE MODELS
# ==================================================================================

class PermissionError(BaseModel):
    status: str = "error"
    message: str = "Insufficient permissions"


class NotFoundError(BaseModel):
    status: str = "error"
    message: str = "Resource not found"


# ==================================================================================
# INSPECTION MODELS
# ==================================================================================

class BladeSurface(str, Enum):
    """Bề mặt cánh turbine"""
    PS = "PS"  # Pressure Side
    LE = "LE"  # Leading Edge
    TE = "TE"  # Trailing Edge
    SS = "SS"  # Suction Side


class InspectionStatus(str, Enum):
    """Trạng thái inspection"""
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ImageStatus(str, Enum):
    """Trạng thái ảnh"""
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    ANALYZED = "analyzed"
    REVIEWED = "reviewed"
    FAILED = "failed"


class DamageGrade(int, Enum):
    """Cấp độ hư hỏng (1-5)"""
    GRADE_1 = 1  # Vết bẩn, vết nứt nhỏ - Green
    GRADE_2 = 2  # Hao mòn lớp phủ - Light Green
    GRADE_3 = 3  # Hư hỏng lớp phủ/LEP - Yellow
    GRADE_4 = 4  # Mất LEP nghiêm trọng - Orange
    GRADE_5 = 5  # Lỗ lớp Laminate 100% - Red


# Request Models
class InspectionUploadRequest(BaseModel):
    """Request khi upload inspection"""
    operator: Optional[str] = None
    equipment: Optional[str] = None
    captured_at: Optional[datetime] = None


class DamageAssessmentUpdateRequest(BaseModel):
    """Request để cập nhật đánh giá hư hỏng sau khi AI xử lý"""
    damage_grade: int = Field(..., ge=1, le=5, description="Cấp độ hư hỏng 1-5")
    damage_description: Optional[str] = Field(None, description="Mô tả chi tiết hư hỏng")
    manual_notes: Optional[str] = Field(None, description="Ghi chú của reviewer")


# Response Models
class DamageGradeInfo(BaseModel):
    """Thông tin cấp độ hư hỏng"""
    grade: int
    label: str
    color: str
    description: str
    impact: str
    recommended_action: str


class DamageAssessmentResponse(BaseModel):
    """✅ Ultra-simplified Response - Only bounding boxes (with type & confidence) + description"""
    id: str
    inspection_image_id: str
    
    # ✅ AI Analysis (Bounding boxes contain all detection info: x, y, width, height, type, confidence)
    ai_bounding_boxes: Optional[List[Dict[str, Any]]]
    ai_processed_at: Optional[datetime]
    
    # ✅ User Notes
    description: Optional[str]
    
    # Audit
    created_at: datetime
    updated_at: datetime


class InspectionImageResponse(BaseModel):
    """Response cho từng ảnh"""
    id: str
    inspection_id: str
    blade: str
    surface: str
    position_pct: Optional[float]
    file_name: str
    file_size: Optional[int]
    status: str
    captured_at: Optional[datetime]
    viewed_at: Optional[datetime]
    created_at: datetime
    
    # Damage assessment nếu có
    damage_assessment: Optional[DamageAssessmentResponse]


class InspectionResponse(BaseModel):
    """Response cho inspection"""
    id: str
    turbine_id: str
    inspection_code: str
    status: str
    captured_at: Optional[datetime]
    operator: Optional[str]
    equipment: Optional[str]
    storage_path: str
    total_images: int
    processed_images: int
    created_at: datetime
    updated_at: datetime
    created_by: CreatedByInfo
    
    # Progress
    progress_percentage: float = 0.0


class InspectionListItemResponse(BaseModel):
    """Response cho list item (simplified version)"""
    id: str
    turbine_id: str
    inspection_code: str
    status: str
    captured_at: Optional[datetime]
    operator: Optional[str]
    total_images: int
    processed_images: int
    created_at: datetime
    
    # Progress
    progress_percentage: float = 0.0


class InspectionDetailResponse(InspectionResponse):
    """Response chi tiết inspection với thống kê"""
    images_by_blade: Dict[str, int]
    images_by_surface: Dict[str, int]
    images_by_status: Dict[str, int]
    damage_distribution: Dict[int, int]  # {grade: count}
