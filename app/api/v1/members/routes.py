"""
Project Members API - Manage members within a project
Only project OWNER can add/update/remove members; all actions are audited.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
import sqlalchemy

from app.db.database import database, project_members_table, users_table
from app.db.models import (
    ProjectMemberResponse, ProjectMemberListResponse,
    AddMemberRequest, UpdateMemberRequest, ProjectRole, EntityType
)
from app.utilities.permissions import check_project_access
from app.services.audit_service import AuditLogger
from app.api.v1.users_admin.auth_routes import require_user


router = APIRouter(prefix="/members", tags=["members"])


def _row_to_member(row: sqlalchemy.engine.Row) -> ProjectMemberResponse:
    return ProjectMemberResponse(
        project_id=str(row["project_id"]),
        user_id=str(row["user_id"]),
        user_name=row["name"],
        user_email=row["email"],
        role=ProjectRole(row["role"]),
        can_invite=bool(row["can_invite"]),
        joined_at=row["joined_at"],
    )


@router.get("/my-role/{project_id}")
async def get_my_project_role(
    project_id: str,
    current_user: dict = Depends(require_user)
):
    """Debug endpoint: Check current user's role in a project."""
    try:
        # Check if project exists
        project_query = "SELECT id, name, created_by FROM projects WHERE id = :project_id"
        project = await database.fetch_one(project_query, {"project_id": project_id})
        
        if not project:
            return {
                "status": "project_not_found",
                "project_id": project_id,
                "user_id": current_user["id"]
            }
        
        # Check if user is member
        member_query = """
        SELECT pm.*, u.name as user_name, u.email
        FROM project_members pm
        INNER JOIN users u ON u.id = pm.user_id
        WHERE pm.project_id = :project_id AND pm.user_id = :user_id
        """
        member = await database.fetch_one(member_query, {
            "project_id": project_id,
            "user_id": current_user["id"]
        })
        
        return {
            "status": "ok" if member else "not_member",
            "project": {
                "id": str(project["id"]),
                "name": project["name"],
                "created_by": str(project["created_by"])
            },
            "user": {
                "id": current_user["id"],
                "name": current_user.get("name"),
                "email": current_user.get("email")
            },
            "membership": dict(member) if member else None,
            "is_creator": str(project["created_by"]) == str(current_user["id"])
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "project_id": project_id,
            "user_id": current_user["id"]
        }


@router.get("/project/{project_id}", response_model=ProjectMemberListResponse)
async def list_project_members(
    project_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(require_user)
):
    """List members of a project (Viewer+)."""
    # Access: at least viewer
    await check_project_access(current_user["id"], project_id, required_role_level=1)

    query = """
    SELECT pm.project_id, pm.user_id, pm.role, pm.can_invite, pm.joined_at,
           u.name, u.email
    FROM project_members pm
    INNER JOIN users u ON u.id = pm.user_id
    WHERE pm.project_id = :project_id
    ORDER BY u.name ASC
    LIMIT :limit OFFSET :offset
    """
    rows = await database.fetch_all(query, {"project_id": project_id, "limit": limit, "offset": offset})
    members = [_row_to_member(r) for r in rows]

    total = await database.fetch_val(
        "SELECT COUNT(*) FROM project_members WHERE project_id = :pid", {"pid": project_id}
    )
    return ProjectMemberListResponse(members=members, total=total or 0, limit=limit, offset=offset)


@router.get("/project/{project_id}/search-users")
async def search_users_for_project(
    project_id: str,
    query: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: dict = Depends(require_user)
):
    """Search users by email to add to project (OWNER only)."""
    await check_project_access(current_user["id"], project_id, required_permissions=["manage_members"])

    sql = """
    SELECT u.id, u.name, u.email
    FROM users u
    WHERE LOWER(u.email) LIKE :q
      AND NOT EXISTS (
        SELECT 1 FROM project_members pm
        WHERE pm.project_id = :pid AND pm.user_id = u.id
      )
    ORDER BY u.email ASC
    LIMIT :limit
    """
    rows = await database.fetch_all(sql, {"q": f"%{query.lower()}%", "pid": project_id, "limit": limit})
    return [{"id": str(r["id"]), "name": r["name"], "email": r["email"]} for r in rows]


@router.post("/project/{project_id}", response_model=ProjectMemberResponse, status_code=status.HTTP_201_CREATED)
async def add_member(
    project_id: str,
    payload: AddMemberRequest,
    request: Request,
    current_user: dict = Depends(require_user)
):
    """Add a user to project by email (OWNER only)."""
    # Require OWNER manage_members
    await check_project_access(current_user["id"], project_id, required_permissions=["manage_members"])

    # Find user by email
    user = await database.fetch_one(
        sqlalchemy.select(users_table).where(users_table.c.email == payload.email)
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Check not already a member
    exists_q = sqlalchemy.select(project_members_table).where(
        sqlalchemy.and_(
            project_members_table.c.project_id == project_id,
            project_members_table.c.user_id == user["id"],
        )
    )
    exists = await database.fetch_one(exists_q)
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already in project")

    # Insert member
    insert = project_members_table.insert().values(
        project_id=project_id,
        user_id=user["id"],
        role=payload.role.value,
        can_invite=payload.can_invite,
    )
    await database.execute(insert)

    # Fetch newly inserted membership with user info
    new_row = await database.fetch_one(
        """
        SELECT pm.project_id, pm.user_id, pm.role, pm.can_invite, pm.joined_at,
               u.name, u.email
        FROM project_members pm
        INNER JOIN users u ON u.id = pm.user_id
        WHERE pm.project_id = :pid AND pm.user_id = :uid
        """,
        {"pid": project_id, "uid": user["id"]},
    )

    # Audit
    ip = AuditLogger.get_client_ip(request)
    await AuditLogger.log_create(
        actor_id=current_user["id"],
        entity_type=EntityType.PROJECT_MEMBER,
        entity_id=project_id,
        entity_data={
            "project_id": project_id,
            "user_id": str(user["id"]),
            "role": payload.role.value,
            "can_invite": payload.can_invite,
        },
        project_id=project_id,
        ip_address=ip,
    )

    # Return member
    return _row_to_member(new_row)


@router.put("/project/{project_id}/{user_id}", response_model=ProjectMemberResponse)
async def update_member(
    project_id: str,
    user_id: str,
    payload: UpdateMemberRequest,
    request: Request,
    current_user: dict = Depends(require_user)
):
    """Update a member's role/can_invite (OWNER only)."""
    await check_project_access(current_user["id"], project_id, required_permissions=["manage_members"])

    # Get current membership with user info
    cur_q = """
      SELECT pm.*, u.name, u.email FROM project_members pm
      INNER JOIN users u ON u.id = pm.user_id
      WHERE pm.project_id = :pid AND pm.user_id = :uid
    """
    cur = await database.fetch_one(cur_q, {"pid": project_id, "uid": user_id})
    if not cur:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    before = {
        "project_id": project_id,
        "user_id": str(user_id),
        "role": cur["role"],
        "can_invite": bool(cur["can_invite"]),
    }

    updates: Dict[str, Any] = {}
    if payload.role is not None:
        updates["role"] = payload.role.value
    if payload.can_invite is not None:
        updates["can_invite"] = payload.can_invite

    if not updates:
        # No changes; return current
        return _row_to_member(cur)

    upd = (
        project_members_table.update()
        .where(
            sqlalchemy.and_(
                project_members_table.c.project_id == project_id,
                project_members_table.c.user_id == user_id,
            )
        )
        .values(**updates)
    )
    await database.execute(upd)

    # Fetch updated
    new = await database.fetch_one(cur_q, {"pid": project_id, "uid": user_id})

    # Audit
    ip = AuditLogger.get_client_ip(request)
    after = {
        "project_id": project_id,
        "user_id": str(user_id),
        "role": new["role"],
        "can_invite": bool(new["can_invite"]),
    }
    await AuditLogger.log_update(
        actor_id=current_user["id"],
        entity_type=EntityType.PROJECT_MEMBER,
        entity_id=project_id,
        before_data=before,
        after_data=after,
        project_id=project_id,
        ip_address=ip,
    )

    return _row_to_member(new)


@router.delete("/project/{project_id}/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    project_id: str,
    user_id: str,
    request: Request,
    current_user: dict = Depends(require_user)
):
    """Remove a member from project (OWNER only)."""
    await check_project_access(current_user["id"], project_id, required_permissions=["manage_members"])

    # Get record
    cur = await database.fetch_one(
        sqlalchemy.select(project_members_table).where(
            sqlalchemy.and_(
                project_members_table.c.project_id == project_id,
                project_members_table.c.user_id == user_id,
            )
        )
    )
    if not cur:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    # Prevent removing oneself inadvertently? optional safeguard
    if str(current_user["id"]) == str(user_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove yourself")

    # Remove
    await database.execute(
        project_members_table.delete().where(
            sqlalchemy.and_(
                project_members_table.c.project_id == project_id,
                project_members_table.c.user_id == user_id,
            )
        )
    )

    # Audit
    ip = AuditLogger.get_client_ip(request)
    await AuditLogger.log_delete(
        actor_id=current_user["id"],
        entity_type=EntityType.PROJECT_MEMBER,
        entity_id=project_id,
        entity_data={
            "project_id": project_id,
            "user_id": str(user_id),
            "role": cur["role"],
            "can_invite": bool(cur["can_invite"]),
        },
        project_id=project_id,
        ip_address=ip,
    )

    return None
