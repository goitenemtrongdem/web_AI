-- ============================================================================
-- MERGED SCHEMA: Authentication (base) + Project/Windfarm/Turbine management
-- Safe to run multiple times (uses IF NOT EXISTS where possible)
-- Requires: PostgreSQL 12+ and extension pgcrypto (for gen_random_uuid)
-- ============================================================================

-- Enable needed extension
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================================
-- AUTHENTICATION & ACCOUNT TABLES  (BASE - from old file)
-- ============================================================================

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    is_active BOOLEAN DEFAULT TRUE,
    is_approved BOOLEAN DEFAULT FALSE,
    approved_at TIMESTAMP NULL,
    approved_by UUID NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Temporary registrations table for OTP verification
CREATE TABLE IF NOT EXISTS temp_registrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    password_hash TEXT NOT NULL,
    otp_code VARCHAR(6) NOT NULL,
    otp_expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Temporary sessions table for login OTP verification
CREATE TABLE IF NOT EXISTS temp_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    otp_code VARCHAR(6) NOT NULL,
    otp_expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Authentication sessions table for logged in users
CREATE TABLE IF NOT EXISTS auth_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    session_token TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS password_resets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    email VARCHAR(255) NOT NULL,
    otp_code VARCHAR(6) NOT NULL,
    otp_expires_at TIMESTAMP NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE,
    used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for better performance
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_phone ON users(phone);
CREATE INDEX IF NOT EXISTS idx_temp_registrations_email ON temp_registrations(email);
CREATE INDEX IF NOT EXISTS idx_temp_registrations_phone ON temp_registrations(phone);
CREATE INDEX IF NOT EXISTS idx_temp_sessions_user_id ON temp_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_session_token ON auth_sessions(session_token);

CREATE INDEX IF NOT EXISTS idx_password_resets_email ON password_resets(email);
CREATE INDEX IF NOT EXISTS idx_password_resets_user_id ON password_resets(user_id);
CREATE INDEX IF NOT EXISTS idx_password_resets_expires_at ON password_resets(otp_expires_at);

-- ============================================================================
-- PROJECT / WINDFARM / TURBINE MANAGEMENT  (from new file)
-- ============================================================================

-- PROJECTS TABLE - Main project management
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
);

-- PROJECT MEMBERS - N-N relationship between users and projects
CREATE TABLE IF NOT EXISTS project_members (
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL DEFAULT 'editor' CHECK (role IN ('owner', 'editor', 'viewer')),
    can_invite BOOLEAN DEFAULT FALSE,
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, user_id)
);

-- Note: Invitations table removed - using simple member management instead

-- WINDFARMS TABLE - Wind farm management within projects
CREATE TABLE IF NOT EXISTS windfarms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    own_company VARCHAR(255),
    location VARCHAR(500),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
);

-- TURBINES TABLE - Individual turbine management within windfarms
CREATE TABLE IF NOT EXISTS turbines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    windfarm_id UUID NOT NULL REFERENCES windfarms(id) ON DELETE CASCADE,
    capacity_mw DECIMAL(10,3),
    coordinates VARCHAR(50), -- Store as "lat,lng" format
    serial_no VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE
);

-- AUDIT LOG TABLE - Track all user actions
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    actor_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL CHECK (action IN (
        'CREATE', 'UPDATE', 'DELETE', 
        'STATUS_CHANGE', 'MEMBER_ADDED', 'MEMBER_REMOVED',
        'BATCH_CREATE'
    )),
    entity_type VARCHAR(30) NOT NULL CHECK (entity_type IN (
        'PROJECT', 'WINDFARM', 'TURBINE', 'PROJECT_MEMBER', 'INSPECTION', 'INSPECTION_IMAGE'
    )),
    entity_id UUID NOT NULL,
    entity_name VARCHAR(255), -- Name/title of the entity for easy reference
    description TEXT, -- Human-readable description of what happened
    before_data JSONB,
    after_data JSONB,
    changes JSONB, -- Calculated diff between before and after data
    metadata JSONB, -- Additional context like batch_count, etc.
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP + INTERVAL '30 days'), -- Auto-expire after 30 days
    ip_address INET,
    user_agent TEXT -- Browser/client information
);

-- ============================================================================
-- BLADE INSPECTION TABLES - Quản lý kiểm tra cánh turbine với AI
-- ============================================================================

-- INSPECTIONS TABLE - Đợt kiểm tra chính
CREATE TABLE IF NOT EXISTS inspections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    turbine_id UUID NOT NULL REFERENCES turbines(id) ON DELETE CASCADE,
    inspection_code VARCHAR(100) UNIQUE NOT NULL,
    status VARCHAR(50) DEFAULT 'uploaded' CHECK (status IN ('uploaded', 'processing', 'completed', 'failed')),
    
    -- Thông tin kiểm tra
    captured_at TIMESTAMP WITH TIME ZONE,
    operator VARCHAR(255),
    equipment VARCHAR(255),
    
    -- Đường dẫn lưu trữ
    storage_path TEXT NOT NULL,
    
    -- Thống kê
    total_images INTEGER DEFAULT 0,
    processed_images INTEGER DEFAULT 0,
    
    -- Audit
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    
    -- Metadata
    metadata JSONB
);

-- INSPECTION IMAGES TABLE - Từng ảnh trong inspection
CREATE TABLE IF NOT EXISTS inspection_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inspection_id UUID NOT NULL REFERENCES inspections(id) ON DELETE CASCADE,
    
    -- Vị trí trên cánh
    blade VARCHAR(10) NOT NULL CHECK (blade IN ('BladeA', 'BladeB', 'BladeC')),
    surface VARCHAR(10) NOT NULL CHECK (surface IN ('PS', 'LE', 'TE', 'SS')),
    position_pct DECIMAL(5,2),
    position_meter DECIMAL(10,2), -- Position in meters from blade root
    
    -- File info
    file_name VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_size BIGINT,
    
    -- Timestamp
    captured_at TIMESTAMP WITH TIME ZONE,
    
    -- Status
    status VARCHAR(50) DEFAULT 'uploaded' CHECK (status IN ('uploaded', 'processing', 'analyzed', 'reviewed', 'failed')),
    
    -- Checked flag for selective AI workflow
    checked_flag VARCHAR(20) DEFAULT 'Unchecked' CHECK (checked_flag IN ('Unchecked', 'Checked', 'Processed')),
    
    -- User interaction
    viewed_by UUID REFERENCES users(id),
    viewed_at TIMESTAMP WITH TIME ZONE,
    
    -- Metadata
    metadata JSONB, -- Additional metadata: camera settings, GPS, weather, etc.
    
    -- Audit
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- ✅ DAMAGE ASSESSMENTS TABLE - ULTRA-SIMPLIFIED (Only Bounding Boxes + Description)
-- ============================================================================
-- Removed grading system, measurements, and AI summary fields
-- Only keeping bounding boxes array (contains all detection info) + user notes
CREATE TABLE IF NOT EXISTS damage_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inspection_image_id UUID NOT NULL REFERENCES inspection_images(id) ON DELETE CASCADE,
    
    -- ✅ AI Analysis (Bounding boxes contain all detection info: x, y, width, height, type, confidence)
    ai_bounding_boxes JSONB, -- [{x, y, width, height, type, confidence}] - Each box contains its own type & confidence
    ai_processed_at TIMESTAMP WITH TIME ZONE,
    
    -- ✅ User Notes (Optional manual input)
    description TEXT, -- User can add custom notes/description
    
    -- Audit
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE damage_assessments IS 'Ultra-simplified: only bounding boxes (with embedded type & confidence per box) + user description';
COMMENT ON COLUMN damage_assessments.description IS 'Optional user notes/description for the damage';
COMMENT ON COLUMN damage_assessments.ai_bounding_boxes IS 'YOLOv8 detection results: [{x, y, width, height, type, confidence}] - All detection data in one array';

-- ============================================================================
-- ❌ REMOVED: damage_grade_definitions table
-- Grading system (1-5 scale with labels/colors) has been removed for simplicity
-- Frontend can implement custom grading/categorization if needed
-- ============================================================================

-- INDEXES for performance optimization
CREATE INDEX IF NOT EXISTS idx_projects_created_by ON projects(created_by);

CREATE INDEX IF NOT EXISTS idx_project_members_project_id ON project_members(project_id);
CREATE INDEX IF NOT EXISTS idx_project_members_user_id ON project_members(user_id);

CREATE INDEX IF NOT EXISTS idx_windfarms_project_id ON windfarms(project_id);
CREATE INDEX IF NOT EXISTS idx_windfarms_created_by ON windfarms(created_by);

CREATE INDEX IF NOT EXISTS idx_turbines_windfarm_id ON turbines(windfarm_id);
CREATE INDEX IF NOT EXISTS idx_turbines_created_by ON turbines(created_by);

CREATE INDEX IF NOT EXISTS idx_audit_logs_project_id ON audit_logs(project_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_id ON audit_logs(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity_type ON audit_logs(entity_type);
CREATE INDEX IF NOT EXISTS idx_audit_logs_entity_id ON audit_logs(entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp);

CREATE INDEX IF NOT EXISTS idx_inspections_turbine_id ON inspections(turbine_id);
CREATE INDEX IF NOT EXISTS idx_inspections_status ON inspections(status);
CREATE INDEX IF NOT EXISTS idx_inspections_created_by ON inspections(created_by);

CREATE INDEX IF NOT EXISTS idx_inspection_images_inspection_id ON inspection_images(inspection_id);
CREATE INDEX IF NOT EXISTS idx_inspection_images_blade_surface ON inspection_images(blade, surface);
CREATE INDEX IF NOT EXISTS idx_inspection_images_status ON inspection_images(status);
CREATE INDEX IF NOT EXISTS idx_inspection_images_checked_flag ON inspection_images(checked_flag);
CREATE INDEX IF NOT EXISTS idx_inspection_images_position_meter ON inspection_images(position_meter);

CREATE INDEX IF NOT EXISTS idx_damage_assessments_image_id ON damage_assessments(inspection_image_id);
CREATE INDEX IF NOT EXISTS idx_damage_assessments_ai_processed_at ON damage_assessments(ai_processed_at);

-- ============================================================================
-- TRIGGERS for updated_at timestamps
-- ============================================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_projects_updated_at BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_windfarms_updated_at BEFORE UPDATE ON windfarms
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_turbines_updated_at BEFORE UPDATE ON turbines
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_inspections_updated_at BEFORE UPDATE ON inspections
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_damage_assessments_updated_at BEFORE UPDATE ON damage_assessments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Note: Invitation system removed - using simple member management instead
-- Members are added directly via email through API endpoints

-- ============================================================================
-- SAMPLE DATA (Optional - for testing)
-- ============================================================================
-- INSERT INTO projects (name, description, created_by) 
-- VALUES (
--     'Sample Wind Farm Project',
--     'A test project for wind turbine management',
--     (SELECT id FROM users WHERE role = 'admin' LIMIT 1)
-- );
