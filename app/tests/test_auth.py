"""
Test file for the authentication API
Run with: pytest test_auth.py
"""

import pytest
import sqlalchemy
from httpx import AsyncClient
from app.main import app

from app.db.database import (auth_sessions_table, database,
                             temp_registrations_table, temp_sessions_table,
                             users_table)


@pytest.fixture
async def client():
    """Create test client"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def setup_database():
    """Setup test database"""
    await database.connect()
    yield
    # Clean up test data
    await database.execute(sqlalchemy.delete(auth_sessions_table))
    await database.execute(sqlalchemy.delete(temp_sessions_table))
    await database.execute(sqlalchemy.delete(temp_registrations_table))
    await database.execute(sqlalchemy.delete(users_table))
    await database.disconnect()


class TestRegistration:

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient, setup_database):
        """Test successful registration"""
        response = await client.post("/auth/register", json={
            "name": "Test User",
            "email": "test@example.com",
            "phone": "0987654321",
            "password": "password123",
            "confirm_password": "password123"
        })

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "Loading"
        assert "temp_registration_id" in response.cookies

    @pytest.mark.asyncio
    async def test_register_password_mismatch(self, client: AsyncClient, setup_database):
        """Test registration with password mismatch"""
        response = await client.post("/auth/register", json={
            "name": "Test User",
            "email": "test@example.com",
            "phone": "0987654321",
            "password": "password123",
            "confirm_password": "different_password"
        })

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["status"] == "error"
        assert "không trùng khớp" in data["detail"]["message"]

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client: AsyncClient, setup_database):
        """Test registration with duplicate email"""
        # First registration
        await client.post("/auth/register", json={
            "name": "Test User 1",
            "email": "test@example.com",
            "phone": "0987654321",
            "password": "password123",
            "confirm_password": "password123"
        })

        # Try to register with same email
        response = await client.post("/auth/register", json={
            "name": "Test User 2",
            "email": "test@example.com",
            "phone": "0987654322",
            "password": "password123",
            "confirm_password": "password123"
        })

        assert response.status_code == 409
        data = response.json()
        assert data["detail"]["status"] == "error"


class TestLogin:

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, client: AsyncClient, setup_database):
        """Test login with invalid credentials"""
        response = await client.post("/auth/login", json={
            "identifier": "nonexistent@example.com",
            "password": "wrongpassword"
        })

        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["status"] == "error"


class TestHealthCheck:

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Test health check endpoint"""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_root_endpoint(self, client: AsyncClient):
        """Test root endpoint"""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "version" in data
