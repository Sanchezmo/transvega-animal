"""
Expense Category Service - Catálogo controlado de categorías de gasto.
Gestiona las categorías de gasto para clasificación de facturas de proveedor.
"""

from typing import Any

import structlog

from app.core.database import get_db_pool
from app.schemas import DEFAULT_EXPENSE_CATEGORIES, ExpenseCategoryCreate, ExpenseCategoryResponse

logger = structlog.get_logger()


class ExpenseCategoryService:
    """Servicio para gestionar el catálogo de categorías de gasto."""

    def __init__(self) -> None:
        self._pool = None
        self._initialized = False

    async def _get_pool(self):
        """Get or create database pool."""
        if self._pool is None:
            self._pool = await get_db_pool()
        return self._pool

    async def initialize(self) -> None:
        """Initialize the expense category table and seed default categories."""
        if self._initialized:
            return

        pool = await self._get_pool()

        # Create table if not exists
        async with pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS expense_categories (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(50) NOT NULL UNIQUE,
                    label VARCHAR(100) NOT NULL,
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    accounting_mapping VARCHAR(50),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            # Create index for active categories
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expense_categories_active
                ON expense_categories(active) WHERE active = TRUE
            """)

            # Seed default categories
            for cat in DEFAULT_EXPENSE_CATEGORIES:
                await conn.execute(
                    """
                    INSERT INTO expense_categories (code, label, active, accounting_mapping)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (code) DO UPDATE SET
                        label = EXCLUDED.label,
                        active = EXCLUDED.active,
                        accounting_mapping = EXCLUDED.accounting_mapping,
                        updated_at = NOW()
                """,
                    cat["code"],
                    cat["label"],
                    cat["active"],
                    cat.get("accounting_mapping"),
                )

        self._initialized = True
        logger.info("expense_category_service_initialized")

    async def list_categories(self, active_only: bool = True) -> list[ExpenseCategoryResponse]:
        """List all expense categories."""
        await self.initialize()
        pool = await self._get_pool()

        query = "SELECT * FROM expense_categories"
        if active_only:
            query += " WHERE active = TRUE"
        query += " ORDER BY code"

        async with pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [ExpenseCategoryResponse(**dict(row)) for row in rows]

    async def get_category(self, code: str) -> ExpenseCategoryResponse | None:
        """Get a category by code."""
        await self.initialize()
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM expense_categories WHERE code = $1", code)
            if row:
                return ExpenseCategoryResponse(**dict(row))
            return None

    async def validate_category(self, code: str) -> bool:
        """Validate that a category code exists and is active."""
        cat = await self.get_category(code)
        return cat is not None and cat.active

    async def create_category(self, data: ExpenseCategoryCreate) -> ExpenseCategoryResponse:
        """Create a new expense category."""
        await self.initialize()
        pool = await self._get_pool()

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO expense_categories (code, label, active, accounting_mapping)
                VALUES ($1, $2, $3, $4)
                RETURNING *
            """,
                data.code,
                data.label,
                data.active,
                data.accounting_mapping,
            )
            return ExpenseCategoryResponse(**dict(row))

    async def update_category(self, code: str, data: dict[str, Any]) -> ExpenseCategoryResponse | None:
        """Update an expense category."""
        await self.initialize()
        pool = await self._get_pool()

        # Build dynamic update query
        fields = []
        values = []
        param_num = 1

        for key, value in data.items():
            if key in ("label", "active", "accounting_mapping"):
                fields.append(f"{key} = ${param_num}")
                values.append(value)
                param_num += 1

        if not fields:
            return await self.get_category(code)

        fields.append("updated_at = NOW()")
        values.append(code)  # for WHERE clause

        query = f"""
            UPDATE expense_categories
            SET {", ".join(fields)}
            WHERE code = ${param_num}
            RETURNING *
        """

        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, *values)
            if row:
                return ExpenseCategoryResponse(**dict(row))
            return None

    async def get_accounting_mapping(self, code: str) -> str | None:
        """Get accounting mapping for a category (returns account code)."""
        cat = await self.get_category(code)
        if cat:
            return cat.accounting_mapping
        return None


# Global instance
expense_category_service = ExpenseCategoryService()


async def get_expense_category_service() -> ExpenseCategoryService:
    """Dependency injection for ExpenseCategoryService."""
    return expense_category_service
