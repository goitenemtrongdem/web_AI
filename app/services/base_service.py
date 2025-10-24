"""
Base service class for common CRUD operations
Provides reusable methods for database operations and validation
"""

from typing import Dict, Any, List, Optional, Type
from datetime import datetime
import uuid
import sqlalchemy
from sqlalchemy import Table
from pydantic import BaseModel
from fastapi import HTTPException, status

from app.db.database import database
from app.services.audit_service import AuditLogger
from app.db.models import EntityType, AuditAction


class BaseService:
    """Base service class with common CRUD operations"""
    
    def __init__(self, table: Table, entity_type: EntityType):
        self.table = table
        self.entity_type = entity_type
    
    async def create(
        self,
        data: Dict[str, Any],
        actor_id: str,
        project_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new entity
        
        Args:
            data: Entity data
            actor_id: ID of user creating the entity
            project_id: Project context
            ip_address: IP address of actor
            
        Returns:
            Created entity data
        """
        
        # Generate ID if not provided
        if "id" not in data:
            data["id"] = str(uuid.uuid4())
        
        # Add timestamps
        data["created_at"] = datetime.utcnow()
        data["updated_at"] = datetime.utcnow()
        
        # Add created_by if not provided and actor_id is available
        if "created_by" not in data and actor_id:
            data["created_by"] = actor_id
        
        # Insert into database
        query = self.table.insert().values(data)
        await database.execute(query)
        
        # Log the creation
        await AuditLogger.log_create(
            actor_id=actor_id,
            entity_type=self.entity_type,
            entity_id=data["id"],
            entity_data=data,
            project_id=project_id,
            ip_address=ip_address
        )
        
        return data
    
    async def get_by_id(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Get entity by ID
        
        Args:
            entity_id: ID of the entity
            
        Returns:
            Entity data if found
        """
        
        query = sqlalchemy.select(self.table).where(
            self.table.c.id == entity_id
        )
        result = await database.fetch_one(query)
        return dict(result) if result else None
    
    async def enhance_created_by_info(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhance entity with full created_by information (id, name, email)
        
        Args:
            entity: Entity data with created_by UUID
            
        Returns:
            Enhanced entity with created_by as {id, name, email}
        """
        if not entity or not entity.get('created_by'):
            return entity
        
        # Check if already enhanced (created_by is dict instead of UUID)
        if isinstance(entity['created_by'], dict):
            return entity
            
        from app.db.database import users_table
        
        # Get user info for created_by
        user_query = sqlalchemy.select(users_table).where(
            users_table.c.id == entity['created_by']
        )
        user = await database.fetch_one(user_query)
        
        if user:
            # Replace created_by UUID with full info
            enhanced_entity = entity.copy()
            enhanced_entity['created_by'] = {
                'id': str(user.id),
                'name': user.name,
                'email': user.email
            }
            return enhanced_entity
        
        return entity
    
    async def get_by_id_enhanced(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Get entity by ID with enhanced created_by information
        
        Args:
            entity_id: ID of the entity
            
        Returns:
            Enhanced entity data if found
        """
        entity = await self.get_by_id(entity_id)
        if not entity:
            return None
            
        return await self.enhance_created_by_info(entity)
    
    async def update(
        self,
        entity_id: str,
        update_data: Dict[str, Any],
        actor_id: str,
        project_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update an entity
        
        Args:
            entity_id: ID of the entity to update
            update_data: Data to update
            actor_id: ID of user updating the entity
            project_id: Project context
            ip_address: IP address of actor
            
        Returns:
            Updated entity data
        """
        
        # Get current data for audit log
        current_data = await self.get_by_id(entity_id)
        if not current_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{self.entity_type.value.title()} not found"
            )
        
        # Add update timestamp
        update_data["updated_at"] = datetime.utcnow()
        
        # Update in database
        query = self.table.update().where(
            self.table.c.id == entity_id
        ).values(update_data)
        
        await database.execute(query)
        
        # Get updated data
        updated_data = await self.get_by_id(entity_id)
        
        # Log the update
        await AuditLogger.log_update(
            actor_id=actor_id,
            entity_type=self.entity_type,
            entity_id=entity_id,
            before_data=current_data,
            after_data=updated_data,
            project_id=project_id,
            ip_address=ip_address
        )
        
        return updated_data
    
    async def delete(
        self,
        entity_id: str,
        actor_id: str,
        project_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        soft_delete: bool = True
    ) -> bool:
        """
        Delete an entity
        
        Args:
            entity_id: ID of the entity to delete
            actor_id: ID of user deleting the entity
            project_id: Project context
            ip_address: IP address of actor
            soft_delete: Whether to perform soft delete
            
        Returns:
            True if deleted successfully
        """
        
        # Get current data for audit log
        current_data = await self.get_by_id(entity_id)
        if not current_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{self.entity_type.value.title()} not found"
            )
        
        if soft_delete and "deleted_at" in self.table.c:
            # Soft delete
            query = self.table.update().where(
                self.table.c.id == entity_id
            ).values(
                deleted_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
        else:
            # Hard delete
            query = self.table.delete().where(
                self.table.c.id == entity_id
            )
        
        await database.execute(query)
        
        # Log the deletion
        await AuditLogger.log_delete(
            actor_id=actor_id,
            entity_type=self.entity_type,
            entity_id=entity_id,
            entity_data=current_data,
            project_id=project_id,
            ip_address=ip_address
        )
        
        return True
    
    async def list_entities(
        self,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        order_desc: bool = True,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        List entities with filtering and pagination
        
        Args:
            filters: Dictionary of filter conditions
            order_by: Column to order by
            order_desc: Whether to order descending
            limit: Maximum number of results
            offset: Number of results to skip
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            List of entities
        """
        
        query = sqlalchemy.select(self.table)
        
        # Apply filters
        conditions = []
        
        # Exclude soft-deleted entities by default
        if not include_deleted and "deleted_at" in self.table.c:
            conditions.append(self.table.c.deleted_at.is_(None))
        
        if filters:
            for key, value in filters.items():
                if hasattr(self.table.c, key):
                    if isinstance(value, list):
                        conditions.append(getattr(self.table.c, key).in_(value))
                    else:
                        conditions.append(getattr(self.table.c, key) == value)
        
        if conditions:
            query = query.where(sqlalchemy.and_(*conditions))
        
        # Apply ordering
        if order_by and hasattr(self.table.c, order_by):
            order_column = getattr(self.table.c, order_by)
            if order_desc:
                order_column = order_column.desc()
            query = query.order_by(order_column)
        else:
            # Default ordering by created_at descending
            if "created_at" in self.table.c:
                query = query.order_by(self.table.c.created_at.desc())
        
        # Apply pagination
        query = query.limit(limit).offset(offset)
        
        results = await database.fetch_all(query)
        return [dict(row) for row in results]
    
    async def list_entities_enhanced(
        self,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        order_desc: bool = True,
        limit: int = 50,
        offset: int = 0,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        List entities with enhanced created_by information
        """
        entities = await self.list_entities(
            filters=filters,
            order_by=order_by,
            order_desc=order_desc,
            limit=limit,
            offset=offset,
            include_deleted=include_deleted
        )
        
        # Enhance each entity
        enhanced_entities = []
        for entity in entities:
            enhanced_entity = await self.enhance_created_by_info(entity)
            enhanced_entities.append(enhanced_entity)
            
        return enhanced_entities
    
    async def count_entities(
        self,
        filters: Optional[Dict[str, Any]] = None,
        include_deleted: bool = False
    ) -> int:
        """
        Count entities with filters
        
        Args:
            filters: Dictionary of filter conditions
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            Total count
        """
        
        query = sqlalchemy.select(sqlalchemy.func.count(self.table.c.id))
        
        # Apply filters
        conditions = []
        
        # Exclude soft-deleted entities by default
        if not include_deleted and "deleted_at" in self.table.c:
            conditions.append(self.table.c.deleted_at.is_(None))
        
        if filters:
            for key, value in filters.items():
                if hasattr(self.table.c, key):
                    if isinstance(value, list):
                        conditions.append(getattr(self.table.c, key).in_(value))
                    else:
                        conditions.append(getattr(self.table.c, key) == value)
        
        if conditions:
            query = query.where(sqlalchemy.and_(*conditions))
        
        result = await database.fetch_val(query)
        return result or 0
    
    async def exists(self, entity_id: str, include_deleted: bool = False) -> bool:
        """
        Check if entity exists
        
        Args:
            entity_id: ID of the entity
            include_deleted: Whether to include soft-deleted entities
            
        Returns:
            True if entity exists
        """
        
        conditions = [self.table.c.id == entity_id]
        
        if not include_deleted and "deleted_at" in self.table.c:
            conditions.append(self.table.c.deleted_at.is_(None))
        
        query = sqlalchemy.select(
            sqlalchemy.func.count(self.table.c.id)
        ).where(sqlalchemy.and_(*conditions))
        
        count = await database.fetch_val(query)
        return count > 0
    
    async def validate_entity_access(
        self,
        entity_id: str,
        user_id: str,
        required_role_level: int = 1  # 1=Viewer, 2=Editor, 3=Owner
    ) -> Dict[str, Any]:
        """
        Validate user access to entity (to be overridden by subclasses)
        
        Args:
            entity_id: ID of the entity
            user_id: ID of the user
            required_role_level: Minimum role level required
            
        Returns:
            Entity data if access granted
        """
        
        # Default implementation - just check if entity exists
        entity = await self.get_by_id(entity_id)
        if not entity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{self.entity_type.value.title()} not found"
            )
        
        return entity
    
    def validate_required_fields(self, data: Dict[str, Any], required_fields: List[str]):
        """
        Validate that required fields are present
        
        Args:
            data: Data to validate
            required_fields: List of required field names
            
        Raises:
            HTTPException if required fields are missing
        """
        
        missing_fields = [field for field in required_fields if field not in data or data[field] is None]
        
        if missing_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Missing required fields: {', '.join(missing_fields)}"
            )
    
    def sanitize_data(self, data: Dict[str, Any], allowed_fields: List[str]) -> Dict[str, Any]:
        """
        Remove fields that are not allowed for update
        
        Args:
            data: Data to sanitize
            allowed_fields: List of allowed field names
            
        Returns:
            Sanitized data
        """
        
        return {key: value for key, value in data.items() if key in allowed_fields}


class ProjectContextService(BaseService):
    """Base service for entities that belong to a project"""
    
    async def validate_project_access(
        self,
        project_id: str,
        user_id: str,
        required_role_level: int = 1
    ) -> Dict[str, Any]:
        """
        Validate user access to project
        
        Args:
            project_id: ID of the project
            user_id: ID of the user
            required_role_level: Minimum role level required (1=Viewer, 2=Editor, 3=Owner)
            
        Returns:
            Project data if access granted
        """
        
        from app.utilities.permissions import check_project_access
        return await check_project_access(user_id, project_id, required_role_level)
    
    async def list_project_entities(
        self,
        project_id: str,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        List entities within a project context
        
        Args:
            project_id: ID of the project
            user_id: ID of the user
            filters: Additional filters
            **kwargs: Other arguments for list_entities
            
        Returns:
            List of entities within the project
        """
        
        # Validate project access
        await self.validate_project_access(project_id, user_id, required_role_level=1)
        
        # Add project_id to filters
        if filters is None:
            filters = {}
        filters["project_id"] = project_id
        
        return await self.list_entities(filters=filters, **kwargs)
    
    async def list_project_entities_enhanced(
        self,
        project_id: str,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        List entities within a project context with enhanced created_by information
        
        Args:
            project_id: ID of the project
            user_id: ID of the user
            filters: Additional filters
            **kwargs: Other arguments for list_entities_enhanced
            
        Returns:
            List of enhanced entities within the project
        """
        
        # Validate project access
        await self.validate_project_access(project_id, user_id, required_role_level=1)
        
        # Add project_id to filters
        if filters is None:
            filters = {}
        filters["project_id"] = project_id
        
        return await self.list_entities_enhanced(filters=filters, **kwargs)
