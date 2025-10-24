"""
Permission utilities for project management
Handles authorization logic for different user roles
"""

from typing import Optional, Dict, Any
from fastapi import HTTPException, Request, status
import sqlalchemy
from app.db.database import database, project_members_table, projects_table
from app.db.models import ProjectRole


async def get_user_project_role(user_id: str, project_id: str) -> Optional[ProjectRole]:
    """Get user's role in a specific project"""
    query = sqlalchemy.select(project_members_table).where(
        sqlalchemy.and_(
            project_members_table.c.user_id == user_id,
            project_members_table.c.project_id == project_id
        )
    )
    member = await database.fetch_one(query)

    if not member:
        return None

    return ProjectRole(member["role"])


async def check_project_access(
    user_id: str, 
    project_id: str, 
    required_permissions: list = None,
    required_role_level: int = None
) -> Dict[str, Any]:
    """
    Check if user has access to project and return project info with role
    
    Args:
        user_id: User ID to check
        project_id: Project ID to check access for
        required_permissions: List of required permissions like ['read', 'write', 'delete', 'invite']
        required_role_level: Minimum role level (1=Viewer, 2=Editor, 3=Owner)
    
    Returns:
        Dict with project data and user role info
        
    Raises:
        HTTPException: If user doesn't have required access
    """
    # First check if project exists
    project_data = await check_project_exists(project_id)
    
    # Get user role in project
    role = await get_user_project_role(user_id, project_id)
    
    if not role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"status": "error", "message": "Access denied: Not a project member"}
        )
    
    # Check role level if specified
    if required_role_level is not None:
        role_levels = {
            ProjectRole.VIEWER: 1,
            ProjectRole.EDITOR: 2, 
            ProjectRole.OWNER: 3
        }
        user_level = role_levels.get(role, 0)
        
        if user_level < required_role_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"status": "error", "message": "Insufficient role level"}
            )
    
    # Check specific permissions if specified
    if required_permissions is None:
        required_permissions = ['read']
    
    # Get user role in project
    role = await get_user_project_role(user_id, project_id)
    
    if not role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"status": "error", "message": "Access denied: Not a project member"}
        )
    
    # Define role permissions
    role_permissions = {
        ProjectRole.OWNER: ['read', 'write', 'delete', 'invite', 'manage_members'],
        ProjectRole.EDITOR: ['read', 'write'],  # No delete permission
        ProjectRole.VIEWER: ['read']
    }
    
    user_permissions = role_permissions.get(role, [])
    
    # Check if user has all required permissions
    missing_permissions = set(required_permissions) - set(user_permissions)
    
    if missing_permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "status": "error", 
                "message": f"Insufficient permissions. Missing: {', '.join(missing_permissions)}"
            }
        )
    
    # Check can_invite permission separately (it's a specific field)
    can_invite = False
    if 'invite' in required_permissions:
        member_query = sqlalchemy.select(project_members_table).where(
            sqlalchemy.and_(
                project_members_table.c.user_id == user_id,
                project_members_table.c.project_id == project_id
            )
        )
        member = await database.fetch_one(member_query)
        can_invite = member["can_invite"] if member else False
        
        if role != ProjectRole.OWNER and not can_invite:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"status": "error", "message": "Not authorized to invite members"}
            )
    
    # Add role info to project data
    project_data.update({
        "user_role": role,
        "user_permissions": user_permissions,
        "user_can_invite": can_invite
    })
    
    return project_data


async def check_project_exists(project_id: str) -> Dict[str, Any]:
    """Check if project exists and return project info"""
    query = sqlalchemy.select(projects_table).where(projects_table.c.id == project_id)
    project = await database.fetch_one(query)
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "error", "message": "Project not found"}
        )
    
    return dict(project)


async def is_admin_user(user_id: str) -> bool:
    """Check if user is a system admin"""
    from app.db.database import users_table
    
    query = sqlalchemy.select(users_table).where(users_table.c.id == user_id)
    user = await database.fetch_one(query)
    
    return user and user.role == 'admin'


def require_project_permission(required_permissions: list):
    """
    Decorator factory for checking project permissions
    
    Usage:
        @require_project_permission(['read', 'write'])
        async def update_project(project_id: str, current_user, ...):
            pass
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Extract project_id from kwargs or args
            project_id = kwargs.get('project_id') or (args[0] if args else None)
            
            # This would need to be adapted based on how you pass current user
            # For now, assuming it's in kwargs as 'current_user'
            current_user = kwargs.get('current_user')
            
            if not current_user or not project_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"status": "error", "message": "Missing required parameters"}
                )
            
            # Check permissions
            await check_project_access(
                user_id=current_user.id,
                project_id=project_id,
                required_permissions=required_permissions
            )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


class PermissionChecker:
    """Helper class for permission checking in route handlers"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
    
    async def can_read_project(self, project_id: str) -> bool:
        """Check if user can read project"""
        try:
            await check_project_access(self.user_id, project_id, ['read'])
            return True
        except HTTPException:
            return False
    
    async def can_write_project(self, project_id: str) -> bool:
        """Check if user can write to project"""
        try:
            await check_project_access(self.user_id, project_id, ['read', 'write'])
            return True
        except HTTPException:
            return False
    
    async def can_delete_project(self, project_id: str) -> bool:
        """Check if user can delete from project"""
        try:
            await check_project_access(self.user_id, project_id, ['read', 'write', 'delete'])
            return True
        except HTTPException:
            return False
    
    async def can_invite_members(self, project_id: str) -> bool:
        """Check if user can invite members to project"""
        try:
            await check_project_access(self.user_id, project_id, ['invite'])
            return True
        except HTTPException:
            return False


async def get_user_projects_with_role(user_id: str) -> list:
    """Get all projects user is member of with their roles"""
    query = sqlalchemy.select(
        projects_table,
        project_members_table.c.role,
        project_members_table.c.joined_at
    ).select_from(
        projects_table.join(
            project_members_table,
            projects_table.c.id == project_members_table.c.project_id
        )
    ).where(project_members_table.c.user_id == user_id)
    
    results = await database.fetch_all(query)
    return [dict(row) for row in results]


async def require_project_role(
    user_id: str, 
    project_id: str, 
    required_role: ProjectRole
) -> Dict[str, Any]:
    """
    Require specific role for project access
    
    Args:        
        user_id: User ID to check
        project_id: Project ID to check access for
        required_role: Required project role
    
    Returns:
        Dict with project data and user role info
        
    Raises:
        HTTPException: If user doesn't have required role
    """
    role_levels = {
        ProjectRole.VIEWER: 1,
        ProjectRole.EDITOR: 2,
        ProjectRole.OWNER: 3
    }
    
    required_level = role_levels.get(required_role, 0)
    return await check_project_access(user_id, project_id, required_role_level=required_level)


async def check_turbine_access(
    turbine_id: str,
    current_user: Dict[str, Any],
    min_role: str = "viewer"
) -> Dict[str, Any]:
    """
    Check if user has access to turbine through project membership
    
    Flow: turbine -> windfarm -> project -> check user role
    
    Args:
        turbine_id: UUID of turbine
        current_user: Dict with user info (id, role, etc.)
        min_role: Minimum role required ('viewer', 'editor', 'owner')
        
    Returns:
        Dict with turbine, windfarm, project info
        
    Raises:
        HTTPException: If user doesn't have access or turbine not found
    """
    from app.db.database import turbines_table, windfarms_table
    
    # Get turbine with windfarm and project info
    query = sqlalchemy.select(
        turbines_table.c.id,
        turbines_table.c.name,
        turbines_table.c.windfarm_id,
        windfarms_table.c.name.label('windfarm_name'),
        windfarms_table.c.project_id
    ).select_from(
        turbines_table.join(
            windfarms_table,
            turbines_table.c.windfarm_id == windfarms_table.c.id
        )
    ).where(turbines_table.c.id == turbine_id)
    
    turbine = await database.fetch_one(query)
    
    if not turbine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "error", "message": "Turbine không tồn tại"}
        )
    
    # Check project access with required role
    role_levels = {
        "viewer": 1,
        "editor": 2,
        "owner": 3
    }
    
    required_level = role_levels.get(min_role.lower(), 1)
    
    try:
        await check_project_access(
            user_id=current_user['id'],
            project_id=str(turbine['project_id']),
            required_role_level=required_level
        )
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "status": "error", 
                "message": f"Access denied: Requires {min_role} role or higher"
            }
        )
    
    return {
        'turbine_id': str(turbine['id']),
        'turbine_name': turbine['name'],
        'windfarm_id': str(turbine['windfarm_id']),
        'windfarm_name': turbine['windfarm_name'],
        'project_id': str(turbine['project_id'])
    }
