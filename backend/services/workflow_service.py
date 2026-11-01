"""
Workflow Service for managing multi-agent workflows
"""
import json
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import select, desc, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AsyncSessionLocal
from backend.models import Workflow, WorkflowStep
from backend.services.langgraph_agent_service import process_message
from backend.services.ai_service import ai_service


class WorkflowService:
    """Service for managing workflow definitions and execution"""

    async def create_workflow(
        self,
        user_id: str,
        name: str,
        description: Optional[str] = None,
        steps: Optional[List[Dict[str, Any]]] = None
    ) -> Workflow:
        """Create a new workflow with optional steps"""
        async with AsyncSessionLocal() as session:
            workflow = Workflow(
                id=str(__import__('uuid').uuid4()),
                user_id=user_id,
                name=name,
                description=description,
                is_active=True
            )
            session.add(workflow)
            await session.commit()
            await session.refresh(workflow)

            # Add steps if provided
            if steps:
                for i, step_data in enumerate(steps):
                    step = WorkflowStep(
                        id=str(__import__('uuid').uuid4()),
                        workflow_id=workflow.id,
                        step_order=i,
                        agent_type=step_data.get("agent_type", "planner"),
                        prompt_template=step_data.get("prompt_template", ""),
                        config=step_data.get("config", {})
                    )
                    session.add(step)
                await session.commit()

            return workflow

    async def get_workflow(self, workflow_id: str, user_id: str) -> Optional[Workflow]:
        """Get a workflow by ID for a specific user"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Workflow)
                .where(
                    Workflow.id == workflow_id,
                    Workflow.user_id == user_id
                )
            )
            return result.scalar_one_or_none()

    async def get_workflows(self, user_id: str, limit: int = 50) -> List[Workflow]:
        """Get all workflows for a user"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Workflow)
                .where(Workflow.user_id == user_id)
                .order_by(desc(Workflow.created_at))
                .limit(limit)
            )
            return result.scalars().all()

    async def update_workflow(
        self,
        workflow_id: str,
        user_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Optional[Workflow]:
        """Update a workflow's properties"""
        async with AsyncSessionLocal() as session:
            workflow = await self.get_workflow(workflow_id, user_id)
            if not workflow:
                return None

            if name is not None:
                workflow.name = name
            if description is not None:
                workflow.description = description
            if is_active is not None:
                workflow.is_active = is_active

            await session.commit()
            await session.refresh(workflow)
            return workflow

    async def delete_workflow(self, workflow_id: str, user_id: str) -> bool:
        """Delete a workflow and all its steps"""
        async with AsyncSessionLocal() as session:
            workflow = await self.get_workflow(workflow_id, user_id)
            if not workflow:
                return False

            await session.delete(workflow)
            await session.commit()
            return True

    async def add_step(
        self,
        workflow_id: str,
        user_id: str,
        agent_type: str,
        prompt_template: str,
        config: Optional[Dict[str, Any]] = None,
        step_order: Optional[int] = None
    ) -> Optional[WorkflowStep]:
        """Add a step to a workflow"""
        async with AsyncSessionLocal() as session:
            # Verify workflow ownership
            workflow_result = await session.execute(
                select(Workflow)
                .where(
                    Workflow.id == workflow_id,
                    Workflow.user_id == user_id
                )
            )
            workflow = workflow_result.scalar_one_or_none()
            if not workflow:
                return None

            # Determine step order
            if step_order is None:
                # Get the highest current order and add 1
                max_order_result = await session.execute(
                    select(WorkflowStep.step_order)
                    .where(WorkflowStep.workflow_id == workflow_id)
                    .order_by(desc(WorkflowStep.step_order))
                    .limit(1)
                )
                max_order = max_order_result.scalar_one_or_none()
                step_order = (max_order + 1) if max_order is not None else 0

            step = WorkflowStep(
                id=str(__import__('uuid').uuid4()),
                workflow_id=workflow_id,
                step_order=step_order,
                agent_type=agent_type,
                prompt_template=prompt_template,
                config=config or {}
            )
            session.add(step)
            await session.commit()
            await session.refresh(step)
            return step

    async def update_step(
        self,
        step_id: str,
        user_id: str,
        agent_type: Optional[str] = None,
        prompt_template: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        step_order: Optional[int] = None
    ) -> Optional[WorkflowStep]:
        """Update a workflow step"""
        async with AsyncSessionLocal() as session:
            # Get step with workflow ownership verification
            result = await session.execute(
                select(WorkflowStep)
                .join(Workflow, WorkflowStep.workflow_id == Workflow.id)
                .where(
                    WorkflowStep.id == step_id,
                    Workflow.user_id == user_id
                )
            )
            step = result.scalar_one_or_none()
            if not step:
                return None

            if agent_type is not None:
                step.agent_type = agent_type
            if prompt_template is not None:
                step.prompt_template = prompt_template
            if config is not None:
                step.config = config
            if step_order is not None:
                step.step_order = step_order

            await session.commit()
            await session.refresh(step)
            return step

    async def delete_step(self, step_id: str, user_id: str) -> bool:
        """Delete a workflow step"""
        async with AsyncSessionLocal() as session:
            # Get step with workflow ownership verification
            result = await session.execute(
                select(WorkflowStep)
                .join(Workflow, WorkflowStep.workflow_id == Workflow.id)
                .where(
                    WorkflowStep.id == step_id,
                    Workflow.user_id == user_id
                )
            )
            step = result.scalar_one_or_none()
            if not step:
                return False

            await session.delete(step)
            await session.commit()
            return True

    async def reorder_steps(
        self,
        workflow_id: str,
        user_id: str,
        step_orders: List[Dict[str, Any]]
    ) -> bool:
        """Reorder workflow steps"""
        async with AsyncSessionLocal() as session:
            # Verify workflow ownership
            workflow_result = await session.execute(
                select(Workflow)
                .where(
                    Workflow.id == workflow_id,
                    Workflow.user_id == user_id
                )
            )
            workflow = workflow_result.scalar_one_or_none()
            if not workflow:
                return False

            # Update step orders
            for item in step_orders:
                step_id = item.get("id")
                new_order = item.get("step_order")
                if step_id is not None and new_order is not None:
                    await session.execute(
                        update(WorkflowStep)
                        .where(
                            WorkflowStep.id == step_id,
                            WorkflowStep.workflow_id == workflow_id
                        )
                        .values(step_order=new_order)
                    )

            await session.commit()
            return True

    async def get_workflow_steps(self, workflow_id: str, user_id: str) -> List[WorkflowStep]:
        """Get all steps for a workflow in order"""
        async with AsyncSessionLocal() as session:
            # Verify workflow ownership and get steps
            result = await session.execute(
                select(WorkflowStep)
                .join(Workflow, WorkflowStep.workflow_id == Workflow.id)
                .where(
                    WorkflowStep.workflow_id == workflow_id,
                    Workflow.user_id == user_id
                )
                .order_by(WorkflowStep.step_order)
            )
            return result.scalars().all()

    async def execute_workflow(
        self,
        workflow_id: str,
        user_id: str,
        initial_input: str,
        session_id: str
    ) -> Dict[str, Any]:
        """Execute a workflow by running each step in sequence"""
        # Get workflow and steps
        workflow = await self.get_workflow(workflow_id, user_id)
        if not workflow:
            raise ValueError("Workflow not found or access denied")

        steps = await self.get_workflow_steps(workflow_id, user_id)
        if not steps:
            raise ValueError("Workflow has no steps")

        # Initialize execution context
        context = {
            "workflow_id": workflow_id,
            "workflow_name": workflow.name,
            "user_id": user_id,
            "session_id": session_id,
            "initial_input": initial_input,
            "previous_output": initial_input,
            "step_results": []
        }

        # Execute each step in order
        for step in steps:
            # Prepare prompt for this step
            prompt = step.prompt_template.replace("{input}", context["previous_output"])
            # Add any additional context variables from step config
            for key, value in step.config.items():
                if isinstance(value, str) and "{" in value and "}" in value:
                    # Simple template replacement
                    prompt = prompt.replace("{" + key + "}", str(context.get(key, "")))

            # Execute the agent
            try:
                agent_response = await process_message(
                    message=prompt,
                    session_id=session_id,
                    user_id=user_id,
                    context={
                        "workflow_step": True,
                        "step_id": step.id,
                        "agent_type": step.agent_type,
                        "workflow_context": context
                    }
                )

                step_result = {
                    "step_id": step.id,
                    "agent_type": step.agent_type,
                    "prompt": prompt,
                    "response": agent_response.get("content", ""),
                    "agent": agent_response.get("agent", "planner"),
                    "toolCalls": agent_response.get("toolCalls", []),
                    "ragUsed": agent_response.get("ragUsed", False),
                    "sources": agent_response.get("sources", []),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }

                context["step_results"].append(step_result)
                context["previous_output"] = agent_response.get("content", "")

            except Exception as e:
                # If a step fails, we still continue but record the error
                step_result = {
                    "step_id": step.id,
                    "agent_type": step.agent_type,
                    "prompt": prompt,
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                context["step_results"].append(step_result)
                # Continue with previous output or break based on configuration
                if not step.config.get("continue_on_error", False):
                    break

        return {
            "workflow_id": workflow_id,
            "workflow_name": workflow.name,
            "execution_complete": True,
            "steps_executed": len(context["step_results"]),
            "total_steps": len(steps),
            "results": context["step_results"],
            "final_output": context["previous_output"]
        }


# Global instance
workflow_service = WorkflowService()