#!/usr/bin/env python3
"""
Script to create the first admin user
"""
import asyncio
import asyncpg
import sys
import os
from getpass import getpass
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.utils import hash_password
from app.core.config import DATABASE_URL


async def create_admin_user():
    """Create admin user"""
    print("=== Tạo Admin User ===")

    name = input("Nhập tên admin: ")
    email = input("Nhập email admin: ")
    phone = input("Nhập số điện thoại admin: ")
    password = getpass("Nhập mật khẩu admin: ")
    confirm_password = getpass("Xác nhận mật khẩu: ")

    if password != confirm_password:
        print("❌ Mật khẩu không khớp!")
        return

    if len(password) < 6:
        print("❌ Mật khẩu phải có ít nhất 6 ký tự!")
        return

    # Hash password
    password_hash = hash_password(password)

    # Connect to database
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Check if admin already exists
        existing_admin = await conn.fetchval(
            "SELECT id FROM users WHERE role = 'admin' LIMIT 1"
        )

        if existing_admin:
            print("⚠️  Admin user đã tồn tại!")
            overwrite = input("Bạn có muốn tạo admin khác không? (y/N): ")
            if overwrite.lower() != 'y':
                await conn.close()
                return

        # Check if email or phone exists
        existing_user = await conn.fetchval(
            "SELECT id FROM users WHERE email = $1 OR phone = $2",
            email, phone
        )

        if existing_user:
            print("❌ Email hoặc số điện thoại đã được sử dụng!")
            await conn.close()
            return

        # Insert admin user
        await conn.execute("""
            INSERT INTO users (name, email, phone, password_hash, role, is_active, is_approved)
            VALUES ($1, $2, $3, $4, 'admin', TRUE, TRUE)
        """, name, email, phone, password_hash)

        print("✅ Tạo admin user thành công!")
        print(f"📧 Email: {email}")
        print(f"📱 Phone: {phone}")
        print(f"👤 Role: admin")

        await conn.close()

    except Exception as e:
        print(f"❌ Lỗi khi tạo admin user: {e}")


async def list_admins():
    """List all admin users"""
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        admins = await conn.fetch(
            "SELECT id, name, email, phone, created_at FROM users WHERE role = 'admin' ORDER BY created_at"
        )

        if not admins:
            print("Không có admin user nào.")
        else:
            print("\n=== Danh sách Admin Users ===")
            for admin in admins:
                print(f"ID: {admin['id']}")
                print(f"Name: {admin['name']}")
                print(f"Email: {admin['email']}")
                print(f"Phone: {admin['phone']}")
                print(f"Created: {admin['created_at']}")
                print("-" * 30)

        await conn.close()

    except Exception as e:
        print(f"❌ Lỗi khi lấy danh sách admin: {e}")


async def main():
    print("🔧 Admin User Management")
    print("1. Tạo admin user mới")
    print("2. Xem danh sách admin")

    choice = input("Chọn (1/2): ").strip()

    if choice == "1":
        await create_admin_user()
    elif choice == "2":
        await list_admins()
    else:
        print("Lựa chọn không hợp lệ!")

if __name__ == "__main__":
    asyncio.run(main())
