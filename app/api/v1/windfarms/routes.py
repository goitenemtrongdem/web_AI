"""
Windfarms API Routes - Quản lý trang trại gió
Cung cấp các endpoint để tạo, quản lý windfarms trong projects
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel

from app.db.database import database, windfarms_table
from app.db.models import (
    WindfarmCreateRequest, WindfarmUpdateRequest, WindfarmResponse, WindfarmListResponse
)
from app.services.base_service import ProjectContextService
from app.services.audit_service import AuditLogger
from app.utilities.permissions import check_project_access
from app.db.models import EntityType
from app.api.v1.users_admin.auth_routes import get_current_user, require_user, require_admin

router = APIRouter(prefix="/windfarms", tags=["windfarms"])

# Initialize service
windfarms_service = ProjectContextService(windfarms_table, EntityType.WINDFARM)


# ===============================
# WINDFARM CRUD OPERATIONS
# ===============================

@router.post("/project/{project_id}", response_model=WindfarmResponse, status_code=status.HTTP_201_CREATED)
async def create_windfarm(
    project_id: str,
    windfarm_data: WindfarmCreateRequest,
    request: Request,
    current_user: dict = Depends(require_user)
):
    """
    Tạo windfarm mới trong project
    
    - **project_id**: ID của project (trong URL path)
    - **name**: Tên windfarm (required)
    - **location**: Vị trí địa lý (required)
    - **own_company**: Công ty sở hữu
    
    Yêu cầu quyền: Editor trở lên trong project
    """
    
    try:
        # Check project access (Editor level required)
        await check_project_access(
            current_user["id"], project_id, required_role_level=2
        )
        
        # Prepare windfarm data
        create_data = windfarm_data.dict()
        create_data["project_id"] = project_id  # Set project_id from URL path
        
        # Get client IP
        ip_address = AuditLogger.get_client_ip(request)
        
        # Create windfarm
        new_windfarm = await windfarms_service.create(
            data=create_data,
            actor_id=current_user["id"],
            project_id=project_id,
            ip_address=ip_address
        )
        
        # Enhance created_by info
        enhanced_windfarm = await windfarms_service.enhance_created_by_info(new_windfarm)
        
        # Get project name for response
        project_query = "SELECT name FROM projects WHERE id = :project_id"
        project = await database.fetch_one(project_query, {"project_id": project_id})
        
        # Add missing fields for response
        enhanced_windfarm["project_name"] = project["name"] if project else None
        enhanced_windfarm["turbine_count"] = 0  # New windfarm has no turbines yet
        
        return WindfarmResponse(**enhanced_windfarm)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create windfarm: {str(e)}"
        )


@router.get("/project/{project_id}", response_model=WindfarmListResponse)
async def list_project_windfarms(
    project_id: str,
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    current_user: dict = Depends(require_user)
):
    """
    Lấy danh sách windfarms trong project
    
    - **project_id**: ID của project
    - **limit**: Số lượng results tối đa (default: 50)
    - **offset**: Bỏ qua số lượng results (default: 0)
    - **search**: Tìm kiếm theo tên hoặc location (optional)
    
    Yêu cầu quyền: Viewer trở lên trong project
    """
    
    try:
        # Check project access (Viewer level required)
        await check_project_access(
            current_user["id"], project_id, required_role_level=1
        )
        
        # Build SQL query with all fields including description and turbine count
        base_query = """
        SELECT 
            w.id,
            w.name,
            w.description,
            w.own_company,
            w.location,
            w.project_id,
            w.created_at,
            w.updated_at,
            w.created_by,
            p.name as project_name,
            (SELECT COUNT(*) FROM turbines t WHERE t.windfarm_id = w.id) as turbine_count
        FROM windfarms w
        INNER JOIN projects p ON w.project_id = p.id
        WHERE w.project_id = :project_id
        """
        
        # Add search filter if provided
        if search:
            search_term = f"%{search.lower()}%"
            base_query += " AND (LOWER(w.name) LIKE :search_term OR LOWER(w.location) LIKE :search_term)"
        
        base_query += " ORDER BY w.created_at DESC LIMIT :limit OFFSET :offset"
        
        # Execute query
        query_params = {"project_id": project_id, "limit": limit, "offset": offset}
        if search:
            query_params["search_term"] = f"%{search.lower()}%"
            
        results = await database.fetch_all(base_query, query_params)
        
        # Enhance created_by information for each windfarm
        windfarms = []
        for row in results:
            windfarm_dict = dict(row)
            windfarm_dict = await windfarms_service.enhance_created_by_info(windfarm_dict)
            windfarms.append(windfarm_dict)
        
        # Count total
        count_query = "SELECT COUNT(*) FROM windfarms w WHERE w.project_id = :project_id"
        count_params = {"project_id": project_id}
        
        if search:
            count_query += " AND (LOWER(w.name) LIKE :search_term OR LOWER(w.location) LIKE :search_term)"
            count_params["search_term"] = f"%{search.lower()}%"
            
        total = await database.fetch_val(count_query, count_params)
        
        # Create response objects
        windfarm_responses = [WindfarmResponse(**wf) for wf in windfarms]
        
        return WindfarmListResponse(
            windfarms=windfarm_responses,
            total=total,
            limit=limit,
            offset=offset
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch windfarms: {str(e)}"
        )


@router.get("/list", response_model=WindfarmListResponse)
async def list_all_windfarms(
    limit: int = 100,
    offset: int = 0,
    current_user: dict = Depends(require_admin)
):
    """
    Admin-only: List all windfarms with project name and turbine count.
    """
    try:
        query = """
        SELECT 
          w.id, 
          w.name, 
          w.description, 
          w.own_company, 
          w.location, 
          w.project_id,
          w.created_at, 
          w.updated_at,
          w.created_by,
          p.name AS project_name,
          (
            SELECT COUNT(*) FROM turbines t
            WHERE t.windfarm_id = w.id
          ) AS turbine_count
        FROM windfarms w
        INNER JOIN projects p ON w.project_id = p.id
        ORDER BY w.created_at DESC
        LIMIT :limit OFFSET :offset
        """
        results = await database.fetch_all(query, {"limit": limit, "offset": offset})
        
        # Enhance created_by information for each windfarm
        windfarms = []
        for row in results:
            windfarm_dict = dict(row)
            windfarm_dict = await windfarms_service.enhance_created_by_info(windfarm_dict)
            windfarms.append(windfarm_dict)

        total = await database.fetch_val("SELECT COUNT(*) FROM windfarms")

        return WindfarmListResponse(
            windfarms=[WindfarmResponse(**wf) for wf in windfarms],
            total=total or 0,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch all windfarms: {str(e)}"
        )


@router.put("/{windfarm_id}", response_model=WindfarmResponse)
async def update_windfarm(
    windfarm_id: str,
    windfarm_data: WindfarmUpdateRequest,
    request: Request,
    current_user: dict = Depends(require_user)
):
    """
    Cập nhật thông tin windfarm
    
    Yêu cầu quyền: Editor trở lên trong project chứa windfarm
    """
    
    try:
        # Get windfarm to check project
        windfarm = await windfarms_service.get_by_id(windfarm_id)
        if not windfarm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Windfarm not found"
            )
        
        # Check project access (Editor level required)
        await check_project_access(
            current_user["id"], windfarm["project_id"], required_role_level=2
        )
        
        # Get client IP
        ip_address = AuditLogger.get_client_ip(request)
        
        # Update windfarm
        update_data = windfarm_data.dict(exclude_unset=True)
        updated_windfarm = await windfarms_service.update(
            entity_id=windfarm_id,
            update_data=update_data,
            actor_id=current_user["id"],
            project_id=windfarm["project_id"],
            ip_address=ip_address
        )
        
        # Get project name and turbine count for response
        project_query = "SELECT name FROM projects WHERE id = :project_id"
        project = await database.fetch_one(project_query, {"project_id": windfarm["project_id"]})
        
        turbine_count_query = """
        SELECT COUNT(*) FROM turbines 
        WHERE windfarm_id = :windfarm_id
        """
        turbine_count = await database.fetch_val(turbine_count_query, {"windfarm_id": windfarm_id})
        
        # Enhance created_by information
        updated_windfarm = await windfarms_service.enhance_created_by_info(updated_windfarm)
        
        # Add missing fields for response
        updated_windfarm["project_name"] = project["name"] if project else None
        updated_windfarm["turbine_count"] = turbine_count or 0
        
        return WindfarmResponse(**updated_windfarm)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update windfarm: {str(e)}"
        )


@router.delete("/{windfarm_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_windfarm(
    windfarm_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Xóa windfarm (soft delete)
    
    Yêu cầu quyền: Editor trở lên trong project chứa windfarm
    """
    
    try:
        # Get windfarm to check project
        windfarm = await windfarms_service.get_by_id(windfarm_id)
        if not windfarm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Windfarm not found"
            )
        
        # Check project access (Editor level required)
        await check_project_access(
            current_user["id"], windfarm["project_id"], required_role_level=2
        )
        
        # Check if windfarm has turbines
        turbine_count_query = """
        SELECT COUNT(*) FROM turbines 
        WHERE windfarm_id = :windfarm_id
        """
        turbine_count = await database.fetch_val(
            turbine_count_query, {"windfarm_id": windfarm_id}
        )
        
        if turbine_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot delete windfarm with {turbine_count} active turbines. Please delete turbines first."
            )
        
        # Get client IP
        ip_address = AuditLogger.get_client_ip(request)
        
        # Soft delete windfarm
        await windfarms_service.delete(
            entity_id=windfarm_id,
            actor_id=current_user["id"],
            project_id=windfarm["project_id"],
            ip_address=ip_address,
            soft_delete=True
        )
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete windfarm: {str(e)}"
        )


# ===============================
# BULK OPERATIONS
# ===============================

@router.delete("/bulk", status_code=status.HTTP_200_OK)
async def bulk_delete_windfarms(
    windfarm_ids: List[str],
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """
    Xóa nhiều windfarms cùng lúc (soft delete)
    
    - **windfarm_ids**: Danh sách IDs của windfarms cần xóa
    
    Yêu cầu quyền: Editor trở lên trong tất cả projects chứa windfarms
    """
    
    try:
        if not windfarm_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one windfarm ID is required"
            )
        
        # Get all windfarms and verify access
        deleted_count = 0
        errors = []
        
        for windfarm_id in windfarm_ids:
            try:
                # Get windfarm
                windfarm = await windfarms_service.get_by_id(windfarm_id)
                if not windfarm:
                    errors.append(f"Windfarm {windfarm_id} not found")
                    continue
                
                # Check project access
                await check_project_access(
                    current_user["id"], windfarm["project_id"], required_role_level=2
                )
                
                # Check for turbines
                turbine_count_query = """
                SELECT COUNT(*) FROM turbines 
                WHERE windfarm_id = :windfarm_id
                """
                turbine_count = await database.fetch_val(
                    turbine_count_query, {"windfarm_id": windfarm_id}
                )
                
                if turbine_count > 0:
                    errors.append(f"Windfarm {windfarm_id} has {turbine_count} active turbines")
                    continue
                
                # Delete windfarm
                ip_address = AuditLogger.get_client_ip(request)
                await windfarms_service.delete(
                    entity_id=windfarm_id,
                    actor_id=current_user["id"],
                    project_id=windfarm["project_id"],
                    ip_address=ip_address,
                    soft_delete=True
                )
                
                deleted_count += 1
                
            except HTTPException as he:
                errors.append(f"Windfarm {windfarm_id}: {he.detail}")
            except Exception as e:
                errors.append(f"Windfarm {windfarm_id}: {str(e)}")
        
        return {
            "deleted_count": deleted_count,
            "total_requested": len(windfarm_ids),
            "errors": errors
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to bulk delete windfarms: {str(e)}"
        )
