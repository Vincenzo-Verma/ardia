"""Formatter node: renders a ReportDraft to DOCX via Node.js and uploads to MinIO."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from typing import Any, Dict

from langchain_core.runnables import RunnableConfig

from agent.events import publish
from agent.state import AgentState
from storage import upload_docx

logger = logging.getLogger(__name__)

_GENERATE_JS = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "document-gen", "generate.js"
)


async def run_formatter(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Serialise the draft to DOCX via Node.js, upload to MinIO, return the signed URL."""
    job_id: str = config.get("configurable", {}).get("job_id", "")
    draft = state["draft"]

    await publish(job_id, {"type": "stage_start", "stage": "formatter",
                           "message": "Generating DOCX document..."})

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as jf:
        json_path = jf.name
        json.dump(draft.model_dump(), jf, default=str)

    docx_fd, docx_path = tempfile.mkstemp(suffix=".docx")
    os.close(docx_fd)

    try:
        result = subprocess.run(
            ["node", os.path.abspath(_GENERATE_JS), json_path, docx_path],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"generate.js exited with code {result.returncode}: {result.stderr}")

        with open(docx_path, "rb") as f:
            docx_bytes = f.read()

        filename = f"{draft.title[:80].replace(' ', '_')}.docx"
        presigned_url = await upload_docx(docx_bytes, filename)
        logger.info("Report uploaded: %s", presigned_url)

        await publish(job_id, {"type": "done", "output_url": presigned_url})
        return {"output_url": presigned_url}

    except Exception as exc:
        await publish(job_id, {"type": "error", "error": str(exc)})
        raise

    finally:
        if os.path.exists(json_path):
            os.unlink(json_path)
        if os.path.exists(docx_path):
            os.unlink(docx_path)
