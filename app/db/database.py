import databases
import sqlalchemy
from sqlalchemy.dialects import postgresql

from app.core.config import DATABASE_URL

# Database connection
database = databases.Database(DATABASE_URL)

# SQLAlchemy metadata
metadata = sqlalchemy.MetaData()

# Define tables
users_table = sqlalchemy.Table(
    "users",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.dialects.postgresql.UUID(as_uuid=True),
                      primary_key=True, server_default=sqlalchemy.text("gen_random_uuid()")),
    sqlalchemy.Column("name", sqlalchemy.String(100), nullable=False),
    sqlalchemy.Column("email", sqlalchemy.String(255), unique=True, nullable=False),
    sqlalchemy.Column("phone", sqlalchemy.String(20), unique=True, nullable=False),
    sqlalchemy.Column("password_hash", sqlalchemy.Text, nullable=False),
    sqlalchemy.Column("role", sqlalchemy.String(50), default="user"),
    sqlalchemy.Column("is_active", sqlalchemy.Boolean, default=True),
    sqlalchemy.Column("is_approved", sqlalchemy.Boolean, default=False),
    sqlalchemy.Column("approved_at", sqlalchemy.DateTime, nullable=True),
    sqlalchemy.Column("approved_by", sqlalchemy.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime, server_default=sqlalchemy.text("CURRENT_TIMESTAMP"))
)

temp_registrations_table = sqlalchemy.Table(
    "temp_registrations",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.dialects.postgresql.UUID(as_uuid=True),
                      primary_key=True, server_default=sqlalchemy.text("gen_random_uuid()")),
    sqlalchemy.Column("name", sqlalchemy.String(100), nullable=False),
    sqlalchemy.Column("email", sqlalchemy.String(255), nullable=False),
    sqlalchemy.Column("phone", sqlalchemy.String(20), nullable=False),
    sqlalchemy.Column("password_hash", sqlalchemy.Text, nullable=False),
    sqlalchemy.Column("otp_code", sqlalchemy.String(6), nullable=False),
    sqlalchemy.Column("otp_expires_at", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime, server_default=sqlalchemy.text("CURRENT_TIMESTAMP"))
)

temp_sessions_table = sqlalchemy.Table(
    "temp_sessions",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.dialects.postgresql.UUID(as_uuid=True),
                      primary_key=True, server_default=sqlalchemy.text("gen_random_uuid()")),
    sqlalchemy.Column("user_id", sqlalchemy.dialects.postgresql.UUID(as_uuid=True),
                      sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    sqlalchemy.Column("otp_code", sqlalchemy.String(6), nullable=False),
    sqlalchemy.Column("otp_expires_at", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime, server_default=sqlalchemy.text("CURRENT_TIMESTAMP"))
)

auth_sessions_table = sqlalchemy.Table(
    "auth_sessions",
    metadata,
    sqlalchemy.Column("id", sqlalchemy.dialects.postgresql.UUID(as_uuid=True),
                      primary_key=True, server_default=sqlalchemy.text("gen_random_uuid()")),
    sqlalchemy.Column("user_id", sqlalchemy.dialects.postgresql.UUID(as_uuid=True),
                      sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    sqlalchemy.Column("session_token", sqlalchemy.Text, unique=True, nullable=False),
    sqlalchemy.Column("expires_at", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime, server_default=sqlalchemy.text("CURRENT_TIMESTAMP"))
)


password_resets_table = sqlalchemy.Table(
    "password_resets",
    metadata,
    sqlalchemy.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sqlalchemy.text("gen_random_uuid()")
    ),
    sqlalchemy.Column(
        "user_id",
        postgresql.UUID(as_uuid=True),
        sqlalchemy.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True  # thêm index để join nhanh với bảng users
    ),
    sqlalchemy.Column("email", sqlalchemy.String(255), nullable=False, index=True),
    sqlalchemy.Column("otp_code", sqlalchemy.String(6), nullable=False),
    sqlalchemy.Column("otp_expires_at", sqlalchemy.DateTime, nullable=False),
    sqlalchemy.Column("is_verified", sqlalchemy.Boolean, server_default=sqlalchemy.text("FALSE")),
    sqlalchemy.Column("used", sqlalchemy.Boolean, server_default=sqlalchemy.text("FALSE")),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime, server_default=sqlalchemy.text("CURRENT_TIMESTAMP"))
)

# Create engine for table creation
engine = sqlalchemy.create_engine(DATABASE_URL)


async def connect_db():
    """Connect to database"""
    await database.connect()


async def disconnect_db():
    """Disconnect from database"""
    await database.disconnect()


# ==================================================================================
# PROJECT MANAGEMENT TABLES
# ==================================================================================

projects_table = sqlalchemy.Table(
    "projects",
    metadata,
    sqlalchemy.Column("id", postgresql.UUID(as_uuid=True),
                      primary_key=True, server_default=sqlalchemy.text("gen_random_uuid()")),
    sqlalchemy.Column("name", sqlalchemy.String(255), nullable=False),
    sqlalchemy.Column("description", sqlalchemy.Text, nullable=True),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime(timezone=True), server_default=sqlalchemy.text("CURRENT_TIMESTAMP")),
    sqlalchemy.Column("updated_at", sqlalchemy.DateTime(timezone=True), server_default=sqlalchemy.text("CURRENT_TIMESTAMP")),
    sqlalchemy.Column("created_by", postgresql.UUID(as_uuid=True),
                      sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

)

project_members_table = sqlalchemy.Table(
    "project_members",
    metadata,
    sqlalchemy.Column("project_id", postgresql.UUID(as_uuid=True),
                      sqlalchemy.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
    sqlalchemy.Column("user_id", postgresql.UUID(as_uuid=True),
                      sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    sqlalchemy.Column("role", sqlalchemy.String(20), nullable=False, server_default=sqlalchemy.text("'editor'"),
                      doc="Role: owner, editor, viewer"),
    sqlalchemy.Column("can_invite", sqlalchemy.Boolean, server_default=sqlalchemy.text("FALSE")),
    sqlalchemy.Column("joined_at", sqlalchemy.DateTime(timezone=True), server_default=sqlalchemy.text("CURRENT_TIMESTAMP")),
    sqlalchemy.PrimaryKeyConstraint("project_id", "user_id")
)

windfarms_table = sqlalchemy.Table(
    "windfarms",
    metadata,
    sqlalchemy.Column("id", postgresql.UUID(as_uuid=True),
                      primary_key=True, server_default=sqlalchemy.text("gen_random_uuid()")),
    sqlalchemy.Column("name", sqlalchemy.String(255), nullable=False),
    sqlalchemy.Column("description", sqlalchemy.Text, nullable=True),
    sqlalchemy.Column("own_company", sqlalchemy.String(255), nullable=True),
    sqlalchemy.Column("location", sqlalchemy.String(500), nullable=True),
    sqlalchemy.Column("project_id", postgresql.UUID(as_uuid=True),
                      sqlalchemy.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime(timezone=True), server_default=sqlalchemy.text("CURRENT_TIMESTAMP")),
    sqlalchemy.Column("updated_at", sqlalchemy.DateTime(timezone=True), server_default=sqlalchemy.text("CURRENT_TIMESTAMP")),
    sqlalchemy.Column("created_by", postgresql.UUID(as_uuid=True),
                      sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
)

turbines_table = sqlalchemy.Table(
    "turbines",
    metadata,
    sqlalchemy.Column("id", postgresql.UUID(as_uuid=True),
                      primary_key=True, server_default=sqlalchemy.text("gen_random_uuid()")),
    sqlalchemy.Column("name", sqlalchemy.String(255), nullable=False),
    sqlalchemy.Column("description", sqlalchemy.Text, nullable=True),
    sqlalchemy.Column("windfarm_id", postgresql.UUID(as_uuid=True),
                      sqlalchemy.ForeignKey("windfarms.id", ondelete="CASCADE"), nullable=False),
    sqlalchemy.Column("capacity_mw", sqlalchemy.DECIMAL(10, 3), nullable=True),
    sqlalchemy.Column("coordinates", sqlalchemy.String(50), nullable=True),  # Store as "lat,lng" format
    sqlalchemy.Column("serial_no", sqlalchemy.String(100), nullable=True),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime(timezone=True), server_default=sqlalchemy.text("CURRENT_TIMESTAMP")),
    sqlalchemy.Column("updated_at", sqlalchemy.DateTime(timezone=True), server_default=sqlalchemy.text("CURRENT_TIMESTAMP")),
    sqlalchemy.Column("created_by", postgresql.UUID(as_uuid=True),
                      sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
)

audit_logs_table = sqlalchemy.Table(
    "audit_logs",
    metadata,
    sqlalchemy.Column("id", postgresql.UUID(as_uuid=True),
                      primary_key=True, server_default=sqlalchemy.text("gen_random_uuid()")),
    sqlalchemy.Column("project_id", postgresql.UUID(as_uuid=True),
                      sqlalchemy.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
    sqlalchemy.Column("actor_id", postgresql.UUID(as_uuid=True),
                      sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    sqlalchemy.Column("action", sqlalchemy.String(50), nullable=False,
                      doc="Action: CREATE, UPDATE, DELETE, STATUS_CHANGE, MEMBER_ADDED, MEMBER_REMOVED"),
    sqlalchemy.Column("entity_type", sqlalchemy.String(30), nullable=False,
                      doc="Entity: PROJECT, WINDFARM, TURBINE, PROJECT_MEMBER"),
    sqlalchemy.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
    sqlalchemy.Column("entity_name", sqlalchemy.String(255), nullable=True),
    sqlalchemy.Column("description", sqlalchemy.Text, nullable=True),
    sqlalchemy.Column("before_data", postgresql.JSONB, nullable=True),
    sqlalchemy.Column("after_data", postgresql.JSONB, nullable=True),
    sqlalchemy.Column("changes", postgresql.JSONB, nullable=True),
    sqlalchemy.Column("metadata", postgresql.JSONB, nullable=True),
    sqlalchemy.Column("timestamp", sqlalchemy.DateTime(timezone=True), server_default=sqlalchemy.text("CURRENT_TIMESTAMP")),
    sqlalchemy.Column("expires_at", sqlalchemy.DateTime(timezone=True), server_default=sqlalchemy.text("CURRENT_TIMESTAMP + INTERVAL '30 days'")),
    sqlalchemy.Column("ip_address", postgresql.INET, nullable=True),
    sqlalchemy.Column("user_agent", sqlalchemy.Text, nullable=True)
)


# ==================================================================================
# BLADE INSPECTION TABLES
# ==================================================================================

inspections_table = sqlalchemy.Table(
    "inspections",
    metadata,
    sqlalchemy.Column("id", postgresql.UUID(as_uuid=True),
                      primary_key=True, server_default=sqlalchemy.text("gen_random_uuid()")),
    sqlalchemy.Column("turbine_id", postgresql.UUID(as_uuid=True),
                      sqlalchemy.ForeignKey("turbines.id", ondelete="CASCADE"), nullable=False),
    sqlalchemy.Column("inspection_code", sqlalchemy.String(100), unique=True, nullable=False),
    sqlalchemy.Column("status", sqlalchemy.String(50), server_default=sqlalchemy.text("'uploaded'")),
    sqlalchemy.Column("captured_at", sqlalchemy.DateTime(timezone=True), nullable=True),
    sqlalchemy.Column("operator", sqlalchemy.String(255), nullable=True),
    sqlalchemy.Column("equipment", sqlalchemy.String(255), nullable=True),
    sqlalchemy.Column("storage_path", sqlalchemy.Text, nullable=False),
    sqlalchemy.Column("total_images", sqlalchemy.Integer, server_default=sqlalchemy.text("0")),
    sqlalchemy.Column("processed_images", sqlalchemy.Integer, server_default=sqlalchemy.text("0")),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime(timezone=True), server_default=sqlalchemy.text("CURRENT_TIMESTAMP")),
    sqlalchemy.Column("updated_at", sqlalchemy.DateTime(timezone=True), server_default=sqlalchemy.text("CURRENT_TIMESTAMP")),
    sqlalchemy.Column("created_by", postgresql.UUID(as_uuid=True),
                      sqlalchemy.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    sqlalchemy.Column("metadata", postgresql.JSONB, nullable=True)
)

inspection_images_table = sqlalchemy.Table(
    "inspection_images",
    metadata,
    sqlalchemy.Column("id", postgresql.UUID(as_uuid=True),
                      primary_key=True, server_default=sqlalchemy.text("gen_random_uuid()")),
    sqlalchemy.Column("inspection_id", postgresql.UUID(as_uuid=True),
                      sqlalchemy.ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False),
    sqlalchemy.Column("blade", sqlalchemy.String(10), nullable=False),
    sqlalchemy.Column("surface", sqlalchemy.String(10), nullable=False),
    sqlalchemy.Column("position_pct", sqlalchemy.DECIMAL(5, 2), nullable=True),
    sqlalchemy.Column("position_meter", sqlalchemy.DECIMAL(10, 2), nullable=True),
    sqlalchemy.Column("file_name", sqlalchemy.String(255), nullable=False),
    sqlalchemy.Column("file_path", sqlalchemy.Text, nullable=False),
    sqlalchemy.Column("file_size", sqlalchemy.BigInteger, nullable=True),
    sqlalchemy.Column("captured_at", sqlalchemy.DateTime(timezone=True), nullable=True),
    sqlalchemy.Column("status", sqlalchemy.String(50), server_default=sqlalchemy.text("'uploaded'")),
    sqlalchemy.Column("checked_flag", sqlalchemy.String(20), server_default=sqlalchemy.text("'Unchecked'")),
    sqlalchemy.Column("metadata", postgresql.JSONB, nullable=True),
    sqlalchemy.Column("viewed_by", postgresql.UUID(as_uuid=True),
                      sqlalchemy.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    sqlalchemy.Column("viewed_at", sqlalchemy.DateTime(timezone=True), nullable=True),
    sqlalchemy.Column("created_at", sqlalchemy.DateTime(timezone=True), server_default=sqlalchemy.text("CURRENT_TIMESTAMP"))
)

damage_assessments_table = sqlalchemy.Table(
    "damage_assessments",
    metadata,
    sqlalchemy.Column("id", postgresql.UUID(as_uuid=True),
                      primary_key=True, server_default=sqlalchemy.text("gen_random_uuid()")),
    sqlalchemy.Column("inspection_image_id", postgresql.UUID(as_uuid=True),
                      sqlalchemy.ForeignKey("inspection_images.id", ondelete="CASCADE"), nullable=False),
    
    # ✅ AI Analysis (Pure Detection Results - bounding boxes contain all detection info)
    sqlalchemy.Column("ai_bounding_boxes", postgresql.JSONB, nullable=True),
    sqlalchemy.Column("ai_processed_at", sqlalchemy.DateTime(timezone=True), nullable=True),
    
    # ✅ User Notes (Optional manual input)
    sqlalchemy.Column("description", sqlalchemy.Text, nullable=True),
    
    # Audit
    sqlalchemy.Column("created_at", sqlalchemy.DateTime(timezone=True), server_default=sqlalchemy.text("CURRENT_TIMESTAMP")),
    sqlalchemy.Column("updated_at", sqlalchemy.DateTime(timezone=True), server_default=sqlalchemy.text("CURRENT_TIMESTAMP"))
)


def create_tables():
    """Create all tables"""
    metadata.create_all(engine)
