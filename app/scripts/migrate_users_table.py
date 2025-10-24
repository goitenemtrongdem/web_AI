#!/usr/bin/env python3
"""
Non-interactive migration to ensure users table has expected columns for the app.
- Adds missing columns: name, phone, role, is_active, is_approved, approved_at, approved_by, created_at
- Adds UNIQUE constraint on email and phone if missing
- Prints resulting schema
"""
import asyncio
import asyncpg
from typing import Set
from app.core.config import DATABASE_URL

EXPECTED_COLUMNS = {
    # column_name: (definition SQL)
    "name": ("ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(100)"),
    "email": ("ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255)"),
    "phone": ("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20)"),
    "password_hash": ("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT"),
    "role": ("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'user'"),
    "is_active": ("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE"),
    "is_approved": ("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_approved BOOLEAN DEFAULT FALSE"),
    "approved_at": ("ALTER TABLE users ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP NULL"),
    "approved_by": ("ALTER TABLE users ADD COLUMN IF NOT EXISTS approved_by UUID NULL"),
    "created_at": ("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
}


async def get_existing_columns(conn: asyncpg.Connection) -> Set[str]:
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'users'
        """
    )
    return {r["column_name"] for r in rows}


async def migrate():
    print("Connecting to database...")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        existing = await get_existing_columns(conn)
        print(f"Existing columns: {sorted(existing)}")

        for col, ddl in EXPECTED_COLUMNS.items():
            if col not in existing:
                print(f"Adding missing column: {col}")
                await conn.execute(ddl)
            else:
                # ensure default for role/is_active/is_approved if column exists without default
                if col in ("role", "is_active", "is_approved"):
                    # Set defaults explicitly for existing rows where NULL
                    if col == "role":
                        await conn.execute("UPDATE users SET role='user' WHERE role IS NULL")
                    elif col == "is_active":
                        await conn.execute("UPDATE users SET is_active=TRUE WHERE is_active IS NULL")
                    elif col == "is_approved":
                        await conn.execute("UPDATE users SET is_approved=FALSE WHERE is_approved IS NULL")

        # Backfill 'name' from legacy 'full_name' if present
        try:
            await conn.execute("UPDATE users SET name = full_name WHERE name IS NULL AND full_name IS NOT NULL")
        except Exception:
            pass

        # Ensure unique indexes for email & phone (works across Postgres versions)
        unique_index_cmds = [
            "CREATE UNIQUE INDEX IF NOT EXISTS users_email_key ON users (email)",
            "CREATE UNIQUE INDEX IF NOT EXISTS users_phone_key ON users (phone)",
        ]
        for cmd in unique_index_cmds:
            try:
                await conn.execute(cmd)
            except Exception as e:
                print(f"Unique index ensure skipped: {e}")

        # Show final schema
        print("\nFinal users table schema:")
        rows = await conn.fetch(
            """
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'users'
            ORDER BY ordinal_position
            """
        )
        for r in rows:
            print(f" - {r['column_name']}: {r['data_type']} NULLABLE={r['is_nullable']} DEFAULT={r['column_default']}")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate())
