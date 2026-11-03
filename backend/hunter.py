"""
GPU Radar - Priority-based GPU/TPU capacity scanning engine.
Supports: On-Demand Reservation, DWS Calendar Reservation, DWS Flex Start, Spot VMs.
Sends real-time progress updates via WebSocket callback.
Uses REST APIs directly. Polls GCP operations to verify actual deployment.
"""

import asyncio
import json
import uuid
import logging
import httpx
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from enum import Enum

from gpu_data import (
    MACHINE_TYPES,
    TPU_TYPES,
    get_zones_for_machine_type,
    get_calendar_zones_for_machine_type,
    get_calendar_config_for_machine_type,
    get_tpu_spec,
    is_consumption_supported,
    FAMILY_TO_GPU_ZONE_KEY,
    MACHINE_TO_FAMILY,
    GPU_ZONES,
)

logger = logging.getLogger(__name__)


class ScanningStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConsumptionModel(str, Enum):
    ON_DEMAND = "on_demand"
    DWS_CALENDAR = "dws_calendar"
    DWS_FLEX = "dws_flex"
    SPOT = "spot"


CONSUMPTION_LABELS = {
    ConsumptionModel.ON_DEMAND: "On-Demand Reservation",
    ConsumptionModel.DWS_CALENDAR: "DWS Calendar Mode",
    ConsumptionModel.DWS_FLEX: "DWS Flex Start",
    ConsumptionModel.SPOT: "Spot VMs",
}


def _get_adc_token() -> str:
    import os
    if os.environ.get("AUTH_MODE", "local").lower() == "user":
        raise RuntimeError(
            "This server runs in bring-your-own-credentials mode and never uses "
            "server-side credentials. Provide your own access token "
            "(gcloud auth print-access-token) in the Authentication panel."
        )
    import google.auth
    import google.auth.transport.requests
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


async def get_access_token() -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_adc_token)


def _normalize_datetime(dt_str: str) -> str:
    """Normalize a datetime string to ISO 8601 with seconds and Z suffix."""
    dt_str = dt_str.strip()
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(dt_str, fmt)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return dt_str if dt_str.endswith("Z") else dt_str + "Z"


class ScanningSession:
    """Manages a GPU/TPU scanning session with priority-based strategy."""

    def __init__(
        self,
        session_id: str,
        project: str,
        machine_type: str,
        vm_count: int,
        priorities: list[dict],
        send_update: Callable,
        dws_calendar_duration_hours: int = 24,
        user_token: Optional[str] = None,
        network: Optional[str] = None,
        subnetwork: Optional[str] = None,
        min_vm_count: Optional[int] = None,
        max_vm_count: Optional[int] = None,
        total_hunting_hours: float = 1.0,
    ):
        self.session_id = session_id
        self.project = project
        self.machine_type = machine_type
        self.vm_count = vm_count
        self.min_vm_count = max(1, min_vm_count if min_vm_count is not None else vm_count)
        self.max_vm_count = max(self.min_vm_count, max_vm_count if max_vm_count is not None else vm_count)
        self.total_hunting_hours = max(0.05, float(total_hunting_hours or 1.0))
        self.priorities = priorities
        self.send_update = send_update
        self.dws_calendar_duration_hours = dws_calendar_duration_hours
        self.status = ScanningStatus.PENDING
        self.cancelled = False
        self.result = None
        self._token = None
        self._token_time = None
        self._user_token = user_token
        self.network = network or ""
        self.subnetwork = subnetwork or ""
        self._deploy_start_time = datetime.now(timezone.utc)

    def _is_hunting_expired(self) -> bool:
        """Check whether the total hunting time window has elapsed."""
        elapsed = (datetime.now(timezone.utc) - self._deploy_start_time).total_seconds()
        return elapsed >= self.total_hunting_hours * 3600

    def _get_vm_count_candidates(self) -> list[int]:
        """Return descending VM counts from max_vm_count down to min_vm_count."""
        if self.min_vm_count >= self.max_vm_count:
            return [self.vm_count]
        span = self.max_vm_count - self.min_vm_count
        if span <= 4:
            return list(range(self.max_vm_count, self.min_vm_count - 1, -1))
        # Up to 4 descending steps between max_vm_count and min_vm_count
        candidates = []
        for frac in (1.0, 0.75, 0.5, 0.25, 0.0):
            val = max(self.min_vm_count, round(self.min_vm_count + span * frac))
            if val not in candidates:
                candidates.append(val)
        return candidates

    def _tracking_labels(self, method: str) -> dict:
        """Generate GCP resource labels for tracking deployments created by Capacity Radar."""
        return {
            "created-by": "capacity-radar",
            "capacity-radar-session": self.session_id[:8],
            "capacity-radar-method": method.replace("_", "-"),
            "capacity-radar-machine": self.machine_type[:63].replace(".", "-"),
            "capacity-radar-count": str(self.vm_count),
            "capacity-radar-project": self.project[:63].replace(".", "-"),
        }

    def _log_deployment_event(
        self,
        method: str,
        zone: str,
        resource_name: str,
        success: bool,
        resource_type: str = "reservation",
        extra: dict = None,
    ):
        """Log deployment event to a JSON-lines file for tracking and analytics."""
        import os
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "project": self.project,
            "machine_type": self.machine_type,
            "vm_count": self.vm_count,
            "method": method,
            "zone": zone,
            "region": zone.rsplit("-", 1)[0] if zone else "",
            "resource_name": resource_name,
            "resource_type": resource_type,
            "success": success,
            "duration_seconds": (datetime.now(timezone.utc) - self._deploy_start_time).total_seconds(),
        }
        if extra:
            event.update(extra)

        logger.info(f"DEPLOYMENT_EVENT: {json.dumps(event)}")

        log_dir = os.path.join(os.path.dirname(__file__), "deployment_logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "deployments.jsonl")
        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write deployment log: {e}")

    async def _get_token(self) -> str:
        if self._user_token:
            return self._user_token
        now = datetime.now(timezone.utc)
        if not self._token or not self._token_time or (now - self._token_time).total_seconds() > 3000:
            self._token = await get_access_token()
            self._token_time = now
        return self._token

    async def _refresh_token(self):
        if self._user_token:
            return
        self._token = await get_access_token()
        self._token_time = datetime.now(timezone.utc)

    async def emit(self, msg_type: str, message: str, data: dict = None):
        update = {
            "sessionId": self.session_id,
            "type": msg_type,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": self.status.value,
        }
        if data:
            update["data"] = data
        await self.send_update(update)

    # ── Operation polling ──────────────────────────────────────────────
    async def _wait_for_operation(
        self,
        operation_data: dict,
        zone: str,
        label: str,
        max_polls: int = 30,
        poll_interval: int = 5,
    ) -> bool:
        """Poll a GCP zone operation until DONE. Returns True if succeeded."""
        op_name = operation_data.get("name", "")
        op_status = operation_data.get("status", "")

        if not op_name:
            await self.emit("warning", f"⚠️ [{label}] No operation name in response — cannot verify deployment.")
            return False

        if op_status == "DONE":
            if operation_data.get("error"):
                errs = operation_data["error"].get("errors", [])
                err_msg = errs[0].get("message", "Unknown error") if errs else "Unknown error"
                await self.emit("warning", f"⚠️ [{label}] Operation completed with error: {err_msg}")
                return False
            return True

        await self.emit("info", f"⏳ [{label}] Operation {op_name[:20]}... submitted. Polling status...")

        op_zone = operation_data.get("zone", "")
        if "/zones/" in op_zone:
            op_zone_name = op_zone.split("/zones/")[-1]
            poll_url = (
                f"https://compute.googleapis.com/compute/v1/projects/{self.project}"
                f"/zones/{op_zone_name}/operations/{op_name}"
            )
        elif zone:
            poll_url = (
                f"https://compute.googleapis.com/compute/v1/projects/{self.project}"
                f"/zones/{zone}/operations/{op_name}"
            )
        else:
            poll_url = (
                f"https://compute.googleapis.com/compute/v1/projects/{self.project}"
                f"/global/operations/{op_name}"
            )

        poll_url_beta = poll_url.replace("/compute/v1/", "/compute/beta/")

        for poll_num in range(1, max_polls + 1):
            if self.cancelled:
                return False

            await asyncio.sleep(poll_interval)
            token = await self._get_token()
            headers = {"Authorization": f"Bearer {token}"}

            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(poll_url, headers=headers)
                    if resp.status_code == 404:
                        resp = await client.get(poll_url_beta, headers=headers)
                    if resp.status_code != 200:
                        await self.emit("info", f"⏳ [{label}] Poll {poll_num}/{max_polls} — HTTP {resp.status_code}")
                        continue

                    op = resp.json()
                    status = op.get("status", "UNKNOWN")

                    if status == "DONE":
                        if op.get("error"):
                            errs = op["error"].get("errors", [])
                            err_msg = errs[0].get("message", "Unknown") if errs else "Unknown"
                            await self.emit(
                                "warning",
                                f"⚠️ [{label}] Operation finished with ERROR: {err_msg}",
                            )
                            return False
                        await self.emit(
                            "info",
                            f"✅ [{label}] Operation verified DONE — resource successfully created!",
                        )
                        return True
                    else:
                        if poll_num % 3 == 0:
                            await self.emit(
                                "info",
                                f"⏳ [{label}] Poll {poll_num}/{max_polls} — status: {status}",
                            )
            except Exception as e:
                await self.emit("info", f"⏳ [{label}] Poll error: {str(e)[:100]}")

        await self.emit(
            "warning",
            f"⚠️ [{label}] Operation not confirmed after {max_polls * poll_interval}s. "
            "Resource may still be provisioning — check GCP Console.",
        )
        return False

    def _resolve_valid_zones_for_method(self, method: str, requested_zones: list[str]) -> tuple[list[str], list[str]]:
        """Return (valid_zones, skipped_zones) for a given method and machine type."""
        supported_zones = get_zones_for_machine_type(self.machine_type)
        if method == ConsumptionModel.DWS_CALENDAR:
            cal_zones = get_calendar_zones_for_machine_type(self.machine_type)
            if cal_zones:
                supported_zones = cal_zones
        valid_zones = [z for z in requested_zones if z in supported_zones]
        skipped = [z for z in requested_zones if z not in supported_zones]
        return valid_zones, skipped

    # ── Main run logic ─────────────────────────────────────────────────
    async def run(self, parallel: bool = False):
        self.status = ScanningStatus.RUNNING
        mode_label = "⚡ PARALLEL" if parallel else "📋 SEQUENTIAL"
        await self.emit(
            "start",
            f"🚀 Starting GPU/TPU scan for {self.vm_count}x {self.machine_type} ({mode_label} mode)",
        )

        is_tpu = any(
            self.machine_type in tpu.get("machine_types", {})
            for tpu in TPU_TYPES.values()
        )
        if self.machine_type not in MACHINE_TYPES and not is_tpu:
            self.status = ScanningStatus.FAILED
            await self.emit("error", f"❌ Unknown machine type: {self.machine_type}.")
            return

        try:
            await self._get_token()
            await self.emit("info", "🔑 Authentication successful")
        except Exception as e:
            self.status = ScanningStatus.FAILED
            await self.emit("error", f"❌ Authentication failed: {str(e)}")
            return

        family = MACHINE_TO_FAMILY.get(self.machine_type)
        if family:
            await self.emit(
                "info",
                f"📋 Machine family: {family} | GPU: {MACHINE_TYPES[self.machine_type]['gpu']}",
            )
        else:
            tpu_spec = get_tpu_spec(self.machine_type, self.vm_count)
            tpu_desc = f"{tpu_spec['name']} ({tpu_spec['accelerator_type']})" if tpu_spec else "TPU"
            await self.emit("info", f"📋 Machine type: {self.machine_type} | {tpu_desc}")

        if parallel:
            await self._run_parallel()
            return

        for priority_idx, priority in enumerate(self.priorities):
            if self.cancelled:
                self.status = ScanningStatus.CANCELLED
                await self.emit("cancelled", "🛑 Scanning cancelled by user.")
                return

            method = priority["method"]
            zones = priority.get("zones", [])
            max_retries = priority.get("max_retries", 5)
            retry_interval = priority.get("retry_interval", 60)
            name_prefix = priority.get("name_prefix", "")

            method_label = CONSUMPTION_LABELS.get(method, method)
            priority_num = priority_idx + 1
            total_priorities = len(self.priorities)

            await self.emit(
                "priority_start",
                f"📌 Priority {priority_num}/{total_priorities}: Trying {method_label}",
                {"priority": priority_num, "method": method, "zones": zones},
            )

            if not is_consumption_supported(self.machine_type, method):
                await self.emit(
                    "warning",
                    f"⚠️ {method_label} is NOT supported for {self.machine_type} ({family or 'TPU'}). Skipping.",
                )
                continue

            valid_zones, skipped = self._resolve_valid_zones_for_method(method, zones)
            for z in skipped:
                await self.emit(
                    "warning",
                    f"⚠️ Zone {z} not supported for {self.machine_type} ({method_label}). Skipping.",
                )

            if not valid_zones:
                await self.emit(
                    "warning",
                    f"⚠️ No valid zones for {method_label}. Skipping to next priority.",
                )
                continue

            await self.emit(
                "info",
                f"🔍 Valid zones for {method_label}: {', '.join(valid_zones)}",
            )

            flex_max_wait = priority.get("flex_max_wait_hours", 168)
            flex_usage_dur = priority.get("flex_usage_duration_hours", 24)
            cal_start = priority.get("calendar_start_time", "")
            cal_end = priority.get("calendar_end_time", "")

            success = await self._scan_with_method(
                method,
                valid_zones,
                max_retries,
                retry_interval,
                priority_num,
                name_prefix,
                flex_max_wait,
                flex_usage_dur,
                cal_start,
                cal_end,
            )

            if success:
                self.status = ScanningStatus.SUCCESS
                actual_count = self.result.get("vm_count", self.vm_count) if self.result else self.vm_count
                await self.emit(
                    "success",
                    f"✅ Scan successful! Secured {actual_count}x {self.machine_type} via {method_label}.",
                    {"method": method, "priority": priority_num, "result": self.result},
                )
                _schedule_session_cleanup(self.session_id)
                return

            await self.emit(
                "priority_exhausted",
                f"❌ Priority {priority_num} ({method_label}) exhausted. Moving to next.",
                {"priority": priority_num, "method": method},
            )

        self.status = ScanningStatus.FAILED
        await self.emit(
            "failed",
            f"❌ Scan failed. All priorities exhausted for {self.vm_count}x {self.machine_type}.",
        )
        _schedule_session_cleanup(self.session_id)

    async def _run_parallel(self):
        tasks_info = []
        for pi, priority in enumerate(self.priorities):
            method = priority["method"]
            zones = priority.get("zones", [])
            method_label = CONSUMPTION_LABELS.get(method, method)
            name_prefix = priority.get("name_prefix", "")

            if not is_consumption_supported(self.machine_type, method):
                await self.emit("warning", f"⚠️ {method_label} not supported. Skipping.")
                continue
            valid_zones, _skipped = self._resolve_valid_zones_for_method(method, zones)
            if not valid_zones:
                await self.emit("warning", f"⚠️ No valid zones for {method_label}. Skipping.")
                continue
            tasks_info.append({
                "method": method,
                "zones": valid_zones,
                "max_retries": priority.get("max_retries", 5),
                "retry_interval": priority.get("retry_interval", 60),
                "label": method_label,
                "priority": pi + 1,
                "name_prefix": name_prefix,
                "flex_max_wait_hours": priority.get("flex_max_wait_hours", 168),
                "flex_usage_duration_hours": priority.get("flex_usage_duration_hours", 24),
                "calendar_start_time": priority.get("calendar_start_time", ""),
                "calendar_end_time": priority.get("calendar_end_time", ""),
            })

        if not tasks_info:
            self.status = ScanningStatus.FAILED
            await self.emit("failed", "❌ No valid priorities to run in parallel.")
            return

        await self.emit(
            "info",
            f"⚡ Running {len(tasks_info)} methods in parallel: {', '.join(t['label'] for t in tasks_info)}",
        )
        winner_event = asyncio.Event()
        winner_result = {"method": None}

        async def parallel_scan(task_info):
            method, method_label = task_info["method"], task_info["label"]
            zones, name_prefix = task_info["zones"], task_info["name_prefix"]
            max_retries, retry_interval = task_info["max_retries"], task_info["retry_interval"]

            await self.emit(
                "priority_start",
                f"⚡ [PARALLEL] Starting {method_label} ({len(zones)} zones)",
                {"priority": task_info["priority"], "method": method, "parallel": True},
            )

            for attempt in range(1, max_retries + 1):
                if self.cancelled or winner_event.is_set() or self._is_hunting_expired():
                    return False
                for zone in zones:
                    if self.cancelled or winner_event.is_set() or self._is_hunting_expired():
                        return False
                    for candidate_count in self._get_vm_count_candidates():
                        if self.cancelled or winner_event.is_set() or self._is_hunting_expired():
                            return False
                        self.vm_count = candidate_count
                        count_note = f" ({candidate_count}x)" if self.min_vm_count < self.max_vm_count else ""
                        await self.emit(
                            "attempt",
                            f"🔄 [{method_label}] Attempt {attempt}/{max_retries} — {zone}{count_note}",
                            {"attempt": attempt, "zone": zone, "method": method, "vmCount": candidate_count},
                        )
                        try:
                            await self._refresh_token()
                            success = await self._dispatch_method(
                                method,
                                zone,
                                name_prefix,
                                task_info.get("flex_max_wait_hours", 168),
                                task_info.get("flex_usage_duration_hours", 24),
                                task_info.get("calendar_start_time", ""),
                                task_info.get("calendar_end_time", ""),
                            )
                            if success:
                                if winner_event.is_set():
                                    await self.emit(
                                        "warning",
                                        f"[{method_label}] Created resource in {zone} but another method already won.",
                                    )
                                    return False
                                winner_result["method"] = method_label
                                winner_event.set()
                                return True
                        except Exception as e:
                            await self.emit("error", f"⚠️ [{method_label}] {zone}: {str(e)}")

                if attempt < max_retries and not winner_event.is_set():
                    await self.emit(
                        "waiting",
                        f"⏳ [{method_label}] Waiting {retry_interval}s ({attempt}/{max_retries})...",
                    )
                    for _ in range(retry_interval):
                        if self.cancelled or winner_event.is_set() or self._is_hunting_expired():
                            return False
                        await asyncio.sleep(1)

            await self.emit("priority_exhausted", f"❌ [{method_label}] All retries exhausted.")
            return False

        results = await asyncio.gather(*[parallel_scan(t) for t in tasks_info], return_exceptions=True)
        any_success = any(r is True for r in results if not isinstance(r, Exception))

        if any_success:
            self.status = ScanningStatus.SUCCESS
            actual_count = self.result.get("vm_count", self.vm_count) if self.result else self.vm_count
            await self.emit(
                "success",
                f"✅ Scan successful! Secured {actual_count}x {self.machine_type} "
                f"via {winner_result['method']} (parallel).",
                {"result": self.result},
            )
        elif self.cancelled:
            self.status = ScanningStatus.CANCELLED
            await self.emit("cancelled", "🛑 Scanning cancelled.")
        else:
            self.status = ScanningStatus.FAILED
            await self.emit("failed", f"❌ All {len(tasks_info)} parallel methods exhausted.")
        _schedule_session_cleanup(self.session_id)

    async def _scan_with_method(
        self,
        method,
        zones,
        max_retries,
        retry_interval,
        priority_num,
        name_prefix="",
        flex_max_wait_hours=168,
        flex_usage_duration_hours=24,
        calendar_start_time="",
        calendar_end_time="",
    ):
        method_label = CONSUMPTION_LABELS.get(method, method)
        for attempt in range(1, max_retries + 1):
            if self.cancelled:
                return False
            if self._is_hunting_expired():
                await self.emit(
                    "warning",
                    f"⏰ Total hunting time limit ({self.total_hunting_hours}h) reached.",
                )
                return False
            for zone in zones:
                if self.cancelled:
                    return False
                if self._is_hunting_expired():
                    await self.emit(
                        "warning",
                        f"⏰ Total hunting time limit ({self.total_hunting_hours}h) reached.",
                    )
                    return False
                for candidate_count in self._get_vm_count_candidates():
                    if self.cancelled or self._is_hunting_expired():
                        return False
                    self.vm_count = candidate_count
                    count_note = f" ({candidate_count}x)" if self.min_vm_count < self.max_vm_count else ""
                    await self.emit(
                        "attempt",
                        f"🔄 [{method_label}] Attempt {attempt}/{max_retries} — zone: {zone}{count_note}",
                        {
                            "attempt": attempt,
                            "maxRetries": max_retries,
                            "zone": zone,
                            "method": method,
                            "vmCount": candidate_count,
                        },
                    )
                    try:
                        await self._refresh_token()
                        if await self._dispatch_method(
                            method,
                            zone,
                            name_prefix,
                            flex_max_wait_hours,
                            flex_usage_duration_hours,
                            calendar_start_time,
                            calendar_end_time,
                        ):
                            return True
                    except Exception as e:
                        await self.emit(
                            "error",
                            f"⚠️ [{method_label}] Error in {zone}: {str(e)}",
                            {"zone": zone, "error": str(e), "attempt": attempt},
                        )
            if attempt < max_retries:
                await self.emit(
                    "waiting",
                    f"⏳ Waiting {retry_interval}s before next attempt ({attempt}/{max_retries})...",
                )
                for _ in range(retry_interval):
                    if self.cancelled or self._is_hunting_expired():
                        return False
                    await asyncio.sleep(1)
        return False

    def _is_tpu_type(self) -> bool:
        """Check if current machine type is a TPU type."""
        return any(self.machine_type in t.get("machine_types", {}) for t in TPU_TYPES.values())

    def _get_tpu_version(self) -> str:
        """Get the TPU version (e.g., 'v7x', 'v6e', 'v5p') for the current machine type."""
        for tpu_type, tpu_info in TPU_TYPES.items():
            if self.machine_type in tpu_info.get("machine_types", {}):
                return tpu_type
        return ""

    async def _dispatch_method(
        self,
        method,
        zone,
        name_prefix="",
        flex_max_wait_hours=168,
        flex_usage_duration_hours=24,
        calendar_start_time="",
        calendar_end_time="",
    ):
        if method == ConsumptionModel.ON_DEMAND:
            if self._is_tpu_type():
                return await self._try_tpu_on_demand(zone, name_prefix)
            return await self._try_on_demand_rest(zone, name_prefix)
        elif method == ConsumptionModel.DWS_CALENDAR:
            # Both GPU and TPU Calendar Mode create and secure a GCE Future Reservation
            # (specificSkuProperties for GPU, aggregateReservation for TPU) so customers
            # can attach GKE node pools or GCE/TPU instances to the reservation.
            return await self._try_dws_calendar_rest(
                zone, name_prefix, calendar_start_time, calendar_end_time
            )
        elif method == ConsumptionModel.DWS_FLEX:
            if self._is_tpu_type():
                return await self._try_tpu_queued_resource(
                    zone, name_prefix, flex_max_wait_hours, flex_usage_duration_hours
                )
            return await self._try_dws_flex_rest(
                zone, name_prefix, flex_max_wait_hours, flex_usage_duration_hours
            )
        elif method == ConsumptionModel.SPOT:
            if self._is_tpu_type():
                return await self._try_tpu_spot(zone, name_prefix)
            return await self._try_spot_rest(zone, name_prefix)
        return False

    # ── Resource creation methods ──────────────────────────────────────

    def _make_name(self, prefix: str, method_tag: str, zone: str) -> str:
        """Generate resource name with optional user prefix (max 63 chars)."""
        short_zone = zone.replace("-", "")
        short_id = self.session_id[:8]
        if prefix:
            return f"{prefix}-{method_tag}-{short_id}-{short_zone}"[:63]
        return f"gpu-radar-{method_tag}-{short_id}-{short_zone}"[:63]

    async def _try_on_demand_rest(self, zone: str, name_prefix: str = "") -> bool:
        """Create on-demand reservation and poll operation to verify.
        Preserves reservation-first workflow so customers can attach VMs or GKE node pools later.
        """
        res_name = self._make_name(name_prefix, "od", zone)
        token = await self._get_token()

        await self.emit(
            "action",
            f"📡 Creating on-demand reservation '{res_name}' in {zone}...",
        )

        url = (
            f"https://compute.googleapis.com/compute/v1/projects/{self.project}"
            f"/zones/{zone}/reservations"
        )
        instance_props = {"machineType": self.machine_type}
        machine_info = MACHINE_TYPES.get(self.machine_type, {})
        # Guest-attached GPUs (N1 / T4) must include bare acceleratorType name in reservation
        if machine_info.get("guest_attached_gpu") and machine_info.get("accelerator_type"):
            instance_props["guestAccelerators"] = [{
                "acceleratorType": machine_info["accelerator_type"],
                "acceleratorCount": machine_info.get("gpu_count", 1),
            }]

        body = {
            "name": res_name,
            "specificReservation": {
                "count": str(self.vm_count),
                "instanceProperties": instance_props,
            },
            "specificReservationRequired": True,
        }
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(url, json=body, headers=headers)
                data = resp.json()

                if resp.status_code in (200, 201):
                    verified = await self._wait_for_operation(data, zone, "On-Demand")
                    if verified:
                        self.result = {
                            "method": "on_demand",
                            "reservation_name": res_name,
                            "zone": zone,
                            "vm_count": self.vm_count,
                        }
                        self._log_deployment_event("on_demand", zone, res_name, True, "reservation")
                        await self.emit(
                            "info",
                            f"✅ On-demand reservation verified: {res_name} in {zone} ({self.vm_count} VMs)",
                        )
                        return True
                    else:
                        self._log_deployment_event("on_demand", zone, res_name, False, "reservation")
                        return False
                else:
                    await self.emit(
                        "warning",
                        f"⚠️ On-demand failed in {zone}: {self._parse_api_error(data)}",
                    )
                    return False
        except httpx.TimeoutException:
            await self.emit("warning", f"⚠️ Timeout in {zone}")
            return False

    async def _try_dws_calendar_rest(
        self,
        zone: str,
        name_prefix: str = "",
        calendar_start_time: str = "",
        calendar_end_time: str = "",
    ) -> bool:
        """Create DWS Calendar Mode Future Reservation via REST API (beta).
        Supports both GPU (specificSkuProperties + DENSE) and TPU (aggregateReservation).
        """
        cal_cfg = get_calendar_config_for_machine_type(self.machine_type)
        if not cal_cfg:
            await self.emit(
                "warning",
                f"⚠️ DWS Calendar Mode is not supported for {self.machine_type}.",
            )
            return False

        res_name = self._make_name(name_prefix, "cal", zone)
        token = await self._get_token()

        min_ahead_hours = cal_cfg.get("min_ahead_hours", 1)
        min_duration_days = cal_cfg.get("min_duration_days", 1)
        now_utc = datetime.now(timezone.utc)
        earliest_start = (now_utc + timedelta(hours=min_ahead_hours + 2)).replace(
            minute=0, second=0, microsecond=0
        )

        if calendar_start_time:
            norm_start = _normalize_datetime(calendar_start_time)
            try:
                parsed_start = datetime.strptime(norm_start, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                parsed_start = earliest_start
            if parsed_start < earliest_start:
                await self.emit(
                    "info",
                    f"ℹ️ Adjusting Calendar start time to {earliest_start.strftime('%Y-%m-%dT%H:%M:%SZ')} "
                    f"(minimum lead time for {self.machine_type} is {min_ahead_hours}h).",
                )
                parsed_start = earliest_start
        else:
            parsed_start = earliest_start

        if calendar_end_time:
            norm_end = _normalize_datetime(calendar_end_time)
            try:
                parsed_end = datetime.strptime(norm_end, "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                parsed_end = parsed_start + timedelta(days=min_duration_days)
        else:
            req_days = max(min_duration_days, (self.dws_calendar_duration_hours + 23) // 24)
            parsed_end = parsed_start + timedelta(days=req_days)

        # Calendar Mode requires duration in whole-day (24h) increments >= min_duration_days
        dur_seconds = (parsed_end - parsed_start).total_seconds()
        min_dur_seconds = min_duration_days * 86400
        if dur_seconds < min_dur_seconds:
            parsed_end = parsed_start + timedelta(days=min_duration_days)
        elif int(dur_seconds) % 86400 != 0:
            whole_days = max(min_duration_days, round(dur_seconds / 86400))
            parsed_end = parsed_start + timedelta(days=whole_days)

        start_str = parsed_start.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = parsed_end.strftime("%Y-%m-%dT%H:%M:%SZ")

        url = (
            f"https://compute.googleapis.com/compute/beta/projects/{self.project}"
            f"/zones/{zone}/futureReservations"
        )
        short_zone = zone.replace("-", "")[:8]
        base_prefix = (name_prefix if name_prefix else f"cr-{self.session_id[:8]}")[:20]
        # Reservation name must be <= 38 chars for Future Reservations
        target_res_name = f"{base_prefix}-rsv-{short_zone}"[:38]

        body = {
            "name": res_name,
            "reservationMode": "CALENDAR",
            "specificReservationRequired": True,
            "planningStatus": "SUBMITTED",
            "reservationName": target_res_name,
            "autoDeleteAutoCreatedReservations": True,
            "autoCreatedReservationsDeleteTime": end_str,
            "timeWindow": {"startTime": start_str, "endTime": end_str},
            "shareSettings": {"shareType": "LOCAL"},
        }

        if cal_cfg.get("category") == "TPU":
            chips_per_vm = cal_cfg.get("chips_per_vm", 1)
            allowed = cal_cfg.get("allowed_accelerator_counts", [1, 4, 8, 16, 32, 64, 128, 256])
            desired_chips = max(1, self.vm_count) * chips_per_vm
            total_chips = min(allowed, key=lambda c: abs(c - desired_chips))
            eff_vm_count = max(1, total_chips // chips_per_vm)

            agg_res = {
                "vmFamily": cal_cfg["vm_family"],
                "reservedResources": [{
                    "accelerator": {
                        "acceleratorCount": total_chips,
                        "acceleratorType": f"zones/{zone}/acceleratorTypes/{cal_cfg['gce_accelerator_type']}",
                    }
                }],
            }
            if cal_cfg.get("requires_workload_type"):
                agg_res["workloadType"] = "SERVING" if total_chips <= 8 else "BATCH"
            elif cal_cfg.get("default_workload_type"):
                agg_res["workloadType"] = cal_cfg["default_workload_type"]
            body["aggregateReservation"] = agg_res
        else:
            min_vms = cal_cfg.get("min_vm_count", 1)
            max_vms = cal_cfg.get("max_vm_count", 128)
            step = cal_cfg.get("vm_count_step", 1)
            eff_vm_count = max(min_vms, min(max_vms, self.vm_count))
            if step > 1 and eff_vm_count % step != 0:
                eff_vm_count = min(max_vms, ((eff_vm_count + step - 1) // step) * step)

            body["specificSkuProperties"] = {
                "totalCount": str(eff_vm_count),
                "instanceProperties": {"machineType": self.machine_type},
            }
            body["deploymentType"] = cal_cfg.get("deployment_type", "DENSE")

        await self.emit(
            "action",
            f"📡 Creating DWS Calendar future reservation '{res_name}' in {zone} "
            f"({start_str} → {end_str}, count={eff_vm_count})...",
        )

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(url, json=body, headers=headers)
                data = resp.json()
                if resp.status_code in (200, 201):
                    verified = await self._wait_for_operation(data, zone, "DWS Calendar")
                    if verified:
                        approved = await self._poll_future_reservation_status(
                            zone, res_name, max_polls=60, poll_interval=10
                        )
                        if approved:
                            self.result = {
                                "method": "dws_calendar",
                                "future_reservation_name": res_name,
                                "reservation_name": target_res_name,
                                "zone": zone,
                                "vm_count": eff_vm_count,
                                "start_time": start_str,
                                "end_time": end_str,
                            }
                            self._log_deployment_event("dws_calendar", zone, res_name, True, "future_reservation")
                            await self.emit(
                                "info",
                                f"✅ DWS Calendar reservation APPROVED: {res_name} "
                                f"(target reservation: {target_res_name}) in {zone}",
                            )
                            return True
                        else:
                            self._log_deployment_event(
                                "dws_calendar",
                                zone,
                                res_name,
                                False,
                                "future_reservation",
                                {"status": "pending_approval"},
                            )
                            await self.emit(
                                "info",
                                f"📋 DWS Calendar submitted in {zone}: {res_name}. "
                                f"Pending Google approval — not yet active. Continuing to try other options...",
                            )
                            return False
                    return False
                else:
                    await self.emit(
                        "warning",
                        f"⚠️ DWS Calendar failed in {zone}: {self._parse_api_error(data)}",
                    )
                    return False
        except httpx.TimeoutException:
            await self.emit("warning", f"⚠️ Timeout creating DWS Calendar in {zone}")
            return False

    async def _poll_future_reservation_status(
        self,
        zone: str,
        name: str,
        max_polls: int = 360,
        poll_interval: int = 30,
    ) -> bool:
        """Poll a future reservation until APPROVED, REJECTED, or max_polls reached."""
        await self.emit(
            "info",
            f"⏳ Polling future reservation '{name}' "
            f"(every {poll_interval}s, max {max_polls} polls)...",
        )
        poll_num = 0
        while max_polls <= 0 or poll_num < max_polls:
            if self.cancelled:
                return False
            await asyncio.sleep(poll_interval)
            poll_num += 1
            token = await self._get_token()
            url = (
                f"https://compute.googleapis.com/compute/beta/projects/{self.project}"
                f"/zones/{zone}/futureReservations/{name}"
            )
            headers = {"Authorization": f"Bearer {token}"}
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        status = data.get("status", {}).get("procurementStatus", "UNKNOWN")
                        if status in ("APPROVED", "PROVISIONING", "FULFILLED"):
                            await self.emit(
                                "info",
                                f"✅ Future reservation '{name}' APPROVED! Status: {status}",
                            )
                            return True
                        elif status in ("FAILED", "CANCELLED", "DECLINED"):
                            await self.emit(
                                "warning",
                                f"⚠️ Future reservation '{name}' REJECTED. Status: {status}",
                            )
                            return False
                        else:
                            if poll_num % 6 == 0:
                                mins_elapsed = (poll_num * poll_interval) // 60
                                await self.emit(
                                    "info",
                                    f"⏳ Future reservation '{name}' status: {status} "
                                    f"(waiting {mins_elapsed} min so far)",
                                )
                    elif resp.status_code == 404:
                        await self.emit(
                            "warning",
                            f"⚠️ Future reservation '{name}' not found (may have been deleted).",
                        )
                        return False
            except Exception as e:
                if poll_num % 6 == 0:
                    await self.emit("info", f"⏳ Poll error: {str(e)[:80]}")

        await self.emit(
            "warning",
            f"⚠️ Future reservation '{name}' not resolved after "
            f"{poll_num * poll_interval}s. Check GCP Console.",
        )
        return False

    def _build_gpu_instance_body(
        self,
        inst_name: str,
        zone: str,
        network: str,
        subnetwork: Optional[str],
        provisioning_model: str,
        label_method: str,
        max_run_secs: int = 0,
        wait_secs: int = 0,
    ) -> dict:
        """Build a valid GCE instances.insert body for either SPOT or FLEX_START."""
        machine_info = MACHINE_TYPES.get(self.machine_type, {})
        disk_type = machine_info.get("default_boot_disk_type", "pd-balanced")
        requires_hyperdisk = machine_info.get("requires_hyperdisk", False)
        requires_gvnic = machine_info.get("requires_gvnic", True)

        boot_disk = {
            "boot": True,
            "autoDelete": True,
            "initializeParams": {
                "sourceImage": "projects/debian-cloud/global/images/family/debian-12",
                "diskSizeGb": "100" if requires_hyperdisk else "50",
                "diskType": f"zones/{zone}/diskTypes/{disk_type}",
            },
        }
        if requires_gvnic:
            boot_disk["guestOsFeatures"] = [{"type": "GVNIC"}]

        net_iface = {
            "network": network,
            **({"subnetwork": subnetwork} if subnetwork else {}),
            **({"nicType": "GVNIC"} if requires_gvnic else {}),
            "accessConfigs": [{"type": "ONE_TO_ONE_NAT", "name": "External NAT"}],
        }

        scheduling = {
            "provisioningModel": provisioning_model,
            "instanceTerminationAction": "DELETE",
            "automaticRestart": False,
            "onHostMaintenance": "TERMINATE",
        }
        if provisioning_model == "FLEX_START":
            clamped_run = min(604800, max(600, max_run_secs))
            scheduling["maxRunDuration"] = {"seconds": str(clamped_run)}

        body = {
            "name": inst_name,
            "machineType": f"zones/{zone}/machineTypes/{self.machine_type}",
            "scheduling": scheduling,
            "disks": [boot_disk],
            "networkInterfaces": [net_iface],
            "labels": self._tracking_labels(label_method),
        }

        # IMPORTANT: Only attach guestAccelerators for guest-attached GPU families (N1 / T4).
        # Built-in GPU families (G2, G4, A2, A3, A4, A4X) auto-populate GPUs and Local SSDs.
        if machine_info.get("guest_attached_gpu") and machine_info.get("accelerator_type"):
            body["guestAccelerators"] = [{
                "acceleratorType": f"zones/{zone}/acceleratorTypes/{machine_info['accelerator_type']}",
                "acceleratorCount": machine_info.get("gpu_count", 1),
            }]

        if provisioning_model == "FLEX_START" and wait_secs > 0:
            clamped_wait = min(604800, max(600, wait_secs))
            body["params"] = {
                "requestValidForDuration": {"seconds": str(clamped_wait)},
            }

        return body

    async def _try_dws_flex_rest(
        self,
        zone: str,
        name_prefix: str = "",
        flex_max_wait_hours: int = 168,
        flex_usage_duration_hours: int = 24,
    ) -> bool:
        """Provision GPU VM(s) using genuine DWS Flex Start (provisioningModel=FLEX_START).
        Uses instances.insert with scheduling.provisioningModel='FLEX_START',
        maxRunDuration (up to 7 days), and params.requestValidForDuration.
        """
        token = await self._get_token()
        network = await self._get_network(token, zone)
        subnetwork = await self._get_gpu_subnetwork(token, zone)

        # DWS Flex Start maxRunDuration and requestValidForDuration are capped at 7 days (604800s)
        max_run_secs = min(604800, max(600, int(flex_usage_duration_hours) * 3600))
        wait_secs = min(604800, max(600, int(flex_max_wait_hours) * 3600))

        url = (
            f"https://compute.googleapis.com/compute/v1/projects/{self.project}"
            f"/zones/{zone}/instances"
        )
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        created = []
        for i in range(self.vm_count):
            if self.cancelled:
                return False
            suffix = f"-{i}" if self.vm_count > 1 else ""
            inst_name = self._make_name(name_prefix, f"flex{suffix}", zone)

            await self.emit(
                "action",
                f"📡 [DWS Flex Start] Creating FLEX_START VM '{inst_name}' in {zone} "
                f"(max wait: {wait_secs // 3600}h, max run: {max_run_secs // 3600}h"
                f"{f', {i+1}/{self.vm_count}' if self.vm_count > 1 else ''})...",
            )

            body = self._build_gpu_instance_body(
                inst_name=inst_name,
                zone=zone,
                network=network,
                subnetwork=subnetwork,
                provisioning_model="FLEX_START",
                label_method="dws-flex",
                max_run_secs=max_run_secs,
                wait_secs=wait_secs,
            )

            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.post(url, json=body, headers=headers)
                    data = resp.json()
                    if resp.status_code in (200, 201):
                        verified = await self._wait_for_operation(
                            data, zone, f"DWS Flex VM {inst_name}", max_polls=60, poll_interval=10
                        )
                        if verified:
                            created.append(inst_name)
                            await self.emit(
                                "info",
                                f"✅ DWS Flex Start VM verified running: {inst_name} in {zone}",
                            )
                        else:
                            await self.emit(
                                "warning",
                                f"⚠️ DWS Flex Start VM operation still queued or not verified for {inst_name}",
                            )
                            return False
                    else:
                        err_msg = self._parse_api_error(data)
                        await self.emit("warning", f"⚠️ [DWS Flex Start] {zone}: {err_msg}")
                        return False
            except httpx.TimeoutException:
                await self.emit("warning", f"⚠️ Timeout creating DWS Flex Start VM in {zone}")
                return False

        if created:
            self.result = {
                "method": "dws_flex",
                "instance_names": created,
                "zone": zone,
                "vm_count": len(created),
            }
            self._log_deployment_event(
                "dws_flex",
                zone,
                ",".join(created),
                True,
                "instance",
                {"instance_count": len(created), "provisioning_model": "FLEX_START"},
            )
            return True
        return False

    async def _resolve_network_selection(self, token: str, region: str) -> dict:
        """Resolve which VPC network + regional subnetwork to use."""
        cache_key = f"_cached_netsel_{region}"
        if hasattr(self, cache_key):
            return getattr(self, cache_key)

        if self.network:
            sel = {
                "network_name": self.network,
                "subnetwork_name": self.subnetwork or None,
                "region": region,
            }
            if not sel["subnetwork_name"]:
                try:
                    async with httpx.AsyncClient(timeout=15) as client:
                        sub_resp = await client.get(
                            f"https://compute.googleapis.com/compute/v1/projects/{self.project}"
                            f"/regions/{region}/subnetworks",
                            headers={"Authorization": f"Bearer {token}"},
                        )
                        if sub_resp.status_code == 200:
                            for s in sub_resp.json().get("items", []):
                                if s.get("network", "").rsplit("/", 1)[-1] == self.network:
                                    sel["subnetwork_name"] = s["name"]
                                    break
                except Exception:
                    pass
            setattr(self, cache_key, sel)
            return sel

        region_subnets = {}
        all_networks = []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                sub_resp = await client.get(
                    f"https://compute.googleapis.com/compute/v1/projects/{self.project}"
                    f"/regions/{region}/subnetworks",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if sub_resp.status_code == 200:
                    for s in sub_resp.json().get("items", []):
                        net = s.get("network", "").rsplit("/", 1)[-1]
                        if net and net not in region_subnets:
                            region_subnets[net] = s["name"]

                net_resp = await client.get(
                    f"https://compute.googleapis.com/compute/v1/projects/{self.project}"
                    f"/global/networks",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if net_resp.status_code == 200:
                    all_networks = [n["name"] for n in net_resp.json().get("items", [])]
        except Exception:
            pass

        chosen_net = None
        chosen_sub = None
        if "default" in all_networks:
            chosen_net = "default"
            chosen_sub = region_subnets.get("default")
        if not chosen_net:
            for net in all_networks:
                if net in region_subnets:
                    chosen_net, chosen_sub = net, region_subnets[net]
                    break
        if not chosen_net and all_networks:
            chosen_net = all_networks[0]
        if not chosen_net:
            chosen_net = "default"

        sel = {"network_name": chosen_net, "subnetwork_name": chosen_sub, "region": region}
        setattr(self, cache_key, sel)
        return sel

    async def _get_network(self, token: str, zone: str = "") -> str:
        """Return the GPU VM networkInterfaces[].network selfLink-style path."""
        if hasattr(self, "_cached_network"):
            return self._cached_network
        region = zone.rsplit("-", 1)[0] if zone else ""
        network_name = self.network
        if not network_name and region:
            sel = await self._resolve_network_selection(token, region)
            network_name = sel["network_name"]
        if not network_name:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(
                        f"https://compute.googleapis.com/compute/v1/projects/{self.project}/global/networks",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if resp.status_code == 200:
                        items = resp.json().get("items", [])
                        names = [n["name"] for n in items]
                        network_name = "default" if "default" in names else (names[0] if names else "default")
            except Exception:
                network_name = "default"
        self._cached_network = f"projects/{self.project}/global/networks/{network_name}"
        return self._cached_network

    async def _get_gpu_subnetwork(self, token: str, zone: str) -> Optional[str]:
        """Return the regional subnetwork path for GPU VMs, if resolvable."""
        region = zone.rsplit("-", 1)[0]
        sel = await self._resolve_network_selection(token, region)
        if sel.get("subnetwork_name"):
            return (
                f"projects/{self.project}/regions/{region}/subnetworks/"
                f"{sel['subnetwork_name']}"
            )
        return None

    async def _get_tpu_network_config(self, token: str, zone: str) -> dict:
        """Resolve a valid networkConfig for a TPU node in the given zone."""
        region = zone.rsplit("-", 1)[0]
        cache_key = f"_cached_tpu_netcfg_{region}"
        if hasattr(self, cache_key):
            return getattr(self, cache_key)

        sel = await self._resolve_network_selection(token, region)
        cfg = {
            "network": f"projects/{self.project}/global/networks/{sel['network_name']}",
            "enableExternalIps": True,
        }
        if sel.get("subnetwork_name"):
            cfg["subnetwork"] = (
                f"projects/{self.project}/regions/{region}/subnetworks/"
                f"{sel['subnetwork_name']}"
            )

        setattr(self, cache_key, cfg)
        return cfg

    async def _try_spot_rest(self, zone: str, name_prefix: str = "") -> bool:
        """Create Spot VM(s) and poll operation to verify."""
        token = await self._get_token()
        network = await self._get_network(token, zone)
        subnetwork = await self._get_gpu_subnetwork(token, zone)

        spot_count = self.vm_count
        url = (
            f"https://compute.googleapis.com/compute/v1/projects/{self.project}"
            f"/zones/{zone}/instances"
        )
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        created = []
        for i in range(spot_count):
            if self.cancelled:
                return False
            suffix = f"-{i}" if spot_count > 1 else ""
            inst_name = self._make_name(name_prefix, f"spot{suffix}", zone)

            await self.emit(
                "action",
                f"📡 Creating Spot VM '{inst_name}' in {zone}"
                f"{f' ({i+1}/{spot_count})' if spot_count > 1 else ''}...",
            )

            body = self._build_gpu_instance_body(
                inst_name=inst_name,
                zone=zone,
                network=network,
                subnetwork=subnetwork,
                provisioning_model="SPOT",
                label_method="spot",
            )

            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.post(url, json=body, headers=headers)
                    data = resp.json()
                    if resp.status_code in (200, 201):
                        verified = await self._wait_for_operation(data, zone, f"Spot VM {inst_name}")
                        if verified:
                            created.append(inst_name)
                            await self.emit(
                                "info",
                                f"✅ Spot VM verified running: {inst_name} in {zone}",
                            )
                        else:
                            await self.emit(
                                "warning",
                                f"⚠️ Spot VM operation not verified for {inst_name}",
                            )
                    else:
                        err_msg = self._parse_api_error(data)
                        await self.emit("warning", f"⚠️ Spot VM failed in {zone}: {err_msg}")
                        if "no capacity" in err_msg.lower() or "stock" in err_msg.lower():
                            return False
            except httpx.TimeoutException:
                await self.emit("warning", f"⚠️ Timeout creating Spot VM in {zone}")

        if created:
            self.result = {
                "method": "spot",
                "instance_names": created,
                "zone": zone,
                "vm_count": len(created),
            }
            self._log_deployment_event(
                "spot",
                zone,
                ",".join(created),
                True,
                "instance",
                {"instance_count": len(created)},
            )
            return True
        return False

    # ── TPU-specific methods ───────────────────────────────────────────

    def _get_tpu_accelerator_type(self, zone: str) -> str:
        """Build the TPU accelerator type string (e.g., v6e-4, v5p-8, v5litepod-4, tpu7x-8)."""
        spec = get_tpu_spec(self.machine_type, self.vm_count)
        if spec:
            return spec["accelerator_type"]
        return self.machine_type

    def _get_tpu_runtime_version(self) -> str:
        """Return the valid Cloud TPU runtimeVersion for the current TPU generation."""
        spec = get_tpu_spec(self.machine_type, self.vm_count)
        if spec:
            return spec["runtime_version"]
        return "tpu-ubuntu2204-base"

    async def _poll_tpu_operation(
        self,
        op_name: str,
        zone: str,
        label: str,
        api_version: str = "v2",
        max_polls: int = 60,
        poll_interval: int = 10,
    ) -> bool:
        """Poll a TPU operation until done."""
        await self.emit("info", f"⏳ [{label}] Polling TPU operation...")
        for poll_num in range(1, max_polls + 1):
            if self.cancelled:
                return False
            await asyncio.sleep(poll_interval)
            token = await self._get_token()
            url = f"https://tpu.googleapis.com/{api_version}/{op_name}"
            headers = {"Authorization": f"Bearer {token}"}
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("done"):
                            if data.get("error"):
                                err_msg = data["error"].get("message", "Unknown error")
                                await self.emit("warning", f"⚠️ [{label}] TPU operation failed: {err_msg}")
                                return False
                            await self.emit("info", f"✅ [{label}] TPU operation completed successfully!")
                            return True
                        elif poll_num % 6 == 0:
                            await self.emit(
                                "info",
                                f"⏳ [{label}] Still provisioning... (poll {poll_num}/{max_polls})",
                            )
            except Exception as e:
                if poll_num % 6 == 0:
                    await self.emit("info", f"⏳ [{label}] Poll error: {str(e)[:80]}")
        await self.emit(
            "warning",
            f"⚠️ [{label}] TPU operation not confirmed after {max_polls * poll_interval}s.",
        )
        return False

    async def _try_tpu_on_demand(self, zone: str, name_prefix: str = "") -> bool:
        """Create an on-demand TPU node using the Cloud TPU v2 API."""
        node_name = self._make_name(name_prefix, "tpu-od", zone)
        token = await self._get_token()
        spec = get_tpu_spec(self.machine_type, self.vm_count) or {}
        accel_type = spec.get("accelerator_type") or self._get_tpu_accelerator_type(zone)
        runtime_version = spec.get("runtime_version") or self._get_tpu_runtime_version()
        net_cfg = await self._get_tpu_network_config(token, zone)

        await self.emit(
            "action",
            f"📡 [TPU] Creating on-demand TPU node '{node_name}' ({accel_type}, runtime={runtime_version}) in {zone}...",
        )

        url = (
            f"https://tpu.googleapis.com/v2/projects/{self.project}"
            f"/locations/{zone}/nodes?nodeId={node_name}"
        )
        body = {
            "acceleratorType": accel_type,
            "runtimeVersion": runtime_version,
            "networkConfig": net_cfg,
            "labels": self._tracking_labels("on-demand"),
        }
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, json=body, headers=headers)
                data = resp.json()
                if resp.status_code in (200, 201):
                    op_name = data.get("name", "")
                    if op_name:
                        ready = await self._poll_tpu_operation(op_name, zone, "TPU On-Demand", api_version="v2")
                        if ready:
                            self.result = {
                                "method": "on_demand",
                                "tpu_node": node_name,
                                "zone": zone,
                                "accelerator_type": accel_type,
                                "vm_count": self.vm_count,
                            }
                            self._log_deployment_event("on_demand", zone, node_name, True, "tpu_node")
                            await self.emit(
                                "info",
                                f"✅ TPU node READY: {node_name} ({accel_type}) in {zone}",
                            )
                            return True
                        return False
                    else:
                        await self.emit(
                            "warning",
                            "⚠️ TPU On-Demand: No operation returned. Cannot verify deployment.",
                        )
                        return False
                else:
                    err_msg = data.get("error", {}).get("message", str(data)[:200])
                    await self.emit("warning", f"⚠️ TPU On-Demand failed in {zone}: {err_msg}")
                    return False
        except httpx.TimeoutException:
            await self.emit("warning", f"⚠️ Timeout creating TPU node in {zone}")
            return False

    async def _poll_tpu_queued_resource(
        self,
        zone: str,
        qr_name: str,
        label: str,
        max_polls: int = 120,
        poll_interval: int = 10,
    ) -> bool:
        """Poll a TPU Queued Resource (v2alpha1) until it is ACTIVE."""
        await self.emit(
            "info",
            f"⏳ [{label}] Polling queued resource '{qr_name}' until ACTIVE...",
        )
        for poll_num in range(1, max_polls + 1):
            if self.cancelled:
                return False
            await asyncio.sleep(poll_interval)
            token = await self._get_token()
            url = (
                f"https://tpu.googleapis.com/v2alpha1/projects/{self.project}"
                f"/locations/{zone}/queuedResources/{qr_name}"
            )
            headers = {"Authorization": f"Bearer {token}"}
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        state = data.get("state", {}).get("state", "UNKNOWN")
                        if state == "ACTIVE":
                            await self.emit(
                                "info",
                                f"✅ [{label}] Queued resource '{qr_name}' is ACTIVE — TPU deployed!",
                            )
                            return True
                        elif state in ("FAILED", "SUSPENDED", "DELETING"):
                            info_str = data.get("state", {}).get("stateInitiator", "")
                            await self.emit(
                                "warning",
                                f"⚠️ [{label}] Queued resource '{qr_name}' state: {state} ({info_str})",
                            )
                            return False
                        else:
                            if poll_num % 6 == 0:
                                await self.emit(
                                    "info",
                                    f"⏳ [{label}] Queued resource state: {state} "
                                    f"(poll {poll_num}/{max_polls})",
                                )
            except Exception as e:
                if poll_num % 6 == 0:
                    await self.emit("info", f"⏳ [{label}] Poll error: {str(e)[:80]}")
        await self.emit(
            "info",
            f"⏳ [{label}] Queued resource '{qr_name}' not ACTIVE after {max_polls * poll_interval}s. "
            "Continuing to try other options...",
        )
        return False

    def _build_tpu_queued_resource_node_spec(
        self,
        zone: str,
        qr_name: str,
        net_cfg: dict,
        label_method: str,
    ) -> tuple[dict, str, str]:
        """Build the tpu.nodeSpec entry for Cloud TPU QueuedResource (v2alpha1)."""
        spec = get_tpu_spec(self.machine_type, self.vm_count) or {}
        accel_type = spec.get("accelerator_type") or self._get_tpu_accelerator_type(zone)
        runtime_version = spec.get("runtime_version") or self._get_tpu_runtime_version()

        node_entry = {
            "parent": f"projects/{self.project}/locations/{zone}",
            "node": {
                "acceleratorType": accel_type,
                "runtimeVersion": runtime_version,
                "labels": self._tracking_labels(label_method),
                "networkConfig": net_cfg,
            },
        }
        if spec.get("use_multi_node"):
            node_entry["multiNodeParams"] = {
                "nodeCount": spec["node_count"],
                "nodeIdPrefix": f"{qr_name[:45]}-n",
                "workloadType": "AVAILABILITY_OPTIMIZED",
            }
        else:
            node_entry["nodeId"] = f"{qr_name[:55]}-node"

        return node_entry, accel_type, runtime_version

    async def _try_tpu_queued_resource(
        self,
        zone: str,
        name_prefix: str = "",
        flex_max_wait_hours: int = 168,
        flex_usage_duration_hours: int = 24,
    ) -> bool:
        """Create a TPU Queued Resource with provisioningModel=FLEX_START (v2alpha1)."""
        qr_name = self._make_name(name_prefix, "tpu-qr", zone)
        token = await self._get_token()
        net_cfg = await self._get_tpu_network_config(token, zone)
        node_entry, accel_type, runtime_version = self._build_tpu_queued_resource_node_spec(
            zone, qr_name, net_cfg, "dws-flex"
        )

        # Both validUntilDuration and maxRunDuration are clamped to [600s, 604800s (7 days)]
        wait_secs = min(604800, max(600, int(flex_max_wait_hours) * 3600))
        max_run_secs = min(604800, max(600, int(flex_usage_duration_hours) * 3600))

        await self.emit(
            "action",
            f"📡 [TPU] Creating FLEX_START Queued Resource '{qr_name}' ({accel_type}, runtime={runtime_version}) "
            f"in {zone} (max wait: {wait_secs // 3600}h, max run: {max_run_secs // 3600}h)...",
        )

        url = (
            f"https://tpu.googleapis.com/v2alpha1/projects/{self.project}"
            f"/locations/{zone}/queuedResources?queuedResourceId={qr_name}"
        )
        body = {
            "tpu": {
                "nodeSpec": [node_entry],
            },
            "provisioningModel": "FLEX_START",
            "runDuration": {
                "maxRunDuration": f"{max_run_secs}s",
            },
            "queueingPolicy": {
                "validUntilDuration": f"{wait_secs}s",
            },
        }
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, json=body, headers=headers)
                data = resp.json()
                if resp.status_code in (200, 201):
                    ready = await self._poll_tpu_queued_resource(zone, qr_name, "TPU Flex")
                    if ready:
                        self.result = {
                            "method": "dws_flex",
                            "queued_resource": qr_name,
                            "zone": zone,
                            "accelerator_type": accel_type,
                            "vm_count": self.vm_count,
                        }
                        self._log_deployment_event("dws_flex", zone, qr_name, True, "tpu_queued_resource")
                        await self.emit(
                            "info",
                            f"✅ TPU Queued Resource ACTIVE: {qr_name} ({accel_type}) in {zone}",
                        )
                        return True
                    else:
                        await self.emit(
                            "info",
                            f"📋 TPU Queued Resource submitted in {zone}: {qr_name}. "
                            "Not yet active — continuing to try other options...",
                        )
                        return False
                else:
                    err_msg = data.get("error", {}).get("message", str(data)[:200])
                    await self.emit(
                        "warning",
                        f"⚠️ TPU Queued Resource failed in {zone}: {err_msg}",
                    )
                    return False
        except httpx.TimeoutException:
            await self.emit("warning", f"⚠️ Timeout creating TPU Queued Resource in {zone}")
            return False

    async def _try_tpu_spot(self, zone: str, name_prefix: str = "") -> bool:
        """Create a Spot TPU Queued Resource (v2alpha1)."""
        qr_name = self._make_name(name_prefix, "tpu-spot", zone)
        token = await self._get_token()
        net_cfg = await self._get_tpu_network_config(token, zone)
        node_entry, accel_type, runtime_version = self._build_tpu_queued_resource_node_spec(
            zone, qr_name, net_cfg, "spot"
        )

        await self.emit(
            "action",
            f"📡 [TPU] Creating Spot TPU '{qr_name}' ({accel_type}, runtime={runtime_version}) in {zone}...",
        )

        url = (
            f"https://tpu.googleapis.com/v2alpha1/projects/{self.project}"
            f"/locations/{zone}/queuedResources?queuedResourceId={qr_name}"
        )
        body = {
            "tpu": {
                "nodeSpec": [node_entry],
            },
            "spot": {},
        }
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, json=body, headers=headers)
                data = resp.json()
                if resp.status_code in (200, 201):
                    ready = await self._poll_tpu_queued_resource(zone, qr_name, "TPU Spot")
                    if ready:
                        self.result = {
                            "method": "spot",
                            "queued_resource": qr_name,
                            "zone": zone,
                            "accelerator_type": accel_type,
                            "vm_count": self.vm_count,
                        }
                        self._log_deployment_event("spot", zone, qr_name, True, "tpu_queued_resource")
                        await self.emit(
                            "info",
                            f"✅ Spot TPU ACTIVE: {qr_name} ({accel_type}) in {zone}",
                        )
                        return True
                    else:
                        await self.emit(
                            "info",
                            f"📋 Spot TPU submitted in {zone}: {qr_name}. "
                            "Not yet active — continuing to try other options...",
                        )
                        return False
                else:
                    err_msg = data.get("error", {}).get("message", str(data)[:200])
                    await self.emit("warning", f"⚠️ Spot TPU failed in {zone}: {err_msg}")
                    return False
        except httpx.TimeoutException:
            await self.emit("warning", f"⚠️ Timeout creating Spot TPU in {zone}")
            return False

    def _parse_api_error(self, data: dict) -> str:
        error = data.get("error", {})
        message = error.get("message", "")
        code = error.get("code", 0)
        errors = error.get("errors", [])

        if not message and errors:
            message = errors[0].get("message", "Unknown error")
        ml = message.lower()
        if code == 403:
            return f"Permission denied ({code}). Check IAM permissions."
        elif code == 404:
            return f"Not found ({code}). Resource or API doesn't exist."
        elif code == 409:
            return f"Conflict ({code}). Resource may already exist."
        elif "quota" in ml:
            return f"Quota exceeded. ({message[:150]})"
        elif "zone does not have enough resources" in ml or "stockout" in ml:
            return "No capacity — zone out of stock."
        elif "not found" in ml and "machine" in ml:
            return f"Machine type '{self.machine_type}' not in this zone."
        elif "billing" in ml:
            return "Billing issue. Check project billing."
        elif message:
            return message[:200]
        return f"API error (HTTP {code})"

    def cancel(self):
        self.cancelled = True


# ── Session management ─────────────────────────────────────────────────
active_sessions: dict[str, ScanningSession] = {}


def _schedule_session_cleanup(session_id: str, delay: int = 300):
    """Remove session from active_sessions after a delay."""
    try:
        loop = asyncio.get_running_loop()
        loop.call_later(delay, lambda: active_sessions.pop(session_id, None))
    except RuntimeError:
        active_sessions.pop(session_id, None)


def create_session(
    project,
    machine_type,
    vm_count,
    priorities,
    send_update,
    dws_calendar_duration_hours=24,
    user_token=None,
    network=None,
    subnetwork=None,
    min_vm_count=None,
    max_vm_count=None,
    total_hunting_hours=1.0,
) -> ScanningSession:
    session_id = str(uuid.uuid4())
    session = ScanningSession(
        session_id=session_id,
        project=project,
        machine_type=machine_type,
        vm_count=vm_count,
        priorities=priorities,
        send_update=send_update,
        dws_calendar_duration_hours=dws_calendar_duration_hours,
        user_token=user_token,
        network=network,
        subnetwork=subnetwork,
        min_vm_count=min_vm_count,
        max_vm_count=max_vm_count,
        total_hunting_hours=total_hunting_hours,
    )
    active_sessions[session_id] = session
    return session


async def list_networks(project: str, token: str, region: str = "") -> dict:
    """List VPC networks (and regional subnetworks) available to the project."""
    result = {"hasDefault": False, "networks": []}
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            net_resp = await client.get(
                f"https://compute.googleapis.com/compute/v1/projects/{project}/global/networks",
                headers=headers,
            )
            networks = net_resp.json().get("items", []) if net_resp.status_code == 200 else []

            region_subnets = {}
            if region:
                sub_resp = await client.get(
                    f"https://compute.googleapis.com/compute/v1/projects/{project}"
                    f"/regions/{region}/subnetworks",
                    headers=headers,
                )
                if sub_resp.status_code == 200:
                    for s in sub_resp.json().get("items", []):
                        net = s.get("network", "").rsplit("/", 1)[-1]
                        region_subnets.setdefault(net, []).append(s["name"])

            for n in networks:
                name = n["name"]
                if name == "default":
                    result["hasDefault"] = True
                result["networks"].append({
                    "name": name,
                    "subnetworks": sorted(region_subnets.get(name, [])),
                })
    except Exception as e:
        result["error"] = str(e)
    return result


async def create_network(project: str, token: str, name: str) -> dict:
    """Create a new auto-mode VPC network (auto-creates regional subnets)."""
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"https://compute.googleapis.com/compute/v1/projects/{project}/global/networks"
    body = {"name": name, "autoCreateSubnetworks": True}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=body, headers=headers)
            data = resp.json()
            if resp.status_code in (200, 201):
                return {"ok": True, "operation": data.get("name", ""), "network": name}
            msg = data.get("error", {}).get("message", f"HTTP {resp.status_code}")
            return {"ok": False, "error": msg}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def cancel_session(session_id: str) -> bool:
    session = active_sessions.get(session_id)
    if session:
        session.cancel()
        return True
    return False


def get_session(session_id: str) -> Optional[ScanningSession]:
    return active_sessions.get(session_id)
