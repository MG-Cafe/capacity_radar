"""
GPU Radar - FastAPI Backend
Main application with REST endpoints and WebSocket for real-time updates.
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from gpu_data import get_all_machine_types_info, get_zones_for_machine_type, MACHINE_TYPES, get_chip_groups, TPU_TYPES
from advisory import get_calendar_advisory, get_spot_advisory
from hunter import (
    create_session, cancel_session, get_session,
    active_sessions, ConsumptionModel, ScanningStatus,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="GPU Radar",
    description="Priority-based GPU capacity hunting tool for Google Cloud",
    version="1.0.0",
)

# CORS for frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic Models ---

class CalendarAdvisoryRequest(BaseModel):
    project: str
    machineType: str
    vmCount: int = 1
    durationMinDays: int = 1
    durationMaxDays: int = 7
    startFrom: str = ""  # YYYY-MM-DD
    startTo: str = ""    # YYYY-MM-DD
    regions: list[str] = []
    zones: list[str] = []


class SpotAdvisoryRequest(BaseModel):
    project: str
    machineType: str
    regions: list[str] = []
    zones: list[str] = []


class PriorityConfig(BaseModel):
    method: str  # on_demand, dws_calendar, dws_flex, spot
    zones: list[str]
    max_retries: int = Field(default=5, ge=1, le=100)
    retry_interval: int = Field(default=60, ge=10, le=3600)
    name_prefix: str = Field(default="", max_length=50)
    flex_max_wait_hours: int = Field(default=168, ge=1, le=168)  # Max 7 days
    flex_usage_duration_hours: int = Field(default=24, ge=1, le=720)  # Max 30 days
    calendar_start_time: str = Field(default="")  # ISO datetime string
    calendar_end_time: str = Field(default="")    # ISO datetime string


class ScanRequest(BaseModel):
    project: str
    machineType: str
    vmCount: int = Field(default=1, ge=1)
    priorities: list[PriorityConfig]
    dwsCalendarDurationHours: int = Field(default=24, ge=1, le=2160)  # Max 90 days


# --- REST Endpoints ---

@app.post("/api/auth/check")
async def check_auth(body: dict = {}):
    """Check gcloud authentication and project access."""
    import httpx

    project = body.get("project", "")
    result = {
        "authenticated": False,
        "projectValid": False,
        "computeApiEnabled": False,
        "account": None,
        "errors": [],
        "instructions": [],
    }

    # Step 1: Check authentication using Application Default Credentials (ADC)
    try:
        import google.auth
        import google.auth.transport.requests

        creds, default_project = google.auth.default(
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        creds.refresh(google.auth.transport.requests.Request())
        token = creds.token
        result["authenticated"] = True

        # Get account info
        account = getattr(creds, 'service_account_email', None)
        if not account:
            # For user credentials, get account from gcloud
            proc = await asyncio.create_subprocess_exec(
                "gcloud", "config", "get-value", "account",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            account = stdout.decode().strip() if proc.returncode == 0 else "Unknown"
        result["account"] = account

    except Exception as e:
        error = str(e)
        result["errors"].append(f"Not authenticated: {error}")
        result["instructions"].append("Click 'Authenticate with Google' above, or run in terminal:")
        result["instructions"].append("gcloud auth application-default login")
        return result

    if not project:
        return result

    # Step 2: Check project access
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"https://compute.googleapis.com/compute/v1/projects/{project}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 200:
                result["projectValid"] = True
                result["computeApiEnabled"] = True
            elif resp.status_code == 403:
                data = resp.json()
                msg = data.get("error", {}).get("message", "")
                if "has not been used" in msg or "is disabled" in msg:
                    result["projectValid"] = True
                    result["computeApiEnabled"] = False
                    result["errors"].append("Compute Engine API is not enabled for this project.")
                    result["instructions"].append(f"Enable it: gcloud services enable compute.googleapis.com --project={project}")
                else:
                    result["errors"].append(f"Permission denied on project '{project}'.")
                    result["instructions"].append(f"Ensure your account has 'Compute Admin' or 'Editor' role on the project.")
                    result["instructions"].append(f"Check: gcloud projects get-iam-policy {project} --flatten='bindings[].members' --filter='bindings.members:YOUR_EMAIL'")
            elif resp.status_code == 404:
                result["errors"].append(f"Project '{project}' not found. Check the project ID.")
            else:
                data = resp.json()
                msg = data.get("error", {}).get("message", f"HTTP {resp.status_code}")
                result["errors"].append(f"Project check failed: {msg}")
    except Exception as e:
        result["errors"].append(f"Failed to verify project: {str(e)}")

    return result


@app.post("/api/auth/login")
async def trigger_login():
    """Trigger gcloud auth application-default login - opens browser for authentication."""
    try:
        # Use application-default login which sets up ADC with proper OAuth client
        proc = await asyncio.create_subprocess_exec(
            "gcloud", "auth", "application-default", "login", "--launch-browser",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            return {"success": True, "message": "Authentication successful! Click 'Connect' to verify."}
        else:
            error = stderr.decode().strip()
            return {"success": False, "message": f"Authentication process completed. Click 'Connect' to verify. ({error[:200]})"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/api/machine-types")
async def list_machine_types():
    """Get all available machine types with zone and consumption model info."""
    return {"machineTypes": get_all_machine_types_info()}


@app.get("/api/chip-groups")
async def list_chip_groups():
    """Get machine types grouped by chip for multi-step selection."""
    return get_chip_groups()


@app.get("/api/machine-types/{machine_type}/zones")
async def list_zones_for_machine_type(machine_type: str):
    """Get supported zones for a specific machine type."""
    zones = get_zones_for_machine_type(machine_type)
    if not zones:
        raise HTTPException(status_code=404, detail=f"Machine type '{machine_type}' not found")
    regions = sorted(set(z.rsplit("-", 1)[0] for z in zones))
    return {"machineType": machine_type, "zones": zones, "regions": regions}


@app.post("/api/advisory/calendar")
async def calendar_advisory(req: CalendarAdvisoryRequest):
    """Query DWS Calendar Mode Advisory API."""
    try:
        result = await get_calendar_advisory(
            project=req.project,
            machine_type=req.machineType,
            vm_count=req.vmCount,
            duration_min_days=req.durationMinDays,
            duration_max_days=req.durationMaxDays,
            start_from=req.startFrom,
            start_to=req.startTo,
            regions=req.regions if req.regions else None,
            zones=req.zones if req.zones else None,
        )
        return result
    except Exception as e:
        logger.error(f"Calendar advisory error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/advisory/spot")
async def spot_advisory(req: SpotAdvisoryRequest):
    """Query Spot VM Advisory API."""
    try:
        result = await get_spot_advisory(
            project=req.project,
            machine_type=req.machineType,
            regions=req.regions if req.regions else None,
            zones=req.zones if req.zones else None,
        )
        return result
    except Exception as e:
        logger.error(f"Spot advisory error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/scan/cancel/{session_id}")
async def cancel_scan(session_id: str):
    """Cancel an active scanning session."""
    if cancel_session(session_id):
        return {"status": "cancelled", "sessionId": session_id}
    raise HTTPException(status_code=404, detail="Session not found")


@app.get("/api/scan/sessions")
async def list_sessions():
    """List all scanning sessions."""
    sessions = []
    for sid, session in active_sessions.items():
        sessions.append({
            "sessionId": sid,
            "project": session.project,
            "machineType": session.machine_type,
            "vmCount": session.vm_count,
            "status": session.status.value,
        })
    return {"sessions": sessions}


# --- WebSocket for real-time hunting ---

@app.websocket("/ws/scan")
async def websocket_scan(websocket: WebSocket):
    """
    WebSocket endpoint for GPU scaning with real-time updates.

    Client sends a scan request, server streams progress updates.
    Client can send {"action": "cancel", "sessionId": "..."} to cancel.
    """
    await websocket.accept()
    logger.info("WebSocket client connected")

    session = None

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            action = message.get("action", "scan")

            if action == "cancel":
                session_id = message.get("sessionId")
                if session_id and cancel_session(session_id):
                    await websocket.send_json({
                        "type": "cancelled",
                        "message": "🛑 Scanning session cancelled.",
                        "sessionId": session_id,
                    })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Session not found.",
                    })

            elif action == "scan":
                # Validate request
                try:
                    scan_req = ScanRequest(**message.get("config", {}))
                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Invalid scan configuration: {str(e)}",
                    })
                    continue

                # Validate machine type (GPU or TPU)
                is_valid_tpu = any(scan_req.machineType in t.get("machine_types", {})
                                   for t in TPU_TYPES.values())
                if scan_req.machineType not in MACHINE_TYPES and not is_valid_tpu:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown machine type: {scan_req.machineType}",
                    })
                    continue

                # Build priorities list
                priorities = []
                for p in scan_req.priorities:
                    priorities.append({
                        "method": p.method,
                        "zones": p.zones,
                        "max_retries": p.max_retries,
                        "retry_interval": p.retry_interval,
                        "name_prefix": p.name_prefix,
                        "flex_max_wait_hours": p.flex_max_wait_hours,
                        "flex_usage_duration_hours": p.flex_usage_duration_hours,
                        "calendar_start_time": p.calendar_start_time,
                        "calendar_end_time": p.calendar_end_time,
                    })

                # Create send callback
                async def send_update(update):
                    try:
                        await websocket.send_json(update)
                    except Exception:
                        pass

                # Create and run session
                session = create_session(
                    project=scan_req.project,
                    machine_type=scan_req.machineType,
                    vm_count=scan_req.vmCount,
                    priorities=priorities,
                    send_update=send_update,
                    dws_calendar_duration_hours=scan_req.dwsCalendarDurationHours,
                )

                # Send session ID to client
                await websocket.send_json({
                    "type": "session_created",
                    "sessionId": session.session_id,
                    "message": f"Session created: {session.session_id}",
                })

                # Run hunting
                parallel = message.get("config", {}).get("parallel", False)
                await session.run(parallel=parallel)

            elif action == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
        if session:
            session.cancel()
    except json.JSONDecodeError:
        logger.error("Invalid JSON received")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"Server error: {str(e)}",
            })
        except Exception:
            pass


# --- Serve frontend ---
import os

frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve the React frontend for any non-API route."""
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
