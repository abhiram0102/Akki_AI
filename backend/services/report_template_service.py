"""
ReportTemplate Service
<tool_call>
<function=Write>
<parameter=content>
"""
Report Template Service for managing custom report sections and configurations
"""
import json
from typing import List, Optional, Dict, Any
from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AsyncSessionLocal
from backend.models import ReportSectionTemplate, ReportConfiguration
from backend.services.ai_service import ai_service


class ReportTemplateService:
    """Service for managing report templates and configurations"""

    async def create_section_template(
        self,
        user_id: str,
        name: str,
        description: Optional[str] = None,
        section_type: str = None,
        content_template: str = None,
        is_public: bool = False
    ) -> ReportSectionTemplate:
        """Create a new report section template"""
        async with AsyncSessionLocal() as session:
            template = ReportSectionTemplate(
                id=str(__import__('uuid').uuid4()),
                user_id=user_id,
                name=name,
                description=description,
                section_type=section_type,
                content_template=content_template,
                is_public=is_public
            )
            session.add(template)
            await session.commit()
            await session.refresh(template)
            return template

    async def get_section_templates(
        self,
        user_id: str,
        include_public: bool = True,
        limit: int = 50
    ) -> List[ReportSectionTemplate]:
        """Get report section templates for a user"""
        async with AsyncSessionLocal() as session:
            query = select(ReportSectionTemplate).where(
                ReportSectionTemplate.user_id == user_id
            )
            if include_public:
                # Include user's own templates OR public templates
                from sqlalchemy import or_
                query = query.where(
                    or_(
                        ReportSectionTemplate.user_id == user_id,
                        ReportSectionTemplate.is_public == True
                    )
                )

            result = await session.execute(
                query.order_by(ReportSectionTemplate.created_at.desc()).limit(limit)
            )
            return result.scalars().all()

    async def get_section_template(
        self,
        template_id: str,
        user_id: str
    ) -> Optional[ReportSectionTemplate]:
        """Get a specific section template by ID"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ReportSectionTemplate)
                .where(
                    ReportSectionTemplate.id == template_id,
                    ReportSectionTemplate.user_id == user_id
                )
            )
            return result.scalar_one_or_none()

    async def update_section_template(
        self,
        template_id: str,
        user_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        section_type: Optional[str] = None,
        content_template: Optional[str] = None,
        is_public: Optional[bool] = None
    ) -> Optional[ReportSectionTemplate]:
        """Update a report section template"""
        async with AsyncSessionLocal() as session:
            template = await self.get_section_template(template_id, user_id)
            if not template:
                return None

            if name is not None:
                template.name = name
            if description is not None:
                template.description = description
            if section_type is not None:
                template.section_type = section_type
            if content_template is not None:
                template.content_template = content_template
            if is_public is not None:
                template.is_public = is_public

            await session.commit()
            await session.refresh(template)
            return template

    async def delete_section_template(
        self,
        template_id: str,
        user_id: str
    ) -> bool:
        """Delete a report section template"""
        async with AsyncSessionLocal() as session:
            template = await self.get_section_template(template_id, user_id)
            if not template:
                return False

            await session.delete(template)
            await session.commit()
            return True

    async def save_report_configuration(
        self,
        user_id: str,
        name: str,
        description: Optional[str] = None,
        sections: List[Dict[str, Any]] = None,
        is_default: bool = False
    ) -> ReportConfiguration:
        """Save a report configuration"""
        async with AsyncSessionLocal() as session:
            # If setting as default, unset other defaults for this user
            if is_default:
                await session.execute(
                    update(ReportConfiguration)
                    .where(
                        ReportConfiguration.user_id == user_id,
                        ReportConfiguration.is_default == True
                    )
                    .values(is_default=False)
                )

            config = ReportConfiguration(
                id=str(__import__('uuid').uuid4()),
                user_id=user_id,
                name=name,
                description=description,
                sections=sections or [],
                is_default=is_default
            )
            session.add(config)
            await session.commit()
            await session.refresh(config)
            return config

    async def get_report_configurations(
        self,
        user_id: str,
        limit: int = 50
    ) -> List[ReportConfiguration]:
        """Get report configurations for a user"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ReportConfiguration)
                .where(ReportConfiguration.user_id == user_id)
                .order_by(
                    desc(ReportConfiguration.is_default),
                    desc(ReportConfiguration.created_at)
                )
                .limit(limit)
            )
            return result.scalars().all()

    async def get_report_configuration(
        self,
        config_id: str,
        user_id: str
    ) -> Optional[ReportConfiguration]:
        """Get a specific report configuration by ID"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ReportConfiguration)
                .where(
                    ReportConfiguration.id == config_id,
                    ReportConfiguration.user_id == user_id
                )
            )
            return result.scalar_one_or_none()

    async def update_report_configuration(
        self,
        config_id: str,
        user_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        sections: Optional[List[Dict[str, Any]]] = None,
        is_default: Optional[bool] = None
    ) -> Optional[ReportConfiguration]:
        """Update a report configuration"""
        async with AsyncSessionLocal() as session:
            config = await self.get_report_configuration(config_id, user_id)
            if not config:
                return None

            if name is not None:
                config.name = name
            if description is not None:
                config.description = description
            if sections is not None:
                config.sections = sections
            if is_default is not None:
                # If setting as default, unset other defaults
                if is_default:
                    await session.execute(
                        update(ReportConfiguration)
                        .where(
                            ReportConfiguration.user_id == user_id,
                            ReportConfiguration.is_default == True,
                            ReportConfiguration.id != config_id
                        )
                        .values(is_default=False)
                    )
                config.is_default = is_default

            await session.commit()
            await session.refresh(config)
            return config

    async def delete_report_configuration(
        self,
        config_id: str,
        user_id: str
    ) -> bool:
        """Delete a report configuration"""
        async with AsyncSessionLocal() as session:
            config = await self.get_report_configuration(config_id, user_id)
            if not config:
                return False

            await session.delete(config)
            await session.commit()
            return True

    async def generate_custom_report(
        self,
        findings: List[dict],
        executive_summary: str = None,
        scope: str = None,
        sections: List[Dict[str, Any]] = None,
        title: str = "Security Assessment Report",
        report_type: str = "technical",
        user_id: str = None
    ) -> dict:
        """Generate a custom report using the AI service"""
        return await ai_service.generate_custom_report(
            findings=findings,
            executive_summary=executive_summary,
            scope=scope,
            sections=sections,
            title=title,
            report_type=report_type,
            user_id=user_id
        )


# Global instance
report_template_service = ReportTemplateService()