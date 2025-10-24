"""
Audit API Routes - Admin-only access to system-wide audit logs
Provides endpoint to view all user actions with auto-cleanup after 30 days
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel

from app.services.audit_service import AuditLogger
from app.api.v1.users_admin.auth_routes import require_admin

router = APIRouter(prefix="/audit", tags=["audit"])


# ===============================
# RESPONSE MODELS
# ===============================

class AuditLogResponse(BaseModel):
    """Single audit log response"""
    id: str
    actor_id: str
    actor_name: str
    actor_email: str
    action: str
    entity_type: str
    entity_id: str
    entity_name: Optional[str] = None
    description: Optional[str] = None
    project_id: Optional[str] = None
    before_data: Optional[Dict[str, Any]] = None
    after_data: Optional[Dict[str, Any]] = None
    changes: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    expires_at: Optional[datetime] = None


class AuditLogListResponse(BaseModel):
    """List of audit logs with pagination"""
    logs: List[AuditLogResponse]
    total: int
    limit: int
    offset: int


# ===============================
# API ENDPOINTS
# ===============================

@router.get("/logs", response_model=AuditLogListResponse)
async def get_all_audit_logs(
    limit: int = Query(100, ge=1, le=1000, description="Number of logs to return"),
    offset: int = Query(0, ge=0, description="Number of logs to skip"),
    actor_id: Optional[str] = Query(None, description="Filter by user ID"),
    project_id: Optional[str] = Query(None, description="Filter by project ID"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type (PROJECT, WINDFARM, TURBINE, etc.)"),
    action: Optional[str] = Query(None, description="Filter by action (CREATE, UPDATE, DELETE, etc.)"),
    start_date: Optional[datetime] = Query(None, description="Filter logs after this date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="Filter logs before this date (ISO format)"),
    current_user: dict = Depends(require_admin)
):
    """
    Get all audit logs with optional filtering (Admin only)
    
    This endpoint provides comprehensive view of all user actions in the system:
    - **limit**: Maximum number of logs to return (1-1000)
    - **offset**: Number of logs to skip for pagination
    - **actor_id**: Filter by specific user
    - **project_id**: Filter by specific project
    - **entity_type**: Filter by entity type (PROJECT, WINDFARM, TURBINE, PROJECT_MEMBER)
    - **action**: Filter by action type (CREATE, UPDATE, DELETE, STATUS_CHANGE, MEMBER_ADDED, MEMBER_REMOVED)
    - **start_date**: Show logs after this date
    - **end_date**: Show logs before this date
    
    Returns logs sorted by timestamp (newest first) with full user information.
    Logs automatically expire after 30 days.
    """
    
    try:
        # Get logs with filters
        logs = await AuditLogger.get_all_logs(
            limit=limit,
            offset=offset,
            actor_id=actor_id,
            project_id=project_id,
            entity_type=entity_type,
            action=action,
            start_date=start_date,
            end_date=end_date
        )
        
        # Get total count with same filters
        total = await AuditLogger.count_logs(
            actor_id=actor_id,
            project_id=project_id,
            entity_type=entity_type,
            action=action,
            start_date=start_date,
            end_date=end_date
        )
        
        # Convert to response objects
        log_responses = [AuditLogResponse(**log) for log in logs]
        
        return AuditLogListResponse(
            logs=log_responses,
            total=total or 0,
            limit=limit,
            offset=offset
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch audit logs: {str(e)}"
        )


@router.post("/cleanup")
async def cleanup_old_audit_logs(
    current_user: dict = Depends(require_admin)
):
    """
    Manually trigger cleanup of audit logs older than 30 days (Admin only)
    
    This endpoint allows admins to manually run the cleanup process
    that removes audit logs that have passed their expiration date.
    
    Returns the number of deleted log entries.
    """
    
    try:
        deleted_count = await AuditLogger.cleanup_old_logs()
        
        return {
            "status": "success",
            "message": f"Successfully cleaned up {deleted_count} old audit logs",
            "deleted_count": deleted_count
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup audit logs: {str(e)}"
        )


@router.get("/stats")
async def get_audit_stats(
    current_user: dict = Depends(require_admin)
):
    """
    Get statistics about audit logs (Admin only)
    
    Returns overview statistics including:
    - Total number of audit logs
    - Logs by action type
    - Logs by entity type
    - Recent activity summary
    """
    
    try:
        # Get total count
        total_logs = await AuditLogger.count_logs()
        
        # Get recent logs (last 7 days)
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        recent_logs = await AuditLogger.count_logs(start_date=seven_days_ago)
        
        # You could add more detailed statistics here if needed
        
        return {
            "total_logs": total_logs or 0,
            "recent_logs_7_days": recent_logs or 0,
            "retention_days": 30,
            "status": "active"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch audit statistics: {str(e)}"
        )
