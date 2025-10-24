#!/usr/bin/env python3
"""
Script to update database schema to add approval columns
"""
import asyncio
import asyncpg
from app.core.config import DATABASE_URL


async def update_database_schema():
    """Update database schema to add approval functionality"""

    print("🔄 Updating database schema...")

    try:
        conn = await asyncpg.connect(DATABASE_URL)

        # Check if columns already exist
        existing_columns = await conn.fetch("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'users'
            AND column_name IN ('is_approved', 'approved_at', 'approved_by')
        """)

        existing_column_names = [col['column_name'] for col in existing_columns]

        if 'is_approved' not in existing_column_names:
            print("➕ Adding is_approved column...")
            await conn.execute("""
                ALTER TABLE users
                ADD COLUMN is_approved BOOLEAN DEFAULT FALSE
            """)
        else:
            print("✅ is_approved column already exists")

        if 'approved_at' not in existing_column_names:
            print("➕ Adding approved_at column...")
            await conn.execute("""
                ALTER TABLE users
                ADD COLUMN approved_at TIMESTAMP NULL
            """)
        else:
            print("✅ approved_at column already exists")

        if 'approved_by' not in existing_column_names:
            print("➕ Adding approved_by column...")
            await conn.execute("""
                ALTER TABLE users
                ADD COLUMN approved_by UUID NULL
            """)
        else:
            print("✅ approved_by column already exists")

        print("✅ Database schema updated successfully!")

        # Update existing users to be approved (for migration)
        update_choice = input("Bạn có muốn set tất cả user hiện tại thành 'approved'? (y/N): ")
        if update_choice.lower() == 'y':
            result = await conn.execute("""
                UPDATE users
                SET is_approved = TRUE, approved_at = CURRENT_TIMESTAMP
                WHERE is_approved IS FALSE OR is_approved IS NULL
            """)
            print(f"✅ Updated {result.split()[-1] if result else '0'} existing users to approved status")

        await conn.close()

    except Exception as e:
        print(f"❌ Error updating database schema: {e}")


async def check_schema():
    """Check current database schema"""
    try:
        conn = await asyncpg.connect(DATABASE_URL)

        print("\n📋 Current users table schema:")
        columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'users'
            ORDER BY ordinal_position
        """)

        for col in columns:
            nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
            default = f"DEFAULT {col['column_default']}" if col['column_default'] else ""
            print(f"  {col['column_name']}: {col['data_type']} {nullable} {default}")

        await conn.close()

    except Exception as e:
        print(f"❌ Error checking schema: {e}")


async def main():
    print("🔧 Database Schema Manager")
    print("1. Update schema (add approval columns)")
    print("2. Check current schema")

    choice = input("Chọn (1/2): ").strip()

    if choice == "1":
        await update_database_schema()
    elif choice == "2":
        await check_schema()
    else:
        print("Lựa chọn không hợp lệ!")

if __name__ == "__main__":
    asyncio.run(main())
