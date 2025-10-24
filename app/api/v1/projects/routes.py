"""
Projects API Routes - Quản lý dự án gió
Cung cấp các endpoint để tạo, quản lý và thao tác với projects
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel

from app.db.database import database, projects_table, project_members_table
from app.db.models import (
    ProjectCreateRequest, ProjectUpdateRequest, ProjectResponse, ProjectListResponse,
    ProjectMemberResponse, ProjectRole
)
from app.services.base_service import ProjectContextService
from app.services.audit_service import AuditLogger
from app.utilities.permissions import check_project_access
from app.db.models import EntityType
from app.api.v1.users_admin.auth_routes import get_current_user, require_user, require_admin

router = APIRouter(prefix="/projects", tags=["projects"])

# Initialize service
projects_service = ProjectContextService(projects_table, EntityType.PROJECT)


# ===============================
# PROJECT CRUD OPERATIONS
# ===============================

@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_data: ProjectCreateRequest,
    request: Request,
    current_user: dict = Depends(require_user)
):
    """
    Tạo project mới
    
    - **name**: Tên project (required)
    - **description**: Mô tả project
    
    User tạo project sẽ tự động trở thành Owner
    """
    
    try:
        # Prepare project data
        create_data = project_data.dict()
        # ensure string for client schema consistency
        create_data["created_by"] = str(current_user["id"]) if current_user and current_user.get("id") else None
        

        # Get client IP
        ip_address = AuditLogger.get_client_ip(request)
        
        # Create project
        new_project = await projects_service.create(
            data=create_data,
            actor_id=current_user["id"],
            ip_address=ip_address
        )
        
        # Add creator as owner member
        member_data = {
            "project_id": new_project["id"],
            "user_id": current_user["id"],
            "role": ProjectRole.OWNER.value,
            "joined_at": datetime.utcnow()
        }
        
        member_insert = project_members_table.insert().values(member_data)
        await database.execute(member_insert)
        
        # Log member addition (no need for entity_id since composite key)
        await AuditLogger.log_create(
            actor_id=current_user["id"],
            entity_type=EntityType.PROJECT_MEMBER,
            entity_id=new_project["id"],  # Use project_id as reference
            entity_data=member_data,
            project_id=new_project["id"],
            ip_address=ip_address
        )
        
        # Enhance created_by info
        enhanced_project = await projects_service.enhance_created_by_info(new_project)
        
        return ProjectResponse(**enhanced_project)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create project: {str(e)}"
        )


@router.get("/", response_model=ProjectListResponse)
async def list_user_projects(
    limit: int = 50,
    offset: int = 0,
    current_user: dict = Depends(require_user)
):
    """
    Lấy danh sách projects mà user có quyền truy cập
    
    - **limit**: Số lượng results tối đa (default: 50)
    - **offset**: Bỏ qua số lượng results (default: 0)
    """
    
    try:
        # Query projects where user is a member with stats
        query = """
        SELECT DISTINCT 
            p.*, 
            pm.role as user_role, 
            pm.joined_at,
            (SELECT COUNT(*) FROM windfarms w WHERE w.project_id = p.id) as windfarm_count,
            (SELECT COUNT(*) FROM project_members pm2 WHERE pm2.project_id = p.id) as member_count,
            (
                SELECT COUNT(*) FROM turbines t 
                INNER JOIN windfarms w2 ON t.windfarm_id = w2.id 
                WHERE w2.project_id = p.id
            ) as turbine_count
        FROM projects p
        INNER JOIN project_members pm ON p.id = pm.project_id
        WHERE pm.user_id = :user_id
        """
        
        params = {"user_id": current_user["id"]}
        
        # Add ordering and pagination
        query += " ORDER BY p.created_at DESC LIMIT :limit OFFSET :offset"
        params.update({"limit": limit, "offset": offset})
        
        results = await database.fetch_all(query, params)
        
        # Get total count
        count_query = """
        SELECT COUNT(DISTINCT p.id)
        FROM projects p
        INNER JOIN project_members pm ON p.id = pm.project_id
        WHERE pm.user_id = :user_id
        """
        
        count_params = {"user_id": current_user["id"]}
        
        total = await database.fetch_val(count_query, count_params)
        
        # Format response
        projects = []
        for row in results:
            project_dict = dict(row)
            # Add user's role in this project
            project_dict["user_role"] = project_dict.pop("user_role")
            project_dict["user_joined_at"] = project_dict.pop("joined_at")
            
            # Add counts to response
            project_dict["windfarm_count"] = project_dict.get("windfarm_count", 0)
            project_dict["member_count"] = project_dict.get("member_count", 0)
            project_dict["turbine_count"] = project_dict.get("turbine_count", 0)
            
            # Enhance created_by information
            project_dict = await projects_service.enhance_created_by_info(project_dict)
            projects.append(project_dict)
        
        return ProjectListResponse(
            projects=projects,
            total=total or 0,
            limit=limit,
            offset=offset
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch projects: {str(e)}"
        )


@router.get("/list", response_model=ProjectListResponse)
async def list_all_projects(
    limit: int = 100,
    offset: int = 0,
    current_user: dict = Depends(require_admin)
):
    """
    Admin-only: List all projects with counts of windfarms, turbines, and members.
    """
    try:
        query = """
        SELECT 
          p.*, 
          (SELECT COUNT(*) FROM windfarms w WHERE w.project_id = p.id) AS windfarm_count,
          (SELECT COUNT(*) FROM project_members pm WHERE pm.project_id = p.id) AS member_count,
          (
            SELECT COUNT(*) FROM turbines t 
            INNER JOIN windfarms w2 ON t.windfarm_id = w2.id 
            WHERE w2.project_id = p.id
          ) AS turbine_count
        FROM projects p
        ORDER BY p.created_at DESC
        LIMIT :limit OFFSET :offset
        """

        results = await database.fetch_all(query, {"limit": limit, "offset": offset})
        
        # Enhance created_by information for each project
        projects = []
        for row in results:
            project_dict = dict(row)
            project_dict = await projects_service.enhance_created_by_info(project_dict)
            projects.append(project_dict)

        total = await database.fetch_val("SELECT COUNT(*) FROM projects")

        return ProjectListResponse(
            projects=projects,
            total=total or 0,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch all projects: {str(e)}"
        )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project_details(
    project_id: str,
    current_user: dict = Depends(require_user)
):
    """
    Lấy chi tiết project
    
    Yêu cầu quyền: Viewer trở lên
    """
    
    try:
        # Check project access (Viewer level required)
        project_data = await check_project_access(
            current_user["id"], project_id, required_role_level=1
        )
        
        # Enhance created_by information
        project_data = await projects_service.enhance_created_by_info(project_data)
        
        # Get additional project stats
        stats_query = """
        SELECT 
            (SELECT COUNT(*) FROM windfarms WHERE project_id = :project_id) as windfarm_count,
            (SELECT COUNT(*) FROM turbines t 
             INNER JOIN windfarms w ON t.windfarm_id = w.id 
             WHERE w.project_id = :project_id) as turbine_count,
            (SELECT COUNT(*) FROM project_members WHERE project_id = :project_id) as member_count
        """
        
        stats = await database.fetch_one(stats_query, {"project_id": project_id})
        
        # Add stats to project data
        project_response = dict(project_data)
        if stats:
            project_response.update({
                "windfarm_count": stats["windfarm_count"] or 0,
                "turbine_count": stats["turbine_count"] or 0,
                "member_count": stats["member_count"] or 0
            })
        
        return ProjectResponse(**project_response)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch project details: {str(e)}"
        )


# ===============================
# PROJECT UPDATE & DELETE
# ===============================

@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    project_data: ProjectUpdateRequest,
    request: Request,
    current_user: dict = Depends(require_admin)
):
    """
    Cập nhật thông tin project (chỉ admin)
    
    - **project_id**: ID của project cần cập nhật
    - **name**: Tên project mới (optional)
    - **description**: Mô tả project mới (optional)
    - **status**: Trạng thái project mới (optional)
    
    Yêu cầu quyền: Admin
    """
    
    try:
        # Check project access (Owner level required)
        await check_project_access(
            current_user["id"], project_id, required_role_level=3
        )
        
        # Prepare update data
        update_data = project_data.dict(exclude_unset=True)
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update"
            )
        
        # Update project using the service
        updated_project = await projects_service.update(
            entity_id=project_id,
            update_data=update_data,
            actor_id=current_user["id"],
            project_id=project_id,
            ip_address=request.client.host
        )
        
        # Get full project data with counts
        stats_query = """
        SELECT 
            (SELECT COUNT(*) FROM windfarms w WHERE w.project_id = :project_id) as windfarm_count,
            (SELECT COUNT(*) FROM project_members pm WHERE pm.project_id = :project_id) as member_count,
            (
                SELECT COUNT(*) FROM turbines t 
                INNER JOIN windfarms w2 ON t.windfarm_id = w2.id 
                WHERE w2.project_id = :project_id
            ) as turbine_count
        """
        
        stats = await database.fetch_one(stats_query, {"project_id": project_id})
        
        # Enhance created_by info
        enhanced_project = await projects_service.enhance_created_by_info(updated_project)
        
        # Add stats to updated project data
        project_response = dict(enhanced_project)
        if stats:
            project_response.update({
                "windfarm_count": stats["windfarm_count"] or 0,
                "turbine_count": stats["turbine_count"] or 0,
                "member_count": stats["member_count"] or 0
            })
        
        return ProjectResponse(**project_response)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update project: {str(e)}"
        )


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    request: Request,
    current_user: dict = Depends(require_admin)
):
    """
    Xóa project (chỉ admin)
    
    - **project_id**: ID của project cần xóa
    
    Yêu cầu quyền: Admin
    
    Lưu ý: Việc xóa project sẽ xóa tất cả windfarms và turbines liên quan
    """
    
    try:
        # Check project access (Owner level required)
        await check_project_access(
            current_user["id"], project_id, required_role_level=3
        )
        
        # Delete project using the service
        # Don't pass project_id to avoid FK constraint issue in audit_logs
        success = await projects_service.delete(
            entity_id=project_id,
            actor_id=current_user["id"],
            project_id=None,  # Set to None since project will be deleted
            ip_address=request.client.host
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        return {
            "status": "success",
            "message": "Project deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete project: {str(e)}"
        )
