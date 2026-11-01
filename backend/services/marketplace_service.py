"""
Marketplace Service for managing integration marketplace items
"""
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select, desc, func, update, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AsyncSessionLocal
from backend.models import MarketplaceItem, UserMarketplaceItem, User


class MarketplaceService:
    """Service for managing marketplace items"""

    async def create_marketplace_item(
        self,
        name: str,
        description: Optional[str] = None,
        category: str = "tool",
        subcategory: Optional[str] = None,
        version: str = "1.0.0",
        author: Optional[str] = None,
        repository_url: Optional[str] = None,
        documentation_url: Optional[str] = None,
        install_command: Optional[str] = None,
        config_schema: Optional[Dict[str, Any]] = None,
        is_public: bool = False,
        is_verified: bool = False,
        user_id: Optional[str] = None
    ) -> MarketplaceItem:
        """Create a new marketplace item"""
        async with AsyncSessionLocal() as session:
            marketplace_item = MarketplaceItem(
                id=str(__import__('uuid').uuid4()),
                name=name,
                description=description,
                category=category,
                subcategory=subcategory,
                version=version,
                author=author,
                repository_url=repository_url,
                documentation_url=documentation_url,
                install_command=install_command,
                config_schema=config_schema or {},
                is_public=is_public,
                is_verified=is_verified,
                user_id=user_id
            )
            session.add(marketplace_item)
            await session.commit()
            await session.refresh(marketplace_item)
            return marketplace_item

    async def get_marketplace_item(self, item_id: str, user_id: Optional[str] = None) -> Optional[MarketplaceItem]:
        """Get a marketplace item by ID"""
        async with AsyncSessionLocal() as session:
            query = select(MarketplaceItem).where(MarketplaceItem.id == item_id)

            # If user_id is provided, check if user has access (their own items or public items)
            if user_id is not None:
                query = query.where(
                    or_(
                        MarketplaceItem.user_id == user_id,
                        MarketplaceItem.is_public == True
                    )
                )

            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_marketplace_items(
        self,
        user_id: Optional[str] = None,
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
        is_public: Optional[bool] = None,
        is_verified: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[MarketplaceItem]:
        """Get marketplace items with optional filtering"""
        async with AsyncSessionLocal() as session:
            query = select(MarketplaceItem)

            # If user_id is provided, show user's own items plus public items
            # If no user_id, show only public items
            if user_id is not None:
                query = query.where(
                    or_(
                        MarketplaceItem.user_id == user_id,
                        MarketplaceItem.is_public == True
                    )
                )
            else:
                query = query.where(MarketplaceItem.is_public == True)

            if category:
                query = query.where(MarketplaceItem.category == category)
            if subcategory:
                query = query.where(MarketplaceItem.subcategory == subcategory)
            if is_public is not None:
                query = query.where(MarketplaceItem.is_public == is_public)
            if is_verified is not None:
                query = query.where(MarketplaceItem.is_verified == is_verified)

            query = query.order_by(desc(MarketplaceItem.created_at)).limit(limit).offset(offset)

            result = await session.execute(query)
            return result.scalars().all()

    async def search_marketplace_items(
        self,
        query: str,
        user_id: Optional[str] = None,
        limit: int = 50
    ) -> List[MarketplaceItem]:
        """Search marketplace items by name or description"""
        async with AsyncSessionLocal() as session:
            search_query = select(MarketplaceItem).where(
                or_(
                    MarketplaceItem.name.ilike(f"%{query}%"),
                    MarketplaceItem.description.ilike(f"%{query}%")
                )
            )

            # Apply user visibility rules
            if user_id is not None:
                search_query = search_query.where(
                    or_(
                        MarketplaceItem.user_id == user_id,
                        MarketplaceItem.is_public == True
                    )
                )
            else:
                search_query = search_query.where(MarketplaceItem.is_public == True)

            search_query = search_query.order_by(desc(MarketplaceItem.created_at)).limit(limit)

            result = await session.execute(search_query)
            return result.scalars().all()

    async def install_marketplace_item(
        self,
        user_id: str,
        marketplace_item_id: str,
        config: Optional[Dict[str, Any]] = None
    ) -> UserMarketplaceItem:
        """Install a marketplace item for a user"""
        async with AsyncSessionLocal() as session:
            # Verify the marketplace item exists and is accessible
            marketplace_item_result = await session.execute(
                select(MarketplaceItem).where(
                    MarketplaceItem.id == marketplace_item_id,
                    or_(
                        MarketplaceItem.user_id == user_id,
                        MarketplaceItem.is_public == True
                    )
                )
            )
            marketplace_item = marketplace_item_result.scalar_one_or_none()
            if not marketplace_item:
                raise ValueError("Marketplace item not found or access denied")

            # Check if already installed
            existing_result = await session.execute(
                select(UserMarketplaceItem).where(
                    UserMarketplaceItem.user_id == user_id,
                    UserMarketplaceItem.marketplace_item_id == marketplace_item_id
                )
            )
            existing = existing_result.scalar_one_or_none()
            if existing:
                # Update existing installation
                if config is not None:
                    existing.config = config
                existing.is_enabled = True
                await session.commit()
                await session.refresh(existing)
                return existing

            # Create new installation
            user_marketplace_item = UserMarketplaceItem(
                id=str(__import__('uuid').uuid4()),
                user_id=user_id,
                marketplace_item_id=marketplace_item_id,
                config=config or {},
                is_enabled=True
            )
            session.add(user_marketplace_item)

            # Increment download count
            marketplace_item.download_count += 1

            await session.commit()
            await session.refresh(user_marketplace_item)
            return user_marketplace_item

    async def uninstall_marketplace_item(
        self,
        user_id: str,
        marketplace_item_id: str
    ) -> bool:
        """Uninstall a marketplace item for a user"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                delete(UserMarketplaceItem).where(
                    UserMarketplaceItem.user_id == user_id,
                    UserMarketplaceItem.marketplace_item_id == marketplace_item_id
                )
            )
            await session.commit()
            return result.rowcount > 0

    async def get_user_installed_items(
        self,
        user_id: str,
        enabled_only: bool = False
    ) -> List[UserMarketplaceItem]:
        """Get marketplace items installed by a user"""
        async with AsyncSessionLocal() as session:
            query = select(UserMarketplaceItem).where(
                UserMarketplaceItem.user_id == user_id
            )

            if enabled_only:
                query = query.where(UserMarketplaceItem.is_enabled == True)

            query = query.order_by(desc(UserMarketplaceItem.installed_at))

            result = await session.execute(query)
            return result.scalars().all()

    async def update_marketplace_item_config(
        self,
        user_id: str,
        marketplace_item_id: str,
        config: Dict[str, Any]
    ) -> Optional[UserMarketplaceItem]:
        """Update configuration for an installed marketplace item"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserMarketplaceItem).where(
                    UserMarketplaceItem.user_id == user_id,
                    UserMarketplaceItem.marketplace_item_id == marketplace_item_id
                )
            )
            user_item = result.scalar_one_or_none()
            if not user_item:
                return None

            user_item.config = config
            await session.commit()
            await session.refresh(user_item)
            return user_item

    async def toggle_marketplace_item_enabled(
        self,
        user_id: str,
        marketplace_item_id: str,
        is_enabled: bool
    ) -> Optional[UserMarketplaceItem]:
        """Enable or disable an installed marketplace item"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(UserMarketplaceItem).where(
                    UserMarketplaceItem.user_id == user_id,
                    UserMarketplaceItem.marketplace_item_id == marketplace_item_id
                )
            )
            user_item = result.scalar_one_or_none()
            if not user_item:
                return None

            user_item.is_enabled = is_enabled
            await session.commit()
            await session.refresh(user_item)
            return user_item

    async def rate_marketplace_item(
        self,
        item_id: str,
        rating: float,
        user_id: str
    ) -> Optional[MarketplaceItem]:
        """Rate a marketplace item (simplified - in reality would need a separate ratings table)"""
        async with AsyncSessionLocal() as session:
            # Get the item
            result = await session.execute(
                select(MarketplaceItem).where(MarketplaceItem.id == item_id)
            )
            marketplace_item = result.scalar_one_or_none()
            if not marketplace_item:
                return None

            # Update rating (simplified average - real implementation would be more complex)
            # For now, we'll just store the latest rating
            # A proper implementation would have a separate ratings table
            marketplace_item.rating = rating

            await session.commit()
            await session.refresh(marketplace_item)
            return marketplace_item


    async def update_marketplace_item(
        self,
        item_id: str,
        updates: dict,
        user_id: str,
    ) -> Optional[MarketplaceItem]:
        """Update a marketplace item. Only the item creator can update."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(MarketplaceItem).where(MarketplaceItem.id == item_id)
            )
            item = result.scalar_one_or_none()
            if not item:
                return None
            # Only creator can update (system items have user_id=None)
            if item.user_id and item.user_id != user_id:
                return None
            for field, value in updates.items():
                if hasattr(item, field) and value is not None:
                    setattr(item, field, value)
            await session.commit()
            await session.refresh(item)
            return item

    async def delete_marketplace_item(
        self,
        item_id: str,
        user_id: str,
    ) -> bool:
        """Delete a marketplace item. Only the item creator can delete."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(MarketplaceItem).where(MarketplaceItem.id == item_id)
            )
            item = result.scalar_one_or_none()
            if not item:
                return False
            if item.user_id and item.user_id != user_id:
                return False
            # Remove all user installs first
            await session.execute(
                delete(UserMarketplaceItem).where(UserMarketplaceItem.marketplace_item_id == item_id)
            )
            await session.delete(item)
            await session.commit()
            return True

# Global instance
marketplace_service = MarketplaceService()