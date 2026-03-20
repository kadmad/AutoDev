from app.agents.base import BaseAgent, AgentResult
from app.services.zoho_service import update_task_status, PIPELINE_STAGE_TO_ZOHO_STATUS


class ZohoUpdaterAgent(BaseAgent):
    agent_type = "zoho_updater"

    async def run(
        self,
        pipeline_stage: str,
        zoho_task_id: str,
        zoho_config,
        db=None,
        comment: str = None,
        portal_name: str = None,
        project_id: str = None,
    ) -> AgentResult:
        zoho_status = PIPELINE_STAGE_TO_ZOHO_STATUS.get(pipeline_stage, "10")
        self.publish_log(f"[ZohoUpdater] Setting task {zoho_task_id} completion → {zoho_status}%")

        try:
            if pipeline_stage == "failed" and not comment:
                comment = "AutoDev pipeline failed. Please check the AutoDev dashboard."

            effective_portal = portal_name or zoho_config.portal_name
            effective_project = project_id or zoho_config.project_id
            self.publish_log(
                f"[ZohoUpdater] portal={effective_portal!r} "
                f"project={effective_project!r} "
                f"task={zoho_task_id!r} status={zoho_status!r}"
            )

            success = await update_task_status(
                config=zoho_config,
                task_id=zoho_task_id,
                status_name=zoho_status,
                comment=comment,
                db=db,
                portal_name=portal_name,
                project_id=project_id,
            )

            if success:
                confirmed = success if isinstance(success, str) else zoho_status
                self.publish_log(f"[ZohoUpdater] ✓ Zoho confirmed status: {confirmed!r}")
                return AgentResult(success=True, output=f"Updated to {confirmed}")
            else:
                self.publish_log(
                    "[ZohoUpdater] Skipped — Zoho token is expired. "
                    "Go to Settings → Integrations and reconnect Zoho OAuth."
                )
                return AgentResult(success=False, error="Zoho token expired")

        except Exception as e:
            error = str(e)
            self.publish_log(f"[ZohoUpdater] ERROR: {error}")
            return AgentResult(success=False, error=error)
