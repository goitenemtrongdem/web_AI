
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.users_admin.auth_routes import router as auth_router
from app.api.v1.projects.routes import router as projects_router
from app.api.v1.windfarms.routes import router as windfarms_router
from app.api.v1.turbines import router as turbines_router
from app.api.v1.audit import router as audit_router
from app.api.v1.members.routes import router as members_router
from app.api.v1.inspections.routes import router as inspections_router
from app.core.config import FRONTEND_ORIGINS, ensure_storage_directories
from app.db.database import connect_db, disconnect_db

# Create FastAPI app
app = FastAPI(
    title="Wind Turbine Management API",
    description="API for managing wind turbine projects, windfarms, turbines, and team collaboration",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,   # không dùng "*"
    allow_credentials=True,           # để gửi cookie
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1") 
app.include_router(windfarms_router, prefix="/api/v1")
app.include_router(turbines_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1")
app.include_router(members_router, prefix="/api/v1")
app.include_router(inspections_router, prefix="/api/v1")

# Startup and shutdown events


@app.on_event("startup")
async def startup():
    """Connect to database on startup"""
    await connect_db()
    # Create storage directories for inspections
    ensure_storage_directories()
    # Optionally create tables (better to use migrations in production)
    # create_tables()


@app.on_event("shutdown")
async def shutdown():
    """Disconnect from database on shutdown"""
    await disconnect_db()

# Health check endpoint


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "message": "API is running"}

# Root endpoint


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Authentication API",
        "version": "1.0.0",
        "docs": "/docs"
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
