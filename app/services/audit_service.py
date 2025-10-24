"""
Unified Audit logging service for tracking all user actions
Records all CRUD operations and system events with auto-cleanup after 30 days
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import uuid
import sqlalchemy
from fastapi import Request

from app.db.database import database, audit_logs_table, users_table
from app.db.models import AuditAction, EntityType


class AuditLogger:
    """Unified service for logging all user actions and system events"""
    
    @staticmethod
    async def log(
        actor_id: str,
        action: AuditAction,
        entity_type: EntityType,
        entity_id: str,
        entity_name: Optional[str] = None,
        project_id: Optional[str] = None,
        before_data: Optional[Dict[str, Any]] = None,
        after_data: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Log any user action to the unified audit log
        
        Args:
            actor_id: ID of user performing the action
            action: Type of action performed  
            entity_type: Type of entity being acted upon
            entity_id: ID of the specific entity
            entity_name: Name of the entity for easy reference
            project_id: Project context (if applicable)
            before_data: Entity state before the action
            after_data: Entity state after the action
            ip_address: IP address of the actor
            user_agent: User agent string
            metadata: Additional context information
            
        Returns:
            ID of the created audit log entry
        """
        
        log_id = str(uuid.uuid4())
        
        # Generate human-readable description
        description = AuditLogger._generate_description(
            action, entity_type, entity_name, before_data, after_data
        )
        
        # Calculate changes if both before and after data exist
        changes = None
        if before_data and after_data:
            changes = AuditLogger._calculate_changes(before_data, after_data)
        
        # Clean data for JSON serialization
        def clean_for_json(data):
            if data is None:
                return None
            import json
            return json.loads(json.dumps(data, default=str))
        
        # Insert audit log
        insert_data = {
            "id": log_id,
            "actor_id": actor_id,
            "action": action.value,
            "entity_type": entity_type.value,
            "entity_id": entity_id,
            "entity_name": entity_name,
            "description": description,
            "project_id": project_id,
            "before_data": clean_for_json(before_data),
            "after_data": clean_for_json(after_data),
            "changes": clean_for_json(changes),
            "ip_address": ip_address,
            "user_agent": user_agent,
            "metadata": clean_for_json(metadata)
        }
        
        query = audit_logs_table.insert().values(**insert_data)
        await database.execute(query)
        
        return log_id
    
    @staticmethod
    def _generate_description(
        action: AuditAction,
        entity_type: EntityType, 
        entity_name: Optional[str],
        before_data: Optional[Dict[str, Any]],
        after_data: Optional[Dict[str, Any]]
    ) -> str:
        """Generate human-readable description of the action"""
        
        entity_display = entity_name or f"{entity_type.value}"
        
        if action == AuditAction.CREATE:
            return f"Created {entity_type.value.lower()} '{entity_display}'"
        elif action == AuditAction.UPDATE:
            return f"Updated {entity_type.value.lower()} '{entity_display}'"  
        elif action == AuditAction.DELETE:
            return f"Deleted {entity_type.value.lower()} '{entity_display}'"
        elif action == AuditAction.STATUS_CHANGE:
            if before_data and after_data:
                old_status = before_data.get('status', 'unknown')
                new_status = after_data.get('status', 'unknown')
                return f"Changed status of {entity_type.value.lower()} '{entity_display}' from {old_status} to {new_status}"
            return f"Changed status of {entity_type.value.lower()} '{entity_display}'"
        elif action == AuditAction.MEMBER_ADDED:
            return f"Added member to {entity_type.value.lower()} '{entity_display}'"
        elif action == AuditAction.MEMBER_REMOVED:
            return f"Removed member from {entity_type.value.lower()} '{entity_display}'"
        else:
            return f"Performed {action.value.lower()} on {entity_type.value.lower()} '{entity_display}'"
    
    @staticmethod 
    def _calculate_changes(before_data: Dict[str, Any], after_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate what fields changed between before and after data"""
        
        changes = {}
        all_keys = set(before_data.keys()) | set(after_data.keys())
        
        for key in all_keys:
            old_value = before_data.get(key)
            new_value = after_data.get(key)
            
            if old_value != new_value:
                changes[key] = {
                    "from": old_value,
                    "to": new_value
                }
                
        return changes
    
    @staticmethod
    def get_client_ip(request: Request) -> Optional[str]:
        """Extract client IP from request"""
        if request:
            return request.client.host if request.client else None
        return None
    
    @staticmethod
    def get_user_agent(request: Request) -> Optional[str]:
        """Extract user agent from request"""
        if request:
            return request.headers.get("user-agent")
        return None
    
    @staticmethod
    async def get_all_logs(
        limit: int = 100,
        offset: int = 0,
        actor_id: Optional[str] = None,
        project_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        action: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all audit logs with optional filtering (Admin only)
        """
        
        # Base query with user information
        query = sqlalchemy.select(
            audit_logs_table,
            users_table.c.name.label("actor_name"),
            users_table.c.email.label("actor_email")
        ).select_from(
            audit_logs_table.join(users_table, audit_logs_table.c.actor_id == users_table.c.id)
        )
        
        # Apply filters
        conditions = []
        
        if actor_id:
            conditions.append(audit_logs_table.c.actor_id == actor_id)
        if project_id:
            conditions.append(audit_logs_table.c.project_id == project_id)
        if entity_type:
            conditions.append(audit_logs_table.c.entity_type == entity_type)
        if action:
            conditions.append(audit_logs_table.c.action == action)
        if start_date:
            conditions.append(audit_logs_table.c.timestamp >= start_date)
        if end_date:
            conditions.append(audit_logs_table.c.timestamp <= end_date)
            
        if conditions:
            query = query.where(sqlalchemy.and_(*conditions))
        
        # Order by timestamp descending
        query = query.order_by(audit_logs_table.c.timestamp.desc())
        
        # Apply pagination
        query = query.limit(limit).offset(offset)
        
        results = await database.fetch_all(query)
        
        # Convert results to proper format
        formatted_results = []
        for row in results:
            data = dict(row)
            
            # Convert UUID fields to strings
            for field in ['id', 'actor_id', 'entity_id', 'project_id']:
                if data.get(field):
                    data[field] = str(data[field])
            
            # Convert IP address to string
            if data.get('ip_address'):
                data['ip_address'] = str(data['ip_address'])
            
            # Ensure description is not None
            if data.get('description') is None:
                data['description'] = f"Action {data.get('action', 'UNKNOWN')} on {data.get('entity_type', 'UNKNOWN')}"
            
            # Ensure entity_name has default value
            if data.get('entity_name') is None:
                data['entity_name'] = f"{data.get('entity_type', 'Unknown')} {data.get('entity_id', '')[:8]}"
            
            formatted_results.append(data)
            
        return formatted_results
    
    @staticmethod
    async def count_logs(
        actor_id: Optional[str] = None,
        project_id: Optional[str] = None, 
        entity_type: Optional[str] = None,
        action: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> int:
        """
        Count audit logs with optional filtering
        """
        
        query = sqlalchemy.select(sqlalchemy.func.count()).select_from(audit_logs_table)
        
        # Apply same filters as get_all_logs
        conditions = []
        
        if actor_id:
            conditions.append(audit_logs_table.c.actor_id == actor_id)
        if project_id:
            conditions.append(audit_logs_table.c.project_id == project_id)
        if entity_type:
            conditions.append(audit_logs_table.c.entity_type == entity_type)
        if action:
            conditions.append(audit_logs_table.c.action == action)
        if start_date:
            conditions.append(audit_logs_table.c.timestamp >= start_date)
        if end_date:
            conditions.append(audit_logs_table.c.timestamp <= end_date)
            
        if conditions:
            query = query.where(sqlalchemy.and_(*conditions))
        
        return await database.fetch_val(query)
    
    @staticmethod
    async def cleanup_old_logs() -> int:
        """
        Delete audit logs older than 30 days (expired logs)
        Returns number of deleted records
        """
        
        query = audit_logs_table.delete().where(
            audit_logs_table.c.expires_at < datetime.utcnow()
        )
        
        result = await database.execute(query)
        return result
    
    # ===============================
    # COMPATIBILITY METHODS (for existing code)
    # ===============================
    
    @staticmethod
    async def log_create(
        actor_id: str,
        entity_type: EntityType,
        entity_id: str,
        entity_data: Dict[str, Any],
        project_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> str:
        """Compatibility method for log_create"""
        entity_name = entity_data.get('name') or entity_data.get('title')
        return await AuditLogger.log(
            actor_id=actor_id,
            action=AuditAction.CREATE,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            project_id=project_id,
            after_data=entity_data,
            metadata=metadata,
            ip_address=ip_address
        )

    @staticmethod
    async def log_update(
        actor_id: str,
        entity_type: EntityType,
        entity_id: str,
        before_data: Dict[str, Any],
        after_data: Dict[str, Any],
        project_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> str:
        """Compatibility method for log_update"""
        entity_name = after_data.get('name') or after_data.get('title') or before_data.get('name') or before_data.get('title')
        return await AuditLogger.log(
            actor_id=actor_id,
            action=AuditAction.UPDATE,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            project_id=project_id,
            before_data=before_data,
            after_data=after_data,
            metadata=metadata,
            ip_address=ip_address
        )

    @staticmethod
    async def log_delete(
        actor_id: str,
        entity_type: EntityType,
        entity_id: str,
        entity_data: Dict[str, Any],
        project_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> str:
        """Compatibility method for log_delete"""
        entity_name = entity_data.get('name') or entity_data.get('title')
        return await AuditLogger.log(
            actor_id=actor_id,
            action=AuditAction.DELETE,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_name=entity_name,
            project_id=project_id,
            before_data=entity_data,
            metadata=metadata,
            ip_address=ip_address
        )

    @staticmethod
    async def log_member_added(
        actor_id: str,
        project_id: str,
        member_id: str,
        member_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> str:
        """Compatibility method for log_member_added"""
        entity_name = member_data.get('name') or member_data.get('email')
        return await AuditLogger.log(
            actor_id=actor_id,
            action=AuditAction.MEMBER_ADDED,
            entity_type=EntityType.PROJECT_MEMBER,
            entity_id=member_id,
            entity_name=entity_name,
            project_id=project_id,
            after_data=member_data,
            metadata=metadata,
            ip_address=ip_address
        )

    @staticmethod
    async def log_member_removed(
        actor_id: str,
        project_id: str,
        member_id: str,
        member_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> str:
        """Compatibility method for log_member_removed"""
        entity_name = member_data.get('name') or member_data.get('email')
        return await AuditLogger.log(
            actor_id=actor_id,
            action=AuditAction.MEMBER_REMOVED,
            entity_type=EntityType.PROJECT_MEMBER,
            entity_id=member_id,
            entity_name=entity_name,
            project_id=project_id,
            before_data=member_data,
            metadata=metadata,
            ip_address=ip_address
        )

    @staticmethod
    async def log_status_change(
        actor_id: str,
        entity_type: EntityType,
        entity_id: str,
        old_status: str,
        new_status: str,
        project_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> str:
        """Compatibility method for log_status_change"""
        status_metadata = {
            "old_status": old_status,
            "new_status": new_status,
            **(metadata or {})
        }
        
        return await AuditLogger.log(
            actor_id=actor_id,
            action=AuditAction.STATUS_CHANGE,
            entity_type=entity_type,
            entity_id=entity_id,
            project_id=project_id,
            before_data={"status": old_status},
            after_data={"status": new_status},
            metadata=status_metadata,
            ip_address=ip_address
        )