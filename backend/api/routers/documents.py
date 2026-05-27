"""Serve raw document files referenced by chat tool calls.

The chat agent's ``read_file`` tool surfaces a file pill in the UI; clicking
the pill hits this endpoint to fetch the underlying bytes. Auth-required.
Path traversal protection lives in ``LocalFileSystem``.
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import Response

from backend.api.auth import require_auth
from backend.api.dependencies import get_agent_deps
from backend.api.models.auth import AuthenticatedUser
from backend.core.agents.deps import AgentDeps

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/documents/{file_path:path}")
async def get_document(
    file_path: str,
    user: AuthenticatedUser = Depends(require_auth),  # noqa: ARG001
    deps: AgentDeps = Depends(get_agent_deps),
) -> Response:
    """Serve a file from the documents root.

    Path traversal, symlink, and extension whitelisting are enforced by
    ``LocalFileSystem.read_bytes``. Any signal of an invalid path becomes 404.
    """
    try:
        data = deps.fs.read_bytes(file_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="Not found") from e
    except ValueError as e:
        logger.info("documents: rejected path %r: %s", file_path, e)
        raise HTTPException(status_code=404, detail="Not found") from e
    except OSError as e:
        logger.warning("documents: read failed for %r: %s", file_path, e)
        raise HTTPException(status_code=500, detail="Could not read file") from e

    media_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    filename = PurePosixPath(file_path).name
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
