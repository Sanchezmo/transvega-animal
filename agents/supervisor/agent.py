"""
Supervisor Agent - Orchestrates the complete multi-agent pipeline.
Integrates: Telegram → Dog Intake → Media Pipeline → Content Marketing → Publishing
"""
import asyncio
import httpx
import structlog
from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import uuid4
from enum import Enum

from app.agents.dog_intake.agent import DogIntakeAgent
from app.agents.media_pipeline.agent import create_media_pipeline_agent
from app.agents.content_marketing.agent import create_content_marketing_agent
from app.agents.publishing.agent import create_publishing_agent

logger = structlog.get_logger()


class WorkflowStep(str, Enum):
    """Pipeline workflow steps."""
    DOG_INTAKE = "dog_intake"
    MEDIA_INGEST = "media_ingest"
    MEDIA_ANALYZE = "media_analyze"
    MEDIA_SELECT = "media_select"
    CONTENT_GENERATE = "content_generate"
    CONTENT_APPROVE = "content_approve"
    PUBLISH_DRAFT = "publish_draft"
    PUBLISH_APPROVE = "publish_approve"
    PUBLISH_EXECUTE = "publish_execute"
    COMPLETE = "complete"


class SupervisorAgent:
    """
    Supervisor Agent - Central orchestrator for the multi-agent system.
    
    Pipeline: Telegram webhook → Dog Intake → Media Pipeline → Content → Publishing
    
    Responsibilities:
    - Route incoming Telegram messages to DogIntakeAgent
    - Coordinate media processing after dog creation
    - Trigger content generation for approved dogs
    - Manage publishing workflow with human approvals
    - Handle errors and retries
    - Audit logging
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.agent_id = "supervisor"
        self.agent_name = "Supervisor Agent"
        self.status = "idle"
        
        # Internal API client
        self.api_base = config.get("INTERNAL_API_URL", "http://localhost:8000")
        self.api_client = httpx.AsyncClient(base_url=self.api_base, timeout=60.0)
        self.api_key = config.get("AGENT_API_KEY_SUPERVISOR", "")
        
        # Sub-agents
        self.dog_intake_agent = DogIntakeAgent({"INTERNAL_API_URL": self.api_base})
        self.media_pipeline_agent = create_media_pipeline_agent(config)
        self.content_agent = create_content_marketing_agent(config)
        self.publishing_agent = create_publishing_agent(config)
        
        # Workflow state
        self.active_workflows: Dict[str, Dict] = {}
        self.pending_approvals: Dict[str, Dict] = {}
        
        self.capabilities = [
            "orchestrate_dog_intake",
            "orchestrate_media_pipeline",
            "orchestrate_content_generation",
            "orchestrate_publishing",
            "manage_approvals",
            "get_workflow_status",
            "retry_failed_step",
        ]
        self.restrictions = [
            "no_direct_db_access",
            "human_approval_required_for_publish",
            "human_approval_required_for_price_change",
        ]

    async def start(self):
        """Start the supervisor and sub-agents."""
        logger.info("starting_supervisor", agent_id=self.agent_id)
        self.status = "running"
        
        # Start sub-agents
        await self.dog_intake_agent.start()
        
        # Start background tasks
        asyncio.create_task(self._monitor_workflows())
        asyncio.create_task(self._cleanup_completed_workflows())
        
        logger.info("supervisor_started")

    async def stop(self):
        """Stop the supervisor and close connections."""
        logger.info("stopping_supervisor")
        self.status = "stopped"
        await self.api_client.aclose()
        await self.media_pipeline_agent.close()
        await self.content_agent.client.aclose()
        await self.publishing_agent.close()
        await self.dog_intake_agent.stop()

    # =========================================================================
    # WORKFLOW ENTRY POINTS
    # =========================================================================

    async def handle_telegram_message(self, message: Dict) -> Dict:
        """
        Entry point for Telegram webhook.
        Routes to DogIntakeAgent for multi-step dog creation.
        
        Expects a Telegram update object with message/edited_message containing:
        - chat.id, from.id, text, photo, etc.
        """
        # Extract message from update
        tg_message = message.get("message") or message.get("edited_message")
        if not tg_message:
            return {"success": False, "error": "No message in update"}
        
        chat_id = tg_message.get("chat", {}).get("id")
        user_id = tg_message.get("from", {}).get("id")
        text = tg_message.get("text", "")
        
        if chat_id is None or user_id is None:
            return {"success": False, "error": "Could not extract chat/user ID"}
        
        workflow_id = f"wf-{chat_id}-{user_id}"
        
        # Initialize or get existing workflow
        if workflow_id not in self.active_workflows:
            self.active_workflows[workflow_id] = {
                "workflow_id": workflow_id,
                "chat_id": chat_id,
                "user_id": user_id,
                "step": WorkflowStep.DOG_INTAKE,
                "status": "in_progress",
                "created_at": datetime.utcnow().isoformat(),
                "dog_id": None,
                "dog_internal_id": None,
                "media_items": [],
                "content": None,
                "publication_id": None,
            }
        
        workflow = self.active_workflows[workflow_id]
        
        # Delegate to DogIntakeAgent - pass the full message for it to handle
        result = await self.dog_intake_agent.process_message({
            "chat_id": chat_id,
            "user_id": user_id,
            "text": text,
            "message": tg_message,
        })
        
        if result.get("completed") and result.get("dog"):
            # Dog created successfully - advance workflow
            workflow["dog_id"] = result["dog"]["id"]
            workflow["dog_internal_id"] = result["dog"]["internal_id"]
            workflow["step"] = WorkflowStep.MEDIA_INGEST
            workflow["status"] = "awaiting_media"
            
            return {
                "success": True,
                "workflow_id": workflow_id,
                "step": workflow["step"],
                "message": f"Perro {result['dog']['internal_id']} creado. Ahora envía fotos/vídeos.",
                "dog": result["dog"],
            }
        
        return {
            "success": True,
            "workflow_id": workflow_id,
            "step": workflow["step"],
            "message": result.get("message", "Continúa con el ingreso..."),
            "awaiting_input": True,
        }

    async def handle_media_upload(self, workflow_id: str, file_content: bytes, 
                                   filename: str, purpose: str = "original") -> Dict:
        """
        Handle media upload for a dog.
        Part of Media Pipeline: INGEST → ANALYZE → SELECT
        """
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return {"success": False, "error": "Workflow not found"}
        
        dog_internal_id = workflow["dog_internal_id"]
        if not dog_internal_id:
            return {"success": False, "error": "No dog associated with workflow"}
        
        # Ingest media
        ingest_result = await self.media_pipeline_agent.ingest_media(
            file_content=file_content,
            filename=filename,
            dog_internal_id=dog_internal_id,
            purpose=purpose,
        )
        
        if not ingest_result["success"]:
            return ingest_result
        
        media_meta = ingest_result["media_metadata"]
        workflow["media_items"].append(media_meta)
        
        # Auto-analyze if photo
        if media_meta["media_type"] == "photo":
            analysis = await self.media_pipeline_agent.selection_agent.analyze_image(
                media_meta["file_path"]
            )
            media_meta["analysis"] = analysis
        
        return {
            "success": True,
            "workflow_id": workflow_id,
            "step": WorkflowStep.MEDIA_ANALYZE,
            "message": f"Media recibida ({len(workflow['media_items'])} total). Análisis completado.",
            "media": media_meta,
        }

    async def finalize_media_selection(self, workflow_id: str) -> Dict:
        """
        Finalize media selection after all uploads.
        Triggers: SELECT best → GENERATE variants → PREPARE for publishing
        """
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return {"success": False, "error": "Workflow not found"}
        
        if not workflow["media_items"]:
            return {"success": False, "error": "No media to select from"}
        
        # Select best media for publishing
        selection = await self.media_pipeline_agent.select_best_for_publishing(
            workflow["dog_internal_id"],
            workflow["media_items"]
        )
        
        # Generate social variants (optional, async)
        cover_path = None
        if selection.get("cover"):
            # Find cover file path
            for m in workflow["media_items"]:
                if m["file_hash"] in selection["cover"]:
                    cover_path = m["file_path"]
                    break
            
            if cover_path:
                # Get dog info for prompts
                dog_info = await self._get_dog_info(workflow["dog_id"])
                if dog_info:
                    await self.media_pipeline_agent.generate_social_variants(
                        dog_internal_id=workflow["dog_internal_id"],
                        cover_image_path=cover_path,
                        breed=dog_info.get("breed_name", ""),
                        dog_name=dog_info.get("name", ""),
                        privacy_scope="LOCAL_ONLY",
                    )
        
        workflow["step"] = WorkflowStep.CONTENT_GENERATE
        workflow["media_selection"] = selection
        
        return {
            "success": True,
            "workflow_id": workflow_id,
            "step": workflow["step"],
            "message": "Selección de media completada. Generando contenido...",
            "selection": selection,
        }

    async def generate_content(self, workflow_id: str) -> Dict:
        """
        Generate marketing content for the dog.
        Uses ContentMarketingAgent with dog data + selected media.
        """
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return {"success": False, "error": "Workflow not found"}
        
        dog_id = workflow["dog_id"]
        
        # Generate individual dog content
        content_result = await self.content_agent.generate_individual_content(dog_id)
        
        if not content_result["success"]:
            return content_result
        
        # Add selected media paths to content
        selection = workflow.get("media_selection", {})
        content_result["suggested_media"] = {
            "cover": selection.get("cover"),
            "listing": selection.get("listing", []),
            "social": selection.get("social", []),
        }
        
        workflow["content"] = content_result
        workflow["step"] = WorkflowStep.CONTENT_APPROVE
        workflow["status"] = "awaiting_content_approval"
        
        return {
            "success": True,
            "workflow_id": workflow_id,
            "step": workflow["step"],
            "message": "Contenido generado. Requiere aprobación antes de publicar.",
            "content": content_result,
            "requires_approval": True,
        }

    async def approve_content(self, workflow_id: str, approved: bool, 
                               feedback: str = "") -> Dict:
        """
        Human approval for generated content.
        """
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return {"success": False, "error": "Workflow not found"}
        
        if not approved:
            workflow["status"] = "content_rejected"
            workflow["rejection_feedback"] = feedback
            return {
                "success": True,
                "workflow_id": workflow_id,
                "message": "Contenido rechazado. Puedes regenerar o editar.",
            }
        
        # Approved - create publication draft
        workflow["step"] = WorkflowStep.PUBLISH_DRAFT
        return await self.create_publication_draft(workflow_id)

    async def create_publication_draft(self, workflow_id: str) -> Dict:
        """
        Create publication draft from approved content.
        """
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return {"success": False, "error": "Workflow not found"}
        
        content = workflow["content"]
        selection = workflow.get("media_selection", {})
        dog_info = await self._get_dog_info(workflow["dog_id"])
        
        # Create publication via API
        pub_data = {
            "expediente_id": dog_info.get("expediente_id", 1),
            "platform": "milanuncios",
            "title": content["title"],
            "description": content["copy"],
            "photos": selection.get("listing", [])[:10],  # Milanuncios max 20
            "price": dog_info.get("sale_price"),
        }
        
        response = await self._api_post("/publicaciones/", pub_data)
        if not response.get("success"):
            return {"success": False, "error": response.get("error")}
        
        publication = response["data"]
        workflow["publication_id"] = publication["id"]
        workflow["step"] = WorkflowStep.PUBLISH_APPROVE
        workflow["status"] = "awaiting_publish_approval"
        
        return {
            "success": True,
            "workflow_id": workflow_id,
            "step": workflow["step"],
            "message": "Borrador de publicación creado. Requiere aprobación para publicar.",
            "publication": publication,
            "requires_approval": True,
        }

    async def approve_publication(self, workflow_id: str, approved: bool,
                                   feedback: str = "") -> Dict:
        """
        Human approval to publish.
        """
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return {"success": False, "error": "Workflow not found"}
        
        if not approved:
            workflow["status"] = "publish_rejected"
            return {
                "success": True,
                "workflow_id": workflow_id,
                "message": "Publicación rechazada.",
            }
        
        # Approve via API
        pub_id = workflow["publication_id"]
        approve_resp = await self._api_post(f"/publicaciones/{pub_id}/approve")
        
        if not approve_resp.get("success"):
            return {"success": False, "error": approve_resp.get("error")}
        
        workflow["step"] = WorkflowStep.PUBLISH_EXECUTE
        return await self.execute_publication(workflow_id)

    async def execute_publication(self, workflow_id: str) -> Dict:
        """
        Execute actual publication on platform (Milanuncios via Playwright).
        """
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            return {"success": False, "error": "Workflow not found"}
        
        pub_id = workflow["publication_id"]
        
        # Prepare assets for publishing
        assets = await self.media_pipeline_agent.prepare_for_publishing(
            workflow["dog_internal_id"],
            platforms=["milanuncios"]
        )
        
        # Publish via API (triggers PublishingAgent)
        publish_resp = await self._api_post(f"/publicaciones/{pub_id}/publish")
        
        if not publish_resp.get("success"):
            return {"success": False, "error": publish_resp.get("error")}
        
        workflow["step"] = WorkflowStep.COMPLETE
        workflow["status"] = "completed"
        workflow["completed_at"] = datetime.utcnow().isoformat()
        
        return {
            "success": True,
            "workflow_id": workflow_id,
            "step": workflow["step"],
            "message": "¡Publicación completada! El anuncio está en vivo.",
            "publication": publish_resp.get("data"),
        }

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    async def _get_dog_info(self, dog_id: int) -> Optional[Dict]:
        """Fetch dog info from internal API."""
        try:
            resp = await self.api_client.get(
                f"/dogs/{dog_id}",
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.error("failed_to_get_dog", dog_id=dog_id, error=str(e))
        return None

    async def _api_post(self, path: str, data: Dict = None) -> Dict:
        """POST to internal API with auth."""
        try:
            resp = await self.api_client.post(
                path,
                json=data,
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            if resp.status_code in (200, 201, 202):
                return {"success": True, "data": resp.json()}
            return {"success": False, "error": resp.text}
        except Exception as e:
            logger.error("api_post_failed", path=path, error=str(e))
            return {"success": False, "error": str(e)}

    async def _monitor_workflows(self):
        """Monitor workflows for timeouts/stale states."""
        while self.status == "running":
            await asyncio.sleep(60)
            now = datetime.utcnow()
            
            for wf_id, workflow in list(self.active_workflows.items()):
                # Check for stale workflows (>1 hour in same step)
                created = datetime.fromisoformat(workflow["created_at"])
                if (now - created).total_seconds() > 3600:
                    if workflow["status"] in ["awaiting_media", "awaiting_content_approval", "awaiting_publish_approval"]:
                        logger.warning("workflow_stale", workflow_id=wf_id, step=workflow["step"])

    async def _cleanup_completed_workflows(self):
        """Clean up old completed workflows."""
        while self.status == "running":
            await asyncio.sleep(3600)  # Every hour
            
            now = datetime.utcnow()
            to_remove = []
            
            for wf_id, workflow in self.active_workflows.items():
                if workflow["status"] == "completed":
                    completed_at = datetime.fromisoformat(workflow.get("completed_at", workflow["created_at"]))
                    if (now - completed_at).total_seconds() > 86400:  # 24 hours
                        to_remove.append(wf_id)
            
            for wf_id in to_remove:
                del self.active_workflows[wf_id]
                logger.info("workflow_cleaned", workflow_id=wf_id)

    def get_workflow_status(self, workflow_id: str) -> Optional[Dict]:
        """Get current workflow status."""
        return self.active_workflows.get(workflow_id)

    def list_active_workflows(self) -> List[Dict]:
        """List all active workflows."""
        return list(self.active_workflows.values())


def create_supervisor_agent(config: Dict) -> SupervisorAgent:
    """Factory function."""
    return SupervisorAgent(config)