"""
GPU Radar - Priority-based GPU/TPU capacity scanning engine.
Supports: On-Demand Reservation, DWS Calendar, DWS Flex Start, Spot VMs.
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
    MACHINE_TYPES, get_zones_for_machine_type, is_consumption_supported,
    FAMILY_TO_GPU_ZONE_KEY, MACHINE_TO_FAMILY, GPU_ZONES
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
    import google.auth
    import google.auth.transport.requests
    creds, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
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
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            dt = datetime.strptime(dt_str, fmt)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            continue
    return dt_str if dt_str.endswith("Z") else dt_str + "Z"


class ScanningSession:
    """Manages a GPU scanning session with priority-based strategy."""

    def __init__(
        self,
        session_id: str,
        project: str,
        machine_type: str,
        vm_count: int,
        priorities: list[dict],
        send_update: Callable,
        dws_calendar_duration_hours: int = 24,
    ):
        self.session_id = session_id
        self.project = project
        self.machine_type = machine_type
        self.vm_count = vm_count
        self.priorities = priorities
        self.send_update = send_update
        self.dws_calendar_duration_hours = dws_calendar_duration_hours
        self.status = ScanningStatus.PENDING
        self.cancelled = False
        self.result = None
        self._token = None
        self._token_time = None

    async def _get_token(self) -> str:
        now = datetime.now(timezone.utc)
        if not self._token or not self._token_time or (now - self._token_time).total_seconds() > 3000:
            self._token = await get_access_token()
            self._token_time = now
        return self._token

    async def _refresh_token(self):
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
    async def _wait_for_operation(self, operation_data: dict, zone: str,
                                   label: str, max_polls: int = 30,
                                   poll_interval: int = 5) -> bool:
        """Poll a GCP zone operation until DONE. Returns True if succeeded."""
        op_name = operation_data.get("name", "")
        op_status = operation_data.get("status", "")

        if not op_name:
            await self.emit("warning", f"⚠️ [{label}] No operation name in response — cannot verify deployment.")
            return False

        if op_status == "DONE":
            # Check for errors in completed operation
            if operation_data.get("error"):
                errs = operation_data["error"].get("errors", [])
                err_msg = errs[0].get("message", "Unknown error") if errs else "Unknown error"
                await self.emit("warning", f"⚠️ [{label}] Operation completed with error: {err_msg}")
                return False
            return True

        await self.emit("info", f"⏳ [{label}] Operation {op_name[:20]}... submitted. Polling status...")
        token = await self._get_token()

        # Determine if it's a zone or global operation
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

        # Also try beta endpoint if v1 fails
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
                            await self.emit("warning",
                                f"⚠️ [{label}] Operation finished with ERROR: {err_msg}")
                            return False
                        await self.emit("info",
                            f"✅ [{label}] Operation verified DONE — resource successfully created!")
                        return True
                    else:
                        if poll_num % 3 == 0:  # Log every 3rd poll to reduce noise
                            await self.emit("info",
                                f"⏳ [{label}] Poll {poll_num}/{max_polls} — status: {status}")
            except Exception as e:
                await self.emit("info", f"⏳ [{label}] Poll error: {str(e)[:100]}")

        await self.emit("warning",
            f"⚠️ [{label}] Operation not confirmed after {max_polls * poll_interval}s. "
            "Resource may still be provisioning — check GCP Console.")
        return False

    # ── Main run logic ─────────────────────────────────────────────────
    async def run(self, parallel: bool = False):
        self.status = ScanningStatus.RUNNING
        mode_label = "⚡ PARALLEL" if parallel else "📋 SEQUENTIAL"
        await self.emit("start",
            f"🚀 Starting GPU scan for {self.vm_count}x {self.machine_type} ({mode_label} mode)")

        # Validate machine type (GPU or TPU)
        from gpu_data import TPU_TYPES
        is_tpu = any(self.machine_type in tpu.get("machine_types", {})
                      for tpu in TPU_TYPES.values())
        if self.machine_type not in MACHINE_TYPES and not is_tpu:
            self.status = ScanningStatus.FAILED
            await self.emit("error",
                f"❌ Unknown machine type: {self.machine_type}.")
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
            await self.emit("info",
                f"📋 Machine family: {family} | GPU: {MACHINE_TYPES[self.machine_type]['gpu']}")
        else:
            await self.emit("info", f"📋 Machine type: {self.machine_type} (TPU)")

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

            await self.emit("priority_start",
                f"📌 Priority {priority_num}/{total_priorities}: Trying {method_label}",
                {"priority": priority_num, "method": method, "zones": zones})

            if not is_consumption_supported(self.machine_type, method):
                await self.emit("warning",
                    f"⚠️ {method_label} is NOT supported for {self.machine_type} ({family}). Skipping.")
                continue

            supported_zones = get_zones_for_machine_type(self.machine_type)
            valid_zones = [z for z in zones if z in supported_zones]
            skipped = [z for z in zones if z not in supported_zones]
            for z in skipped:
                await self.emit("warning", f"⚠️ Zone {z} not supported for {self.machine_type}. Skipping.")

            if not valid_zones:
                await self.emit("warning",
                    f"⚠️ No valid zones for {method_label}. Skipping to next priority.")
                continue

            await self.emit("info",
                f"🔍 Valid zones for {method_label}: {', '.join(valid_zones)}")

            flex_max_wait = priority.get("flex_max_wait_hours", 168)
            flex_usage_dur = priority.get("flex_usage_duration_hours", 24)
            cal_start = priority.get("calendar_start_time", "")
            cal_end = priority.get("calendar_end_time", "")

            success = await self._scan_with_method(
                method, valid_zones, max_retries, retry_interval, priority_num,
                name_prefix, flex_max_wait, flex_usage_dur, cal_start, cal_end)

            if success:
                self.status = ScanningStatus.SUCCESS
                actual_count = self.result.get("vm_count", self.vm_count) if self.result else self.vm_count
                await self.emit("success",
                    f"✅ Scan successful! Secured {actual_count}x {self.machine_type} via {method_label}.",
                    {"method": method, "priority": priority_num, "result": self.result})
                _schedule_session_cleanup(self.session_id)
                return

            await self.emit("priority_exhausted",
                f"❌ Priority {priority_num} ({method_label}) exhausted. Moving to next.",
                {"priority": priority_num, "method": method})

        self.status = ScanningStatus.FAILED
        await self.emit("failed",
            f"❌ Scan failed. All priorities exhausted for {self.vm_count}x {self.machine_type}.")
        _schedule_session_cleanup(self.session_id)

    async def _run_parallel(self):
        supported_zones = get_zones_for_machine_type(self.machine_type)
        tasks_info = []
        for pi, priority in enumerate(self.priorities):
            method = priority["method"]
            zones = priority.get("zones", [])
            method_label = CONSUMPTION_LABELS.get(method, method)
            name_prefix = priority.get("name_prefix", "")

            if not is_consumption_supported(self.machine_type, method):
                await self.emit("warning", f"⚠️ {method_label} not supported. Skipping.")
                continue
            valid_zones = [z for z in zones if z in supported_zones]
            if not valid_zones:
                await self.emit("warning", f"⚠️ No valid zones for {method_label}. Skipping.")
                continue
            tasks_info.append({
                "method": method, "zones": valid_zones,
                "max_retries": priority.get("max_retries", 5),
                "retry_interval": priority.get("retry_interval", 60),
                "label": method_label, "priority": pi + 1,
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

        await self.emit("info",
            f"⚡ Running {len(tasks_info)} methods in parallel: {', '.join(t['label'] for t in tasks_info)}")
        winner_event = asyncio.Event()
        winner_result = {"method": None}

        async def parallel_scan(task_info):
            method, method_label = task_info["method"], task_info["label"]
            zones, name_prefix = task_info["zones"], task_info["name_prefix"]
            max_retries, retry_interval = task_info["max_retries"], task_info["retry_interval"]

            await self.emit("priority_start",
                f"⚡ [PARALLEL] Starting {method_label} ({len(zones)} zones)",
                {"priority": task_info["priority"], "method": method, "parallel": True})

            for attempt in range(1, max_retries + 1):
                if self.cancelled or winner_event.is_set():
                    return False
                for zone in zones:
                    if self.cancelled or winner_event.is_set():
                        return False
                    await self.emit("attempt",
                        f"🔄 [{method_label}] Attempt {attempt}/{max_retries} — {zone}",
                        {"attempt": attempt, "zone": zone, "method": method})
                    try:
                        await self._refresh_token()
                        success = await self._dispatch_method(
                            method, zone, name_prefix,
                            task_info.get("flex_max_wait_hours", 168),
                            task_info.get("flex_usage_duration_hours", 24),
                            task_info.get("calendar_start_time", ""),
                            task_info.get("calendar_end_time", ""),
                        )
                        if success:
                            if winner_event.is_set():
                                await self.emit("warning",
                                    f"[{method_label}] Created resource in {zone} but another method already won.")
                                return False
                            winner_result["method"] = method_label
                            winner_event.set()
                            return True
                    except Exception as e:
                        await self.emit("error", f"⚠️ [{method_label}] {zone}: {str(e)}")

                if attempt < max_retries and not winner_event.is_set():
                    await self.emit("waiting",
                        f"⏳ [{method_label}] Waiting {retry_interval}s ({attempt}/{max_retries})...")
                    for _ in range(retry_interval):
                        if self.cancelled or winner_event.is_set():
                            return False
                        await asyncio.sleep(1)

            await self.emit("priority_exhausted", f"❌ [{method_label}] All retries exhausted.")
            return False

        results = await asyncio.gather(*[parallel_scan(t) for t in tasks_info], return_exceptions=True)
        any_success = any(r is True for r in results if not isinstance(r, Exception))

        if any_success:
            self.status = ScanningStatus.SUCCESS
            actual_count = self.result.get("vm_count", self.vm_count) if self.result else self.vm_count
            await self.emit("success",
                f"✅ Scan successful! Secured {actual_count}x {self.machine_type} "
                f"via {winner_result['method']} (parallel).",
                {"result": self.result})
        elif self.cancelled:
            self.status = ScanningStatus.CANCELLED
            await self.emit("cancelled", "🛑 Scanning cancelled.")
        else:
            self.status = ScanningStatus.FAILED
            await self.emit("failed", f"❌ All {len(tasks_info)} parallel methods exhausted.")
        _schedule_session_cleanup(self.session_id)

    async def _scan_with_method(self, method, zones, max_retries, retry_interval,
                                 priority_num, name_prefix="",
                                 flex_max_wait_hours=168, flex_usage_duration_hours=24,
                                 calendar_start_time="", calendar_end_time=""):
        method_label = CONSUMPTION_LABELS.get(method, method)
        for attempt in range(1, max_retries + 1):
            if self.cancelled:
                return False
            for zone in zones:
                if self.cancelled:
                    return False
                await self.emit("attempt",
                    f"🔄 [{method_label}] Attempt {attempt}/{max_retries} — zone: {zone}",
                    {"attempt": attempt, "maxRetries": max_retries, "zone": zone, "method": method})
                try:
                    await self._refresh_token()
                    if await self._dispatch_method(method, zone, name_prefix,
                                                    flex_max_wait_hours, flex_usage_duration_hours,
                                                    calendar_start_time, calendar_end_time):
                        return True
                except Exception as e:
                    await self.emit("error",
                        f"⚠️ [{method_label}] Error in {zone}: {str(e)}",
                        {"zone": zone, "error": str(e), "attempt": attempt})
            if attempt < max_retries:
                await self.emit("waiting",
                    f"⏳ Waiting {retry_interval}s before next attempt ({attempt}/{max_retries})...")
                for _ in range(retry_interval):
                    if self.cancelled:
                        return False
                    await asyncio.sleep(1)
        return False

    def _is_tpu_type(self) -> bool:
        """Check if current machine type is a TPU type."""
        from gpu_data import TPU_TYPES
        return any(self.machine_type in t.get("machine_types", {}) for t in TPU_TYPES.values())

    def _get_tpu_version(self) -> str:
        """Get the TPU version (e.g., 'v6e') for the current machine type."""
        from gpu_data import TPU_TYPES
        for tpu_type, tpu_info in TPU_TYPES.items():
            if self.machine_type in tpu_info.get("machine_types", {}):
                return tpu_type
        return ""

    async def _dispatch_method(self, method, zone, name_prefix="",
                                flex_max_wait_hours=168, flex_usage_duration_hours=24,
                                calendar_start_time="", calendar_end_time=""):
        if method == ConsumptionModel.ON_DEMAND:
            if self._is_tpu_type():
                return await self._try_tpu_on_demand(zone, name_prefix)
            return await self._try_on_demand_rest(zone, name_prefix)
        elif method == ConsumptionModel.DWS_CALENDAR:
            if self._is_tpu_type():
                return await self._try_tpu_dws_calendar(zone, name_prefix,
                                                         calendar_start_time, calendar_end_time)
            return await self._try_dws_calendar_rest(zone, name_prefix,
                                                      calendar_start_time, calendar_end_time)
        elif method == ConsumptionModel.DWS_FLEX:
            if self._is_tpu_type():
                return await self._try_tpu_queued_resource(
                    zone, name_prefix, flex_max_wait_hours, flex_usage_duration_hours)
            return await self._try_dws_flex_rest(
                zone, name_prefix, flex_max_wait_hours, flex_usage_duration_hours)
        elif method == ConsumptionModel.SPOT:
            if self._is_tpu_type():
                return await self._try_tpu_spot(zone, name_prefix)
            return await self._try_spot_rest(zone, name_prefix)
        return False

    # ── Resource creation methods ──────────────────────────────────────

    def _make_name(self, prefix: str, method_tag: str, zone: str) -> str:
        """Generate resource name with optional user prefix."""
        short_zone = zone.replace("-", "")
        short_id = self.session_id[:8]
        if prefix:
            return f"{prefix}-{method_tag}-{short_id}-{short_zone}"[:63]
        return f"gpu-radar-{method_tag}-{short_id}-{short_zone}"[:63]

    async def _try_on_demand_rest(self, zone: str, name_prefix: str = "") -> bool:
        """Create on-demand reservation and poll operation to verify."""
        res_name = self._make_name(name_prefix, "od", zone)
        token = await self._get_token()

        await self.emit("action",
            f"📡 Creating on-demand reservation '{res_name}' in {zone}...")

        url = (f"https://compute.googleapis.com/compute/v1/projects/{self.project}"
               f"/zones/{zone}/reservations")
        body = {
            "name": res_name,
            "specificReservation": {
                "count": str(self.vm_count),
                "instanceProperties": {"machineType": self.machine_type}
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
                        self.result = {"method": "on_demand", "reservation_name": res_name,
                                       "zone": zone, "vm_count": self.vm_count}
                        await self.emit("info",
                            f"✅ On-demand reservation verified: {res_name} in {zone} ({self.vm_count} VMs)")
                        return True
                    else:
                        return False
                else:
                    await self.emit("warning",
                        f"⚠️ On-demand failed in {zone}: {self._parse_api_error(data)}")
                    return False
        except httpx.TimeoutException:
            await self.emit("warning", f"⚠️ Timeout in {zone}")
            return False

    async def _try_dws_calendar_rest(self, zone: str, name_prefix: str = "",
                                      calendar_start_time: str = "",
                                      calendar_end_time: str = "") -> bool:
        """Create DWS Calendar future reservation via REST API."""
        res_name = self._make_name(name_prefix, "cal", zone)
        token = await self._get_token()

        # Use per-priority start/end times if provided, otherwise fallback
        if calendar_start_time:
            start_str = _normalize_datetime(calendar_start_time)
        else:
            start_time = datetime.now(timezone.utc) + timedelta(hours=1)
            start_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        if calendar_end_time:
            end_str = _normalize_datetime(calendar_end_time)
        else:
            end_time = datetime.now(timezone.utc) + timedelta(hours=self.dws_calendar_duration_hours + 1)
            end_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        await self.emit("action",
            f"📡 Creating DWS Calendar future reservation '{res_name}' in {zone} "
            f"({start_str} → {end_str})...")

        url = (f"https://compute.googleapis.com/compute/v1/projects/{self.project}"
               f"/zones/{zone}/futureReservations")
        prefix_tag = name_prefix if name_prefix else f"gpu-radar-{self.session_id[:8]}"
        # Calendar mode requires DENSE for all GPU VMs and specificReservationRequired=true
        from gpu_data import MACHINE_TO_FAMILY
        family = MACHINE_TO_FAMILY.get(self.machine_type, "")
        dense_families = ("A4", "A3 Ultra", "A3 Mega", "A3 High", "A3 Edge")
        body = {
            "name": res_name,
            "autoDeleteAutoCreatedReservations": True,
            "specificReservationRequired": True,
            "planningStatus": "SUBMITTED",
            "reservationMode": "CALENDAR",
            "reservationName": f"{prefix_tag}-rsv",
            "namePrefix": prefix_tag,
            "specificSkuProperties": {
                "totalCount": str(self.vm_count),
                "instanceProperties": {"machineType": self.machine_type}
            },
            "timeWindow": {"startTime": start_str, "endTime": end_str},
            "shareSettings": {"shareType": "LOCAL"},
        }
        if family in dense_families:
            body["deploymentType"] = "DENSE"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(url, json=body, headers=headers)
                data = resp.json()
                if resp.status_code in (200, 201):
                    verified = await self._wait_for_operation(data, zone, "DWS Calendar")
                    if verified:
                        # Future reservation submitted, but NOT yet approved/deployed.
                        # Check if the reservation is in APPROVED status by polling.
                        approved = await self._poll_future_reservation_status(
                            zone, res_name, max_polls=60, poll_interval=10)
                        if approved:
                            self.result = {"method": "dws_calendar", "reservation_name": res_name,
                                           "zone": zone, "vm_count": self.vm_count,
                                           "start_time": start_str, "end_time": end_str}
                            await self.emit("info",
                                f"✅ DWS Calendar reservation APPROVED and deployed: {res_name} in {zone}")
                            return True
                        else:
                            await self.emit("info",
                                f"📋 DWS Calendar submitted in {zone}: {res_name}. "
                                f"Pending Google approval — not yet deployed. Continuing to try other options...")
                            return False
                    return False
                else:
                    await self.emit("warning",
                        f"⚠️ DWS Calendar failed in {zone}: {self._parse_api_error(data)}")
                    return False
        except httpx.TimeoutException:
            await self.emit("warning", f"⚠️ Timeout creating DWS Calendar in {zone}")
            return False

    async def _poll_future_reservation_status(self, zone: str, name: str,
                                                max_polls: int = 360,
                                                poll_interval: int = 30) -> bool:
        """Poll a future reservation until APPROVED, REJECTED, or max_polls reached."""
        await self.emit("info",
            f"⏳ Polling future reservation '{name}' "
            f"(every {poll_interval}s, max {max_polls} polls)...")
        poll_num = 0
        while max_polls <= 0 or poll_num < max_polls:
            if self.cancelled:
                return False
            await asyncio.sleep(poll_interval)
            poll_num += 1
            token = await self._get_token()
            url = (f"https://compute.googleapis.com/compute/beta/projects/{self.project}"
                   f"/zones/{zone}/futureReservations/{name}")
            headers = {"Authorization": f"Bearer {token}"}
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        status = data.get("status", {}).get("procurementStatus", "UNKNOWN")
                        if status in ("APPROVED", "PROVISIONING", "FULFILLED"):
                            await self.emit("info",
                                f"✅ Future reservation '{name}' APPROVED! Status: {status}")
                            return True
                        elif status in ("FAILED", "CANCELLED", "DECLINED"):
                            await self.emit("warning",
                                f"⚠️ Future reservation '{name}' REJECTED. Status: {status}")
                            return False
                        else:
                            if poll_num % 6 == 0:
                                mins_elapsed = (poll_num * poll_interval) // 60
                                await self.emit("info",
                                    f"⏳ Future reservation '{name}' status: {status} "
                                    f"(waiting {mins_elapsed} min so far)")
                    elif resp.status_code == 404:
                        await self.emit("warning",
                            f"⚠️ Future reservation '{name}' not found (may have been deleted).")
                        return False
            except Exception as e:
                if poll_num % 6 == 0:
                    await self.emit("info", f"⏳ Poll error: {str(e)[:80]}")

        await self.emit("warning",
            f"⚠️ Future reservation '{name}' not resolved after "
            f"{poll_num * poll_interval}s. Check GCP Console.")
        return False

    def _family_supports_on_demand(self) -> bool:
        """Check if the current machine type's family supports on-demand reservations."""
        from gpu_data import CONSUMPTION_SUPPORT
        family = MACHINE_TO_FAMILY.get(self.machine_type, "")
        return CONSUMPTION_SUPPORT.get("on_demand", {}).get(family, False)

    async def _try_dws_flex_rest(self, zone: str, name_prefix: str = "",
                                  flex_max_wait_hours: int = 168,
                                  flex_usage_duration_hours: int = 24) -> bool:
        """GPU DWS Flex: For families that support on-demand reservations, try a standard
        reservation with auto-delete. For families that don't (A4, A3 Ultra, A4X Max),
        use future reservations which is the proper DWS Flex mechanism."""
        # Families without on-demand support need future reservations for DWS Flex
        if not self._family_supports_on_demand():
            return await self._try_dws_flex_via_future(
                zone, name_prefix, flex_usage_duration_hours=flex_usage_duration_hours)

        res_name = self._make_name(name_prefix, "flex", zone)
        token = await self._get_token()

        end_time = datetime.now(timezone.utc) + timedelta(hours=flex_usage_duration_hours)
        end_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        await self.emit("action",
            f"📡 [DWS Flex] Trying reservation '{res_name}' in {zone} "
            f"(usage: {flex_usage_duration_hours}h)...")

        url = (f"https://compute.googleapis.com/compute/v1/projects/{self.project}"
               f"/zones/{zone}/reservations")
        body = {
            "name": res_name,
            "specificReservation": {
                "count": str(self.vm_count),
                "instanceProperties": {"machineType": self.machine_type}
            },
            "specificReservationRequired": True,
            "deleteAtTime": end_str,
        }
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(url, json=body, headers=headers)
                data = resp.json()
                if resp.status_code in (200, 201):
                    verified = await self._wait_for_operation(data, zone, "DWS Flex")
                    if verified:
                        self.result = {"method": "dws_flex", "reservation_name": res_name,
                                       "zone": zone, "vm_count": self.vm_count}
                        await self.emit("info",
                            f"✅ DWS Flex reservation verified: {res_name} in {zone}")
                        return True
                    return False
                else:
                    err_msg = self._parse_api_error(data)
                    # If standard reservation fails, fall back to future reservation approach
                    if "not supported" in err_msg.lower() or "not available" in err_msg.lower():
                        await self.emit("info",
                            f"📋 Standard reservation not available in {zone}, "
                            f"trying future reservation approach...")
                        return await self._try_dws_flex_via_future(
                            zone, name_prefix, flex_usage_duration_hours=flex_usage_duration_hours)
                    await self.emit("warning",
                        f"⚠️ [DWS Flex] {zone}: {err_msg}")
                    return False
        except httpx.TimeoutException:
            await self.emit("warning", f"⚠️ Timeout creating DWS Flex in {zone}")
            return False

    async def _try_dws_flex_via_future(self, zone: str, name_prefix: str = "",
                                       flex_usage_duration_hours: int = 0) -> bool:
        """Create a future reservation for DWS Flex — the proper mechanism for families
        that don't support on-demand reservations (A4, A3 Ultra, A4X Max)."""
        res_name = self._make_name(name_prefix, "flex-fr", zone)
        token = await self._get_token()

        usage_hours = flex_usage_duration_hours if flex_usage_duration_hours > 0 else self.dws_calendar_duration_hours
        start_time = datetime.now(timezone.utc) + timedelta(minutes=5)
        end_time = start_time + timedelta(hours=usage_hours)
        start_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        await self.emit("action",
            f"📡 Creating future reservation '{res_name}' in {zone} (flex-like, "
            f"{start_str} → {end_str})...")

        url = (f"https://compute.googleapis.com/compute/v1/projects/{self.project}"
               f"/zones/{zone}/futureReservations")
        prefix_tag = name_prefix if name_prefix else f"gpu-radar-{self.session_id[:8]}"
        from gpu_data import MACHINE_TO_FAMILY
        family = MACHINE_TO_FAMILY.get(self.machine_type, "")
        dense_families = ("A4", "A3 Ultra", "A3 Mega", "A3 High", "A3 Edge")
        body = {
            "name": res_name,
            "autoDeleteAutoCreatedReservations": True,
            "specificReservationRequired": True,
            "planningStatus": "SUBMITTED",
            "namePrefix": prefix_tag,
            "specificSkuProperties": {
                "totalCount": str(self.vm_count),
                "instanceProperties": {"machineType": self.machine_type}
            },
            "timeWindow": {"startTime": start_str, "endTime": end_str},
            "shareSettings": {"shareType": "LOCAL"},
        }
        if family in dense_families:
            body["deploymentType"] = "DENSE"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(url, json=body, headers=headers)
                data = resp.json()
                if resp.status_code in (200, 201):
                    verified = await self._wait_for_operation(data, zone, "DWS Flex (future)")
                    if verified:
                        approved = await self._poll_future_reservation_status(
                            zone, res_name, max_polls=60, poll_interval=10)
                        if approved:
                            self.result = {"method": "dws_flex", "reservation_name": res_name,
                                           "zone": zone, "vm_count": self.vm_count,
                                           "start_time": start_str, "end_time": end_str}
                            await self.emit("info",
                                f"✅ DWS Flex (future reservation) APPROVED: {res_name} in {zone}")
                            return True
                        else:
                            await self.emit("info",
                                f"📋 DWS Flex future reservation submitted in {zone}: {res_name}. "
                                "Pending approval — continuing to try other options...")
                            return False
                    return False
                else:
                    await self.emit("warning",
                        f"⚠️ DWS Flex (future) failed in {zone}: {self._parse_api_error(data)}")
                    return False
        except httpx.TimeoutException:
            await self.emit("warning", f"⚠️ Timeout creating DWS Flex future reservation in {zone}")
            return False

    async def _get_network(self, token: str) -> str:
        """Get the first available VPC network for this project."""
        if hasattr(self, '_cached_network'):
            return self._cached_network
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"https://compute.googleapis.com/compute/v1/projects/{self.project}/global/networks",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 200:
                    networks = resp.json().get("items", [])
                    if networks:
                        self._cached_network = networks[0]["selfLink"]
                        return self._cached_network
        except Exception:
            pass
        self._cached_network = f"projects/{self.project}/global/networks/default"
        return self._cached_network

    def _is_accelerator_optimized(self) -> bool:
        """Check if machine type is an accelerator-optimized family (A3/A4/A4X).
        These have GPUs integrated — no guestAccelerators needed, require GVNIC."""
        family = MACHINE_TO_FAMILY.get(self.machine_type, "")
        return family.startswith(("A3", "A4"))

    async def _try_spot_rest(self, zone: str, name_prefix: str = "") -> bool:
        """Create Spot VM(s) and poll operation to verify. Creates vm_count instances
        for accelerator-optimized families, or 1 instance for standard GPU types."""
        token = await self._get_token()
        machine_info = MACHINE_TYPES.get(self.machine_type, {})
        network = await self._get_network(token)
        is_accel_opt = self._is_accelerator_optimized()

        # Accelerator-optimized families (A3/A4) have specific requirements
        spot_count = self.vm_count if is_accel_opt else 1

        created = []
        for i in range(spot_count):
            if self.cancelled:
                return False
            suffix = f"-{i}" if spot_count > 1 else ""
            inst_name = self._make_name(name_prefix, f"spot{suffix}", zone)

            await self.emit("action",
                f"📡 Creating Spot VM '{inst_name}' in {zone}"
                f"{f' ({i+1}/{spot_count})' if spot_count > 1 else ''}...")

            url = (f"https://compute.googleapis.com/compute/v1/projects/{self.project}"
                   f"/zones/{zone}/instances")

            if is_accel_opt:
                # A3/A4 families: GPUs integrated into machine type, need GVNIC,
                # use HPC VM image, no guestAccelerators
                body = {
                    "name": inst_name,
                    "machineType": f"zones/{zone}/machineTypes/{self.machine_type}",
                    "scheduling": {
                        "provisioningModel": "SPOT",
                        "instanceTerminationAction": "STOP",
                        "automaticRestart": False,
                        "onHostMaintenance": "TERMINATE",
                    },
                    "disks": [{"boot": True, "autoDelete": True,
                               "initializeParams": {
                                   "sourceImage": "projects/cloud-hpc-image-public/global/images/family/hpc-rocky-linux-8",
                                   "diskSizeGb": "200",
                                   "diskType": f"zones/{zone}/diskTypes/pd-ssd",
                               }}],
                    "networkInterfaces": [{
                        "network": network,
                        "nicType": "GVNIC",
                        "accessConfigs": [{"type": "ONE_TO_ONE_NAT", "name": "External NAT"}],
                    }],
                }
            else:
                # Standard GPU families (G2, A2): need guestAccelerators
                body = {
                    "name": inst_name,
                    "machineType": f"zones/{zone}/machineTypes/{self.machine_type}",
                    "scheduling": {
                        "provisioningModel": "SPOT",
                        "instanceTerminationAction": "STOP",
                        "automaticRestart": False,
                    },
                    "disks": [{"boot": True, "autoDelete": True,
                               "initializeParams": {
                                   "sourceImage": "projects/debian-cloud/global/images/family/debian-12",
                                   "diskSizeGb": "50",
                               }}],
                    "networkInterfaces": [{
                        "network": network,
                        "accessConfigs": [{"type": "ONE_TO_ONE_NAT", "name": "External NAT"}],
                    }],
                }
                if machine_info.get("accelerator_type"):
                    body["guestAccelerators"] = [{
                        "acceleratorType": f"zones/{zone}/acceleratorTypes/{machine_info['accelerator_type']}",
                        "acceleratorCount": machine_info["gpu_count"],
                    }]
                    body["scheduling"]["onHostMaintenance"] = "TERMINATE"

            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.post(url, json=body, headers=headers)
                    data = resp.json()
                    if resp.status_code in (200, 201):
                        verified = await self._wait_for_operation(data, zone, f"Spot VM {inst_name}")
                        if verified:
                            created.append(inst_name)
                            await self.emit("info",
                                f"✅ Spot VM verified running: {inst_name} in {zone}")
                        else:
                            await self.emit("warning",
                                f"⚠️ Spot VM operation not verified for {inst_name}")
                    else:
                        err_msg = self._parse_api_error(data)
                        await self.emit("warning",
                            f"⚠️ Spot VM failed in {zone}: {err_msg}")
                        # For capacity errors, don't try more instances in same zone
                        if "no capacity" in err_msg.lower() or "stock" in err_msg.lower():
                            return False
            except httpx.TimeoutException:
                await self.emit("warning", f"⚠️ Timeout creating Spot VM in {zone}")

        if created:
            self.result = {"method": "spot", "instance_names": created,
                           "zone": zone, "vm_count": len(created)}
            return True
        return False

    # ── TPU-specific methods ───────────────────────────────────────────

    def _get_tpu_accelerator_type(self, zone: str) -> str:
        """Build the TPU accelerator type string for the TPU API.
        
        For v2/v3: machine type name IS the accelerator type (e.g., v2-8, v3-8)
        For v5e/v5p/v6e: use accelerator_prefix + chip count (e.g., v5litepod-1, v5p-8)
        """
        tpu_version = self._get_tpu_version()
        from gpu_data import TPU_TYPES
        tpu_info = TPU_TYPES.get(tpu_version, {})
        mt_spec = tpu_info.get("machine_types", {}).get(self.machine_type, {})
        
        # For older TPUs (v2, v3), the machine type name IS the accelerator type
        if tpu_version in ("v2", "v3"):
            return self.machine_type  # e.g., "v2-8", "v3-8"
        
        # For newer TPUs, use accelerator_prefix + chip count
        chips = mt_spec.get("chips", 1)
        prefix = tpu_info.get("accelerator_prefix", tpu_version)
        return f"{prefix}-{chips}"

    async def _poll_tpu_operation(self, op_name: str, zone: str, label: str,
                                   max_polls: int = 60, poll_interval: int = 10) -> bool:
        """Poll a TPU operation until done."""
        await self.emit("info", f"⏳ [{label}] Polling TPU operation...")
        for poll_num in range(1, max_polls + 1):
            if self.cancelled:
                return False
            await asyncio.sleep(poll_interval)
            token = await self._get_token()
            url = f"https://tpu.googleapis.com/v2/{op_name}"
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
                            await self.emit("info", f"⏳ [{label}] Still provisioning... (poll {poll_num}/{max_polls})")
            except Exception as e:
                if poll_num % 6 == 0:
                    await self.emit("info", f"⏳ [{label}] Poll error: {str(e)[:80]}")
        await self.emit("warning", f"⚠️ [{label}] TPU operation not confirmed after {max_polls * poll_interval}s.")
        return False

    async def _try_tpu_on_demand(self, zone: str, name_prefix: str = "") -> bool:
        """Create a TPU node using the TPU v2 API (on-demand)."""
        node_name = self._make_name(name_prefix, "tpu-od", zone)
        token = await self._get_token()
        accel_type = self._get_tpu_accelerator_type(zone)

        await self.emit("action",
            f"📡 [TPU] Creating on-demand TPU node '{node_name}' ({accel_type}) in {zone}...")

        url = (f"https://tpu.googleapis.com/v2/projects/{self.project}"
               f"/locations/{zone}/nodes?nodeId={node_name}")
        body = {
            "acceleratorType": accel_type,
            "runtimeVersion": "tpu-vm-tf-2.17.0-pjrt",
        }
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, json=body, headers=headers)
                data = resp.json()
                if resp.status_code in (200, 201):
                    op_name = data.get("name", "")
                    if op_name:
                        ready = await self._poll_tpu_operation(op_name, zone, "TPU On-Demand")
                        if ready:
                            self.result = {"method": "on_demand", "tpu_node": node_name,
                                           "zone": zone, "accelerator_type": accel_type}
                            await self.emit("info",
                                f"✅ TPU node READY: {node_name} ({accel_type}) in {zone}")
                            return True
                        return False
                    else:
                        await self.emit("warning",
                            f"⚠️ TPU On-Demand: No operation returned. Cannot verify deployment.")
                        return False
                else:
                    err_msg = data.get("error", {}).get("message", str(data)[:200])
                    await self.emit("warning",
                        f"⚠️ TPU On-Demand failed in {zone}: {err_msg}")
                    return False
        except httpx.TimeoutException:
            await self.emit("warning", f"⚠️ Timeout creating TPU node in {zone}")
            return False

    async def _poll_tpu_queued_resource(self, zone: str, qr_name: str, label: str,
                                         max_polls: int = 120, poll_interval: int = 10) -> bool:
        """Poll a TPU Queued Resource until it's ACTIVE (truly provisioned)."""
        await self.emit("info",
            f"⏳ [{label}] Polling queued resource '{qr_name}' until ACTIVE...")
        for poll_num in range(1, max_polls + 1):
            if self.cancelled:
                return False
            await asyncio.sleep(poll_interval)
            token = await self._get_token()
            url = (f"https://tpu.googleapis.com/v2/projects/{self.project}"
                   f"/locations/{zone}/queuedResources/{qr_name}")
            headers = {"Authorization": f"Bearer {token}"}
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(url, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        state = data.get("state", {}).get("state", "UNKNOWN")
                        if state == "ACTIVE":
                            await self.emit("info",
                                f"✅ [{label}] Queued resource '{qr_name}' is ACTIVE — TPU deployed!")
                            return True
                        elif state in ("FAILED", "SUSPENDED", "DELETING"):
                            info_str = data.get("state", {}).get("stateInitiator", "")
                            await self.emit("warning",
                                f"⚠️ [{label}] Queued resource '{qr_name}' state: {state} ({info_str})")
                            return False
                        else:
                            if poll_num % 6 == 0:
                                await self.emit("info",
                                    f"⏳ [{label}] Queued resource state: {state} "
                                    f"(poll {poll_num}/{max_polls})")
            except Exception as e:
                if poll_num % 6 == 0:
                    await self.emit("info", f"⏳ [{label}] Poll error: {str(e)[:80]}")
        await self.emit("info",
            f"⏳ [{label}] Queued resource '{qr_name}' not ACTIVE after {max_polls * poll_interval}s. "
            "Continuing to try other options...")
        return False

    async def _try_tpu_queued_resource(self, zone: str, name_prefix: str = "",
                                        flex_max_wait_hours: int = 168,
                                        flex_usage_duration_hours: int = 24) -> bool:
        """Create a TPU Queued Resource (DWS Flex equivalent for TPU)."""
        qr_name = self._make_name(name_prefix, "tpu-qr", zone)
        token = await self._get_token()
        accel_type = self._get_tpu_accelerator_type(zone)

        wait_secs = flex_max_wait_hours * 3600
        await self.emit("action",
            f"📡 [TPU] Creating Queued Resource '{qr_name}' ({accel_type}) in {zone} "
            f"(DWS Flex, max wait: {flex_max_wait_hours}h, usage: {flex_usage_duration_hours}h)...")

        url = (f"https://tpu.googleapis.com/v2/projects/{self.project}"
               f"/locations/{zone}/queuedResources?queuedResourceId={qr_name}")
        body = {
            "tpu": {
                "nodeSpec": [{
                    "parent": f"projects/{self.project}/locations/{zone}",
                    "node": {
                        "acceleratorType": accel_type,
                        "runtimeVersion": "tpu-vm-tf-2.17.0-pjrt",
                    },
                    "nodeId": f"{qr_name}-node",
                }]
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
                    # Poll for ACTIVE state
                    ready = await self._poll_tpu_queued_resource(
                        zone, qr_name, "TPU Flex")
                    if ready:
                        self.result = {"method": "dws_flex", "queued_resource": qr_name,
                                       "zone": zone, "accelerator_type": accel_type}
                        await self.emit("info",
                            f"✅ TPU Queued Resource ACTIVE: {qr_name} ({accel_type}) in {zone}")
                        return True
                    else:
                        await self.emit("info",
                            f"📋 TPU Queued Resource submitted in {zone}: {qr_name}. "
                            "Not yet active — continuing to try other options...")
                        return False
                else:
                    err_msg = data.get("error", {}).get("message", str(data)[:200])
                    await self.emit("warning",
                        f"⚠️ TPU Queued Resource failed in {zone}: {err_msg}")
                    return False
        except httpx.TimeoutException:
            await self.emit("warning", f"⚠️ Timeout creating TPU Queued Resource in {zone}")
            return False

    async def _try_tpu_dws_calendar(self, zone: str, name_prefix: str = "",
                                     calendar_start_time: str = "",
                                     calendar_end_time: str = "") -> bool:
        """Create a TPU Queued Resource with guaranteed scheduling (DWS Calendar)."""
        qr_name = self._make_name(name_prefix, "tpu-cal", zone)
        token = await self._get_token()
        accel_type = self._get_tpu_accelerator_type(zone)

        if calendar_start_time:
            start_str = _normalize_datetime(calendar_start_time)
        else:
            start_time = datetime.now(timezone.utc) + timedelta(hours=1)
            start_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        if calendar_end_time:
            end_str = _normalize_datetime(calendar_end_time)
        else:
            end_time = datetime.now(timezone.utc) + timedelta(hours=self.dws_calendar_duration_hours + 1)
            end_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        await self.emit("action",
            f"📡 [TPU] Creating Calendar Queued Resource '{qr_name}' ({accel_type}) in {zone} "
            f"({start_str} → {end_str})...")

        url = (f"https://tpu.googleapis.com/v2/projects/{self.project}"
               f"/locations/{zone}/queuedResources?queuedResourceId={qr_name}")
        body = {
            "tpu": {
                "nodeSpec": [{
                    "parent": f"projects/{self.project}/locations/{zone}",
                    "node": {
                        "acceleratorType": accel_type,
                        "runtimeVersion": "tpu-vm-tf-2.17.0-pjrt",
                    },
                    "nodeId": f"{qr_name}-node",
                }]
            },
            "queueingPolicy": {
                "validUntilTime": end_str,
            },
            "guaranteed": {
                "reserved": True,
            },
        }
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, json=body, headers=headers)
                data = resp.json()
                if resp.status_code in (200, 201):
                    # Poll for ACTIVE state
                    ready = await self._poll_tpu_queued_resource(
                        zone, qr_name, "TPU Calendar")
                    if ready:
                        self.result = {"method": "dws_calendar", "queued_resource": qr_name,
                                       "zone": zone, "accelerator_type": accel_type,
                                       "start_time": start_str, "end_time": end_str}
                        await self.emit("info",
                            f"✅ TPU Calendar resource ACTIVE: {qr_name} ({accel_type}) in {zone}")
                        return True
                    else:
                        await self.emit("info",
                            f"📋 TPU Calendar submitted in {zone}: {qr_name}. "
                            "Pending — not yet deployed. Continuing to try other options...")
                        return False
                else:
                    err_msg = data.get("error", {}).get("message", str(data)[:200])
                    await self.emit("warning",
                        f"⚠️ TPU Calendar failed in {zone}: {err_msg}")
                    return False
        except httpx.TimeoutException:
            await self.emit("warning", f"⚠️ Timeout creating TPU Calendar resource in {zone}")
            return False

    async def _try_tpu_spot(self, zone: str, name_prefix: str = "") -> bool:
        """Create a Spot TPU Queued Resource."""
        qr_name = self._make_name(name_prefix, "tpu-spot", zone)
        token = await self._get_token()
        accel_type = self._get_tpu_accelerator_type(zone)

        await self.emit("action",
            f"📡 [TPU] Creating Spot TPU '{qr_name}' ({accel_type}) in {zone}...")

        url = (f"https://tpu.googleapis.com/v2/projects/{self.project}"
               f"/locations/{zone}/queuedResources?queuedResourceId={qr_name}")
        body = {
            "tpu": {
                "nodeSpec": [{
                    "parent": f"projects/{self.project}/locations/{zone}",
                    "node": {
                        "acceleratorType": accel_type,
                        "runtimeVersion": "tpu-vm-tf-2.17.0-pjrt",
                    },
                    "nodeId": f"{qr_name}-node",
                }]
            },
            "spot": {},
        }
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, json=body, headers=headers)
                data = resp.json()
                if resp.status_code in (200, 201):
                    # Poll for ACTIVE state
                    ready = await self._poll_tpu_queued_resource(
                        zone, qr_name, "TPU Spot")
                    if ready:
                        self.result = {"method": "spot", "queued_resource": qr_name,
                                       "zone": zone, "accelerator_type": accel_type}
                        await self.emit("info",
                            f"✅ Spot TPU ACTIVE: {qr_name} ({accel_type}) in {zone}")
                        return True
                    else:
                        await self.emit("info",
                            f"📋 Spot TPU submitted in {zone}: {qr_name}. "
                            "Not yet active — continuing to try other options...")
                        return False
                else:
                    err_msg = data.get("error", {}).get("message", str(data)[:200])
                    await self.emit("warning",
                        f"⚠️ Spot TPU failed in {zone}: {err_msg}")
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


def create_session(project, machine_type, vm_count, priorities, send_update,
                   dws_calendar_duration_hours=24) -> ScanningSession:
    session_id = str(uuid.uuid4())
    session = ScanningSession(
        session_id=session_id, project=project, machine_type=machine_type,
        vm_count=vm_count, priorities=priorities, send_update=send_update,
        dws_calendar_duration_hours=dws_calendar_duration_hours,
    )
    active_sessions[session_id] = session
    return session


def cancel_session(session_id: str) -> bool:
    session = active_sessions.get(session_id)
    if session:
        session.cancel()
        return True
    return False


def get_session(session_id: str) -> Optional[ScanningSession]:
    return active_sessions.get(session_id)
