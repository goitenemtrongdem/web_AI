"""
Turbines API Routes - Quản lý turbine gió
Cung cấp các endpoint để tạo, quản lý turbines trong windfarms
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel

from app.db.database import database, turbines_table
from app.db.models import (
    TurbineCreateRequest, TurbineUpdateRequest, TurbineResponse, TurbineListResponse
)
from app.services.base_service import ProjectContextService
from app.services.audit_service import AuditLogger
from app.utilities.permissions import check_project_access
from app.db.models import EntityType
from app.api.v1.users_admin.auth_routes import get_current_user, require_user, require_admin

router = APIRouter(prefix="/turbines", tags=["turbines"])

# Initialize service
turbines_service = ProjectContextService(turbines_table, EntityType.TURBINE)


# ===============================
# TURBINE CRUD OPERATIONS
# ===============================

@router.post("/windfarm/{windfarm_id}", response_model=TurbineResponse, status_code=status.HTTP_201_CREATED)
async def create_turbine(
    windfarm_id: str,
    turbine_data: TurbineCreateRequest,
    request: Request,
    current_user: dict = Depends(require_user)
):
    """
    Tạo turbine mới trong windfarm
    
    - **windfarm_id**: ID của windfarm (trong URL path)
    - **name**: Tên turbine (required)
    - **description**: Mô tả turbine
    - **capacity_mw**: Công suất MW
    - **coordinates**: Tọa độ GPS "lat,lng"
    - **serial_no**: Số seri turbine
    
    Yêu cầu quyền: Editor trở lên trong project chứa windfarm
    """
    
    try:
        # Get windfarm to check project access
        windfarm_query = """
        SELECT w.*, p.id as project_id 
        FROM windfarms w
        INNER JOIN projects p ON w.project_id = p.id
        WHERE w.id = :windfarm_id
        """
        
        windfarm = await database.fetch_one(
            windfarm_query, {"windfarm_id": windfarm_id}
        )
        
        if not windfarm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Windfarm not found"
            )
        
        # Check project access (Editor level required)
        await check_project_access(
            current_user["id"], windfarm["project_id"], required_role_level=2
        )
        
        # Prepare turbine data
        create_data = turbine_data.dict()
        create_data["windfarm_id"] = windfarm_id  # Set windfarm_id from URL path
        
        # Get client IP
        ip_address = AuditLogger.get_client_ip(request)
        
        # Create turbine
        new_turbine = await turbines_service.create(
            data=create_data,
            actor_id=current_user["id"],
            project_id=windfarm["project_id"],
            ip_address=ip_address
        )
        
        # Enhance created_by info
        enhanced_turbine = await turbines_service.enhance_created_by_info(new_turbine)
        
        # Add windfarm_name to the response
        enhanced_turbine["windfarm_name"] = windfarm["name"]
        
        return TurbineResponse(**enhanced_turbine)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create turbine: {str(e)}"
        )


@router.get("/windfarm/{windfarm_id}", response_model=TurbineListResponse)
async def list_windfarm_turbines(
    windfarm_id: str,
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    current_user: dict = Depends(require_user)
):
    """
    Lấy danh sách turbines trong windfarm với full data bao gồm description
    
    - **windfarm_id**: ID của windfarm
    - **limit**: Số lượng results tối đa (default: 50)
    - **offset**: Bỏ qua số lượng results (default: 0)
    - **search**: Tìm kiếm theo tên hoặc serial_no (optional)
    
    Yêu cầu quyền: Viewer trở lên trong project chứa windfarm
    """
    
    try:
        # Get windfarm to check project access
        windfarm_query = """
        SELECT w.*, p.id as project_id 
        FROM windfarms w
        INNER JOIN projects p ON w.project_id = p.id
        WHERE w.id = :windfarm_id
        """
        
        windfarm = await database.fetch_one(
            windfarm_query, {"windfarm_id": windfarm_id}
        )
        
        if not windfarm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Windfarm not found"
            )
        
        # Check project access (Viewer level required)
        await check_project_access(
            current_user["id"], windfarm["project_id"], required_role_level=1
        )
        
        # Build query with direct SQL
        where_conditions = ["t.windfarm_id = :windfarm_id"]
        query_params = {"windfarm_id": windfarm_id, "limit": limit, "offset": offset}
        
        # Add search filter  
        if search:
            where_conditions.append("(t.name ILIKE :search OR t.serial_no ILIKE :search)")
            query_params["search"] = f"%{search}%"
        
        where_clause = " AND ".join(where_conditions)
        
        # Get turbines with windfarm name
        query = f"""
        SELECT 
          t.id,
          t.name,
          t.description,
          t.windfarm_id,
          t.capacity_mw,
          t.coordinates,
          t.serial_no,
          t.created_at,
          t.updated_at,
          t.created_by,
          w.name AS windfarm_name
        FROM turbines t
        INNER JOIN windfarms w ON t.windfarm_id = w.id
        WHERE {where_clause}
        ORDER BY t.created_at DESC
        LIMIT :limit OFFSET :offset
        """
        
        results = await database.fetch_all(query, query_params)
        
        # Enhance created_by information for each turbine
        turbines = []
        for row in results:
            turbine_dict = dict(row)
            turbine_dict = await turbines_service.enhance_created_by_info(turbine_dict)
            turbines.append(turbine_dict)
        
        # Get total count
        count_query = f"""
        SELECT COUNT(*)
        FROM turbines t
        WHERE {where_clause}
        """
        count_params = {k: v for k, v in query_params.items() if k not in ["limit", "offset"]}
        total = await database.fetch_val(count_query, count_params)
        
        # Enhance created_by for each turbine
        enhanced_turbines = []
        for turbine in turbines:
            enhanced_turbine = await turbines_service.enhance_created_by_info(dict(turbine))
            enhanced_turbines.append(enhanced_turbine)
        
        return TurbineListResponse(
            turbines=[TurbineResponse(**t) for t in enhanced_turbines],
            total=total or 0,
            limit=limit,
            offset=offset
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch turbines: {str(e)}"
        )


@router.get("/list", response_model=TurbineListResponse)
async def list_all_turbines(
    limit: int = 100,
    offset: int = 0,
    current_user: dict = Depends(require_admin)
):
    """
    Admin-only: List all turbines with windfarm name.
    """
    try:
        query = """
        SELECT 
          t.id,
          t.name,
          t.description,
          t.windfarm_id,
          t.capacity_mw,
          t.coordinates,
          t.serial_no,
          t.created_at,
          t.updated_at,
          t.created_by,
          w.name AS windfarm_name
        FROM turbines t
        INNER JOIN windfarms w ON t.windfarm_id = w.id
        ORDER BY t.created_at DESC
        LIMIT :limit OFFSET :offset
        """

        results = await database.fetch_all(query, {"limit": limit, "offset": offset})
        
        # Enhance created_by information for each turbine
        turbines = []
        for row in results:
            turbine_dict = dict(row)
            turbine_dict = await turbines_service.enhance_created_by_info(turbine_dict)
            turbines.append(turbine_dict)

        total = await database.fetch_val("SELECT COUNT(*) FROM turbines")

        return TurbineListResponse(
            turbines=[TurbineResponse(**t) for t in turbines],
            total=total or 0,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch all turbines: {str(e)}"
        )



@router.put("/{turbine_id}", response_model=TurbineResponse)
async def update_turbine(
    turbine_id: str,
    turbine_data: TurbineUpdateRequest,
    request: Request,
    current_user: dict = Depends(require_user)
):
    """
    Cập nhật thông tin turbine
    
    Yêu cầu quyền: Editor trở lên trong project chứa turbine
    """
    
    try:
        # Get turbine with project info
        turbine_query = """
        SELECT t.*, w.project_id
        FROM turbines t
        INNER JOIN windfarms w ON t.windfarm_id = w.id
        WHERE t.id = :turbine_id
        """
        
        turbine = await database.fetch_one(
            turbine_query, {"turbine_id": turbine_id}
        )
        
        if not turbine:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Turbine not found"
            )
        
        # Check project access (Editor level required)
        await check_project_access(
            current_user["id"], turbine["project_id"], required_role_level=2
        )
        
        # Get client IP
        ip_address = AuditLogger.get_client_ip(request)
        
        # Update turbine
        update_data = turbine_data.dict(exclude_unset=True)
        updated_turbine = await turbines_service.update(
            entity_id=turbine_id,
            update_data=update_data,
            actor_id=current_user["id"],
            project_id=turbine["project_id"],
            ip_address=ip_address
        )
        
        # Get updated turbine with windfarm name
        full_turbine_query = """
        SELECT 
            t.*,
            w.name as windfarm_name
        FROM turbines t
        INNER JOIN windfarms w ON t.windfarm_id = w.id
        WHERE t.id = :turbine_id
        """
        
        full_turbine = await database.fetch_one(
            full_turbine_query, {"turbine_id": turbine_id}
        )
        
        # Enhance created_by info
        enhanced_turbine = await turbines_service.enhance_created_by_info(dict(full_turbine))
        
        return TurbineResponse(**enhanced_turbine)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update turbine: {str(e)}"
        )


@router.delete("/{turbine_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_turbine(
    turbine_id: str,
    request: Request,
    current_user: dict = Depends(require_user)
):
    """
    Xóa turbine (soft delete)
    
    Yêu cầu quyền: Editor trở lên trong project chứa turbine
    """
    
    try:
        # Get turbine with project info
        turbine_query = """
        SELECT t.*, w.project_id
        FROM turbines t
        INNER JOIN windfarms w ON t.windfarm_id = w.id
        WHERE t.id = :turbine_id
        """
        
        turbine = await database.fetch_one(
            turbine_query, {"turbine_id": turbine_id}
        )
        
        if not turbine:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Turbine not found"
            )
        
        # Check project access (Editor level required)
        await check_project_access(
            current_user["id"], turbine["project_id"], required_role_level=2
        )
        
        # Get client IP
        ip_address = AuditLogger.get_client_ip(request)
        
        # Soft delete turbine
        await turbines_service.delete(
            entity_id=turbine_id,
            actor_id=current_user["id"],
            project_id=turbine["project_id"],
            ip_address=ip_address,
            soft_delete=True
        )
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete turbine: {str(e)}"
        )


# ===============================
# TURBINE STATUS MANAGEMENT
# ===============================
