"""realtime module — to be implemented in a later step.

The router is mounted so frontend developers can see the module exists
in the OpenAPI schema. Replace this stub with real endpoints when the
module is built.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/realtime", tags=["realtime"])


@router.get("/_ping", include_in_schema=False)
async def _ping() -> dict[str, str]:
    return {"module": "realtime", "status": "scaffolded"}
