"""
Advisory API handlers for DWS Calendar Mode, Spot VM, and DWS Flex Start Advisory.
Uses REST APIs (with gcloud fallback) to query capacity recommendations.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def _get_adc_token() -> str:
    """Get access token using Application Default Credentials."""
    import os
    if os.environ.get("AUTH_MODE", "local").lower() == "user":
        raise RuntimeError(
            "This server runs in bring-your-own-credentials mode and never uses "
            "server-side credentials. Provide your own access token "
            "(gcloud auth print-access-token) in the Authentication panel."
        )
    import google.auth
    import google.auth.transport.requests

    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


async def get_gcloud_access_token() -> str:
    """Get access token using ADC (runs in thread to avoid blocking)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_adc_token)


def _compute_time_window(
    start_date: str,
    flexibility_days: int,
    duration_days: int,
    min_ahead_hours: int = 1,
) -> tuple[str, str]:
    """Compute API time window from user inputs, respecting family min_ahead_hours.
    Returns (start_str, end_str) as ISO 8601 UTC strings.
    """
    now_utc = datetime.now(timezone.utc)
    # Add 2 hours buffer beyond min_ahead_hours so request latency never trips validation
    earliest_valid = (now_utc + timedelta(hours=max(1, min_ahead_hours) + 2)).replace(
        minute=0, second=0, microsecond=0
    )

    if start_date:
        try:
            base = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            base = earliest_valid
    else:
        base = earliest_valid

    if base < earliest_valid:
        base = earliest_valid

    start_str = base.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_date = base + timedelta(days=max(0, flexibility_days), hours=23, minutes=59, seconds=59)
    end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    return start_str, end_str


def _resolve_regions_zones(regions, zones):
    """Derive target regions and allowed zones from user input."""
    target_regions = set()
    allowed_zones = set(zones) if zones else set()
    if zones:
        for z in zones:
            region = z.rsplit("-", 1)[0]
            target_regions.add(region)
    if regions:
        target_regions.update(regions)
    return target_regions, allowed_zones


def _get_tpu_info(machine_type: str) -> dict | None:
    """Get TPU info if machine_type is a TPU type, else None."""
    from gpu_data import TPU_TYPES
    for tpu_gen, tpu_info in TPU_TYPES.items():
        if machine_type in tpu_info.get("machine_types", {}):
            mt_spec = tpu_info["machine_types"][machine_type]
            return {
                "gen": tpu_gen,
                "info": tpu_info,
                "chips": mt_spec.get("chips", 1),
                "accelerator_prefix": tpu_info.get("accelerator_prefix", tpu_gen),
                "zones": tpu_info.get("zones", []),
                "specs": mt_spec,
            }
    return None


def _build_tpu_info_payload(machine_type: str) -> dict | None:
    """Build the frontend tpuInfo metadata object for a TPU machine type."""
    tpu = _get_tpu_info(machine_type)
    if not tpu:
        return None
    tpu_gen = tpu["gen"]
    tpu_info = tpu["info"]
    zones_list = tpu_info.get("zones", [])
    return {
        "type": tpu_gen,
        "name": tpu_info.get("gpu", f"Cloud TPU {tpu_gen}"),
        "machineType": machine_type,
        "zones": zones_list,
        "regions": sorted(set(z.rsplit("-", 1)[0] for z in zones_list)),
        "topologies": tpu_info.get("topologies", []),
        "supported": tpu_info.get("supported", {}),
        "specs": tpu["specs"],
    }


def _normalize_calendar_count(machine_type: str, vm_count: int, cal_cfg: dict) -> int:
    """Normalize VM count (for GPU) or returns valid VM count for TPU slice constraints."""
    if cal_cfg.get("category") == "TPU":
        chips_per_vm = cal_cfg.get("chips_per_vm", 1)
        allowed = cal_cfg.get("allowed_accelerator_counts", [1, 4, 8, 16, 32, 64, 128, 256])
        desired_chips = max(1, vm_count) * chips_per_vm
        # Pick the closest allowed accelerator count that is >= chips_per_vm
        valid_counts = [c for c in allowed if c >= chips_per_vm and c % chips_per_vm == 0]
        if not valid_counts:
            valid_counts = allowed
        best_chips = min(valid_counts, key=lambda c: abs(c - desired_chips))
        return max(1, best_chips // chips_per_vm)
    else:
        min_vms = cal_cfg.get("min_vm_count", 1)
        max_vms = cal_cfg.get("max_vm_count", 128)
        step = cal_cfg.get("vm_count_step", 1)
        count = max(min_vms, min(max_vms, vm_count))
        if step > 1 and count % step != 0:
            count = max(min_vms, ((count + step - 1) // step) * step)
            count = min(max_vms, count)
        return count


async def get_calendar_advisory(
    project: str,
    machine_type: str,
    vm_count: int = 1,
    start_date: str = "",
    flexibility_days: int = 0,
    duration_days: int = 7,
    regions: list[str] | None = None,
    zones: list[str] | None = None,
    user_token: str | None = None,
) -> dict:
    """
    Query DWS Calendar Mode Advisory API for both supported GPUs (A4X, A4, A3 Ultra/Mega/High)
    and supported TPUs (v6e, v5p, v5e).
    """
    from gpu_data import (
        get_calendar_config_for_machine_type,
        get_calendar_zones_for_machine_type,
        get_zones_for_machine_type,
    )

    results = {"recommendations": [], "errors": []}
    tpu_payload = _build_tpu_info_payload(machine_type)
    if tpu_payload:
        results["tpuInfo"] = tpu_payload

    cal_cfg = get_calendar_config_for_machine_type(machine_type)
    if not cal_cfg:
        if tpu_payload:
            supported = tpu_payload.get("supported", {})
            zones_list = tpu_payload.get("zones", [])
            results["message"] = (
                f"DWS Calendar Mode is not supported for {tpu_payload['name']} ({machine_type}). "
                f"Supported consumption models: "
                f"{', '.join(k for k, v in [('On-Demand', supported.get('on_demand')), ('Spot', supported.get('spot')), ('DWS Flex', supported.get('dws_flex'))] if v)}. "
                f"Available in {len(zones_list)} zone(s)."
            )
        else:
            results["message"] = (
                f"DWS Calendar Mode is not supported for {machine_type}. "
                "Calendar Mode supports A4X, A4, A3 Ultra, A3 Mega, A3 High, TPU v6e, TPU v5p, and TPU v5e."
            )
        return results

    min_ahead_hours = cal_cfg.get("min_ahead_hours", 1)
    min_dur_days = max(cal_cfg.get("min_duration_days", 1), duration_days)
    max_dur_days = min(cal_cfg.get("max_duration_days", 90), max(min_dur_days, duration_days))
    eff_vm_count = _normalize_calendar_count(machine_type, vm_count, cal_cfg)

    start_str, end_str = _compute_time_window(
        start_date, flexibility_days, max_dur_days, min_ahead_hours=min_ahead_hours
    )

    cal_zones = set(get_calendar_zones_for_machine_type(machine_type))
    target_regions, allowed_zones = _resolve_regions_zones(regions, zones)

    # Filter to calendar-supported zones/regions when available
    if allowed_zones and cal_zones:
        allowed_zones_cal = allowed_zones & cal_zones
        if allowed_zones_cal:
            allowed_zones = allowed_zones_cal
            target_regions = set(z.rsplit("-", 1)[0] for z in allowed_zones)

    if not target_regions:
        auto_zones = list(cal_zones) if cal_zones else get_zones_for_machine_type(machine_type)
        if auto_zones:
            target_regions = set(z.rsplit("-", 1)[0] for z in auto_zones)
        else:
            results["errors"].append("No regions or zones specified for calendar advisory.")
            return results
    elif cal_zones and not zones and not regions:
        target_regions = set(z.rsplit("-", 1)[0] for z in cal_zones)

    if tpu_payload:
        total_chips = eff_vm_count * cal_cfg.get("chips_per_vm", 1)
        results["message"] = (
            f"Querying DWS Calendar Advisory for {tpu_payload['name']} "
            f"({total_chips} chips / {eff_vm_count}x {machine_type}) across {len(target_regions)} region(s)."
        )

    token = user_token or await get_gcloud_access_token()

    tasks = []
    for region in sorted(target_regions):
        tasks.append(_query_calendar_advisory_region(
            token, project, region, machine_type, eff_vm_count,
            start_str, end_str, min_dur_days, max_dur_days
        ))

    region_results = await asyncio.gather(*tasks, return_exceptions=True)

    for region, result in zip(sorted(target_regions), region_results):
        if isinstance(result, Exception):
            results["errors"].append(f"{region}: {str(result)}")
        elif result:
            for rec in result:
                zone = rec.get("zone", "")
                if not allowed_zones or zone in allowed_zones:
                    results["recommendations"].append(rec)

    return results


async def find_best_splits(
    project: str,
    machine_type: str,
    vm_count: int = 1,
    start_date: str = "",
    flexibility_days: int = 0,
    duration_days: int = 7,
    regions: list[str] | None = None,
    zones: list[str] | None = None,
    user_token: str | None = None,
) -> dict:
    """
    Query Calendar Advisory at multiple VM counts to find capacity splits.
    Supports both GPU and TPU Calendar Mode families.
    """
    from gpu_data import (
        get_calendar_config_for_machine_type,
        get_calendar_zones_for_machine_type,
        get_zones_for_machine_type,
    )

    results = {"splits": [], "fullAvailability": [], "errors": [], "summary": ""}
    tpu_payload = _build_tpu_info_payload(machine_type)
    if tpu_payload:
        results["tpuInfo"] = tpu_payload

    cal_cfg = get_calendar_config_for_machine_type(machine_type)
    if not cal_cfg:
        msg = (
            f"DWS Calendar Mode is not supported for {machine_type}. "
            "Calendar Mode supports A4X, A4, A3 Ultra, A3 Mega, A3 High, TPU v6e, TPU v5p, and TPU v5e."
        )
        results["message"] = msg
        results["summary"] = msg
        return results

    min_ahead_hours = cal_cfg.get("min_ahead_hours", 1)
    min_dur_days = cal_cfg.get("min_duration_days", 1)
    max_dur_days = min(cal_cfg.get("max_duration_days", 90), max(min_dur_days, duration_days))

    start_str, end_str = _compute_time_window(
        start_date, flexibility_days, max_dur_days, min_ahead_hours=min_ahead_hours
    )

    cal_zones = set(get_calendar_zones_for_machine_type(machine_type))
    target_regions, allowed_zones = _resolve_regions_zones(regions, zones)
    if allowed_zones and cal_zones:
        allowed_zones_cal = allowed_zones & cal_zones
        if allowed_zones_cal:
            allowed_zones = allowed_zones_cal
            target_regions = set(z.rsplit("-", 1)[0] for z in allowed_zones)

    if not target_regions:
        auto_zones = list(cal_zones) if cal_zones else get_zones_for_machine_type(machine_type)
        if auto_zones:
            target_regions = set(z.rsplit("-", 1)[0] for z in auto_zones)
        else:
            results["errors"].append("No regions or zones specified.")
            return results

    token = user_token or await get_gcloud_access_token()

    # Build valid VM count levels to query: 100%, 75%, 50%, 25%, and minimum valid unit
    levels = []
    seen = set()
    for pct in [100, 75, 50, 25]:
        raw_count = max(1, int(vm_count * pct / 100))
        norm_count = _normalize_calendar_count(machine_type, raw_count, cal_cfg)
        if norm_count not in seen:
            seen.add(norm_count)
            eff_pct = max(1, round(100 * norm_count / max(1, vm_count)))
            levels.append((norm_count, eff_pct))

    min_unit = _normalize_calendar_count(machine_type, 1, cal_cfg)
    if min_unit not in seen and vm_count > min_unit:
        levels.append((min_unit, max(1, round(100 * min_unit / vm_count))))

    all_tasks = []
    task_meta = []
    for count, pct in levels:
        for region in sorted(target_regions):
            all_tasks.append(_query_calendar_advisory_region(
                token, project, region, machine_type, count,
                start_str, end_str, min_dur_days, max_dur_days
            ))
            task_meta.append((count, pct, region))

    all_results = await asyncio.gather(*all_tasks, return_exceptions=True)

    level_recs = {}
    for (count, pct, region), result in zip(task_meta, all_results):
        if count not in level_recs:
            level_recs[count] = {"vmCount": count, "percentOfRequested": pct, "recommendations": []}
        if isinstance(result, Exception):
            results["errors"].append(f"{region} ({count} VMs): {str(result)}")
        elif result:
            for rec in result:
                zone = rec.get("zone", "")
                if not allowed_zones or zone in allowed_zones:
                    level_recs[count]["recommendations"].append(rec)

    for count, _pct in levels:
        if count in level_recs:
            results["splits"].append(level_recs[count])

    top_count = levels[0][0] if levels else vm_count
    if top_count in level_recs:
        results["fullAvailability"] = [
            r for r in level_recs[top_count]["recommendations"]
            if r.get("status") == "RECOMMENDED"
        ]

    summary_parts = []
    for split in results["splits"]:
        recommended = [r for r in split["recommendations"] if r.get("status") == "RECOMMENDED"]
        zones_available = len(set(r.get("zone") for r in recommended))
        if zones_available > 0:
            summary_parts.append(
                f"{split['vmCount']} VMs ({split['percentOfRequested']}%): "
                f"available in {zones_available} zone(s)"
            )
    if summary_parts:
        results["summary"] = " | ".join(summary_parts)
    else:
        results["summary"] = f"No availability found for {machine_type} in the specified time window."

    return results


async def _query_calendar_advisory_region(
    token: str, project: str, region: str,
    machine_type: str, vm_count: int,
    start_time: str, end_time: str,
    duration_min_days: int = 1, duration_max_days: int = 7,
) -> list[dict]:
    """Query calendar advisory for a single region using REST API."""
    import httpx
    from gpu_data import get_calendar_config_for_machine_type

    url = (
        f"https://compute.googleapis.com/compute/v1/projects/{project}"
        f"/regions/{region}/advice/calendarMode"
    )

    cal_cfg = get_calendar_config_for_machine_type(machine_type)
    if not cal_cfg:
        return []

    eff_min_days = max(cal_cfg.get("min_duration_days", 1), duration_min_days)
    eff_max_days = max(eff_min_days, duration_max_days)
    min_duration_secs = eff_min_days * 86400
    max_duration_secs = eff_max_days * 86400

    eff_vm_count = _normalize_calendar_count(machine_type, vm_count, cal_cfg)

    if cal_cfg.get("category") == "TPU":
        chips_per_vm = cal_cfg.get("chips_per_vm", 1)
        total_chips = eff_vm_count * chips_per_vm
        agg_res = {
            "vmFamily": cal_cfg["vm_family"],
            "acceleratorCount": total_chips,
        }
        if cal_cfg.get("requires_workload_type"):
            agg_res["workloadType"] = "SERVING" if total_chips <= 8 else "BATCH"
        elif cal_cfg.get("default_workload_type"):
            agg_res["workloadType"] = cal_cfg["default_workload_type"]

        target_resources = {"aggregateResources": agg_res}
        spec_body = {
            "targetResources": target_resources,
            "timeRangeSpec": {
                "minDuration": f"{min_duration_secs}s",
                "maxDuration": f"{max_duration_secs}s",
                "startTimeNotEarlierThan": start_time,
                "startTimeNotLaterThan": end_time,
            },
        }
    else:
        target_resources = {
            "specificSkuResources": {
                "instanceCount": str(eff_vm_count),
                "machineType": machine_type,
            }
        }
        spec_body = {
            "targetResources": target_resources,
            "timeRangeSpec": {
                "minDuration": f"{min_duration_secs}s",
                "maxDuration": f"{max_duration_secs}s",
                "startTimeNotEarlierThan": start_time,
                "startTimeNotLaterThan": end_time,
            },
            "deploymentType": cal_cfg.get("deployment_type", "DENSE"),
        }

    body = {
        "futureResourcesSpecs": {
            "spec": spec_body,
        }
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    recommendations = []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=body, headers=headers)

            if resp.status_code == 200:
                data = resp.json()
                for rec_group in data.get("recommendations", []):
                    rps = rec_group.get("recommendationsPerSpec", {})
                    for _spec_key, spec in rps.items():
                        rec_type = spec.get("recommendationType", "")

                        location = spec.get("location", "")
                        if location:
                            zone = location.replace("zones/", "")
                            recommendations.append({
                                "region": region,
                                "zone": zone,
                                "machineType": machine_type,
                                "vmCount": eff_vm_count,
                                "status": "RECOMMENDED",
                                "startTime": spec.get("startTime", start_time),
                                "endTime": spec.get("endTime", end_time),
                                "confidence": "HIGH",
                                "source": "DWS Calendar Advisory",
                                "recommendationType": rec_type,
                            })

                        for loc_key, loc_data in spec.get("otherLocations", {}).items():
                            zone = loc_key.replace("zones/", "")
                            status = loc_data.get("status", "UNKNOWN")
                            details = loc_data.get("details", "")
                            if status == "RECOMMENDED":
                                confidence = "MODERATE"
                            elif status == "NO_CAPACITY":
                                confidence = "NONE"
                            else:
                                confidence = "LOW"
                            recommendations.append({
                                "region": region,
                                "zone": zone,
                                "machineType": machine_type,
                                "vmCount": eff_vm_count,
                                "status": status,
                                "details": details,
                                "startTime": start_time,
                                "endTime": end_time,
                                "confidence": confidence,
                                "source": "DWS Calendar Advisory",
                                "recommendationType": rec_type,
                            })

                if not data.get("recommendations"):
                    recommendations.append({
                        "region": region,
                        "zone": "N/A",
                        "machineType": machine_type,
                        "vmCount": eff_vm_count,
                        "status": "NO_DATA",
                        "rawResponse": data,
                        "source": "DWS Calendar Advisory",
                    })
            elif resp.status_code == 404:
                return await _calendar_advisory_gcloud_fallback(
                    project, region, machine_type, eff_vm_count, start_time, end_time
                )
            else:
                error_msg = resp.text
                try:
                    error_data = resp.json()
                    error_msg = error_data.get("error", {}).get("message", resp.text)
                except Exception:
                    pass
                raise RuntimeError(
                    f"Calendar Advisory API returned {resp.status_code}: {error_msg}"
                )
    except httpx.TimeoutException:
        raise RuntimeError(f"Timeout querying calendar advisory for {region}")
    except httpx.ConnectError:
        raise RuntimeError(f"Connection error querying calendar advisory for {region}")

    return recommendations


async def _calendar_advisory_gcloud_fallback(
    project: str, region: str, machine_type: str,
    vm_count: int, start_time: str, end_time: str,
) -> list[dict]:
    """Fallback to gcloud CLI for calendar advisory."""
    import os
    import shutil
    gcloud_bin = shutil.which("gcloud") or (
        "/google/data/ro/teams/cloud-sdk/gcloud"
        if os.path.exists("/google/data/ro/teams/cloud-sdk/gcloud")
        else "gcloud"
    )
    cmd = [
        gcloud_bin, "beta", "compute", "advice", "calendar-mode",
        f"--project={project}",
        f"--region={region}",
        f"--machine-type={machine_type}",
        f"--vm-count={vm_count}",
        f"--start-time={start_time}",
        f"--end-time={end_time}",
        "--format=json",
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        error = stderr.decode().strip()
        raise RuntimeError(f"gcloud calendar advisory failed: {error}")

    try:
        data = json.loads(stdout.decode())
        recommendations = []
        if isinstance(data, list):
            for item in data:
                recommendations.append({
                    "region": region,
                    "zone": item.get("zone", "N/A"),
                    "machineType": machine_type,
                    "vmCount": vm_count,
                    "availableCount": item.get("vmCount", item.get("count", 0)),
                    "startTime": item.get("startTime", start_time),
                    "endTime": item.get("endTime", end_time),
                    "confidence": item.get("confidence", "UNKNOWN"),
                    "source": "DWS Calendar Advisory (gcloud)",
                })
        return recommendations
    except json.JSONDecodeError:
        return []


async def get_spot_advisory(
    project: str,
    machine_type: str,
    regions: list[str] | None = None,
    zones: list[str] | None = None,
    user_token: str | None = None,
) -> dict:
    """
    Query Spot VM Advisory API (Preview).
    Returns spot availability and preemption risk info.
    """
    results = {"recommendations": [], "errors": []}

    # TPU machine types are not supported by the GCE Spot Advisory API
    tpu_payload = _build_tpu_info_payload(machine_type)
    if tpu_payload:
        results["tpuInfo"] = tpu_payload
        zones_list = tpu_payload["zones"]
        supported = tpu_payload["supported"]
        for z in zones_list:
            if zones and z not in zones:
                continue
            r = z.rsplit("-", 1)[0]
            if regions and r not in regions:
                continue
            results["recommendations"].append({
                "region": r,
                "zone": z,
                "machineType": machine_type,
                "spotAvailability": "SUPPORTED" if supported.get("spot") else "NOT_SUPPORTED",
                "preemptionRate": "UNKNOWN",
                "source": "TPU Zone Data (GCE Spot Advisory API not applicable to Cloud TPU)",
            })
        results["message"] = (
            f"The GCE Spot Advisory API applies only to GCE GPU VMs. "
            f"Showing supported Cloud TPU zones for {tpu_payload['name']}. "
            f"Spot TPUs {'are' if supported.get('spot') else 'are NOT'} supported via Queued Resources."
        )
        return results

    target_regions, allowed_zones = _resolve_regions_zones(regions, zones)
    if not target_regions:
        from gpu_data import get_zones_for_machine_type
        auto_zones = get_zones_for_machine_type(machine_type)
        if auto_zones:
            target_regions = set(z.rsplit("-", 1)[0] for z in auto_zones)
        else:
            results["errors"].append("No regions or zones specified for spot advisory.")
            return results

    token = user_token or await get_gcloud_access_token()

    tasks = []
    for region in sorted(target_regions):
        tasks.append(_query_spot_advisory_region(
            token, project, region, machine_type
        ))

    region_results = await asyncio.gather(*tasks, return_exceptions=True)

    for region, result in zip(sorted(target_regions), region_results):
        if isinstance(result, Exception):
            results["errors"].append(f"{region}: {str(result)}")
        elif result:
            for rec in result:
                zone = rec.get("zone", "")
                if not allowed_zones or zone in allowed_zones:
                    results["recommendations"].append(rec)

    return results


async def _query_spot_advisory_region(
    token: str, project: str, region: str, machine_type: str
) -> list[dict]:
    """Query spot advisory using the public Capacity Advisory API (beta).
    Endpoint: POST .../compute/beta/projects/{project}/regions/{region}/advice/capacity
    """
    import httpx
    from gpu_data import MACHINE_TYPES

    # Use /compute/beta/ rather than /compute/alpha/ (which requires project-level
    # Alpha Access allow-listing and returns HTTP 403 on standard GCP projects)
    # or /compute/v1/ (which currently rejects SPOT provisioningModel).
    url = (
        f"https://compute.googleapis.com/compute/beta/projects/{project}"
        f"/regions/{region}/advice/capacity"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    instance_props = {
        "scheduling": {
            "provisioningModel": "SPOT",
        }
    }
    selection_spec: dict = {
        "machineTypes": [machine_type],
    }
    # IMPORTANT: Only attach guestAccelerators for true guest-attached GPU families (N1 / T4),
    # and place it on InstanceSelection (not InstanceProperties, where GCE ignores it).
    # Built-in GPU families (G2, G4, A2, A3, A4, A4X) fail validation if guestAccelerators is set.
    machine_info = MACHINE_TYPES.get(machine_type, {})
    if machine_info.get("guest_attached_gpu") and machine_info.get("accelerator_type"):
        gpu_count = machine_info.get("gpu_count", 1)
        selection_spec["guestAccelerators"] = [{
            "acceleratorType": machine_info["accelerator_type"],
            "acceleratorCount": gpu_count,
        }]

    body = {
        "distributionPolicy": {"targetShape": "ANY_SINGLE_ZONE"},
        "instanceFlexibilityPolicy": {
            "instanceSelections": {
                "instance-selection-1": selection_spec,
            }
        },
        "instanceProperties": instance_props,
        "size": 1,
    }

    recommendations = []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=body, headers=headers)

            if resp.status_code == 200:
                data = resp.json()
                for rec in data.get("recommendations", []):
                    scores = rec.get("scores", {})
                    obtainability = scores.get("obtainability", 0)
                    raw_uptime_score = scores.get("uptimeScore")
                    estimated_uptime = scores.get("estimatedUptime", "unknown")
                    uptime_secs = (
                        _parse_duration_seconds(estimated_uptime)
                        if estimated_uptime != "unknown"
                        else None
                    )

                    if obtainability >= 0.8:
                        availability = "HIGH"
                    elif obtainability >= 0.5:
                        availability = "MODERATE"
                    elif obtainability >= 0.2:
                        availability = "LOW"
                    else:
                        availability = "VERY_LOW"

                    # The public /compute/beta/ endpoint returns estimatedUptime
                    # (e.g. "3600s", "600s", "60s") and omits alpha-only uptimeScore.
                    if raw_uptime_score is not None:
                        uptime_score = raw_uptime_score
                        if uptime_score >= 0.8:
                            preemption = "LOW"
                        elif uptime_score >= 0.5:
                            preemption = "MODERATE"
                        else:
                            preemption = "HIGH"
                    elif uptime_secs is not None:
                        if uptime_secs >= 3600:
                            preemption = "LOW"
                            uptime_score = 0.9
                        elif uptime_secs >= 600:
                            preemption = "MODERATE"
                            uptime_score = 0.6
                        else:
                            preemption = "HIGH"
                            uptime_score = 0.1
                    else:
                        uptime_score = None
                        preemption = "UNKNOWN"

                    for shard in rec.get("shards", []):
                        zone_url = shard.get("zone", "")
                        zone = zone_url.split("/zones/")[-1] if "/zones/" in zone_url else zone_url
                        recommendations.append({
                            "region": region,
                            "zone": zone,
                            "machineType": shard.get("machineType", machine_type),
                            "spotAvailability": availability,
                            "preemptionRate": preemption,
                            "obtainability": obtainability,
                            "uptimeScore": uptime_score,
                            "estimatedUptime": estimated_uptime,
                            "instanceCount": shard.get("instanceCount", 1),
                            "source": "Capacity Advisory (Spot)",
                        })

                if not data.get("recommendations"):
                    recommendations.append({
                        "region": region,
                        "zone": "N/A",
                        "machineType": machine_type,
                        "spotAvailability": "NO_DATA",
                        "preemptionRate": "UNKNOWN",
                        "source": "Capacity Advisory (Spot)",
                    })
            elif resp.status_code == 404:
                raise RuntimeError(
                    f"Capacity Advisory API not available for {region}. "
                    "This API is in Preview and may require project whitelisting."
                )
            else:
                error_msg = resp.text
                try:
                    error_data = resp.json()
                    error_msg = error_data.get("error", {}).get("message", resp.text)
                except Exception:
                    pass
                raise RuntimeError(
                    f"Capacity Advisory API returned {resp.status_code}: {error_msg}"
                )
    except httpx.TimeoutException:
        raise RuntimeError(f"Timeout querying capacity advisory for {region}")
    except httpx.ConnectError:
        raise RuntimeError(f"Connection error querying capacity advisory for {region}")

    return recommendations


# --- DWS Flex Start Capacity Advisory ---------------------------------------

FLEX_WAIT_SENTINEL_SECONDS = 999999999


def _parse_duration_seconds(value) -> int | None:
    """Parse a protobuf Duration string like '86400s' (or a number) to int seconds."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if s.endswith("s"):
        s = s[:-1]
    try:
        return int(float(s))
    except ValueError:
        return None


def _flex_wait_label(wait_seconds: int | None) -> tuple[str, str]:
    """Map an estimated wait duration (seconds) to (availability, humanWait)."""
    if wait_seconds is None:
        return "UNKNOWN", "Unknown"
    if wait_seconds >= FLEX_WAIT_SENTINEL_SECONDS:
        return "NONE", "No near-term capacity"
    if wait_seconds <= 0:
        return "HIGH", "Immediate (~0s)"

    mins = wait_seconds / 60.0
    hours = wait_seconds / 3600.0
    days = wait_seconds / 86400.0
    if wait_seconds < 3600:
        human = f"~{int(round(mins))} min"
    elif wait_seconds < 86400:
        human = f"~{hours:.1f} hr"
    else:
        human = f"~{days:.1f} days"

    if wait_seconds <= 900:
        availability = "HIGH"
    elif wait_seconds <= 21600:
        availability = "MODERATE"
    else:
        availability = "LOW"
    return availability, human


async def get_flex_advisory(
    project: str,
    machine_type: str,
    size: int = 1,
    max_run_duration_hours: int = 24,
    regions: list[str] | None = None,
    zones: list[str] | None = None,
    user_token: str | None = None,
) -> dict:
    """
    Query the DWS Flex Start Capacity Advisory API (Preview / whitelisted).
    """
    from gpu_data import is_consumption_supported, get_zones_for_machine_type

    results = {"recommendations": [], "errors": []}

    tpu_payload = _build_tpu_info_payload(machine_type)
    if tpu_payload:
        results["tpuInfo"] = tpu_payload
        supported = tpu_payload["supported"]
        results["message"] = (
            f"The GCE Flex Start Capacity Advisory API applies only to GCE GPU VMs. "
            f"DWS Flex Start {'is' if supported.get('dws_flex') else 'is NOT'} supported for "
            f"{tpu_payload['name']} — for TPUs use the Scan & Deploy tab (Queued Resources with FLEX_START)."
        )
        return results

    if not is_consumption_supported(machine_type, "dws_flex"):
        results["message"] = (
            f"DWS Flex Start is not supported for {machine_type}. "
            "Supported GPU families for Flex Start: A4X Max, A4X, A4, A3 (Ultra/Mega/High/Edge), G4, G2, and N1."
        )
        return results

    target_regions, allowed_zones = _resolve_regions_zones(regions, zones)
    if not target_regions:
        auto_zones = get_zones_for_machine_type(machine_type)
        if auto_zones:
            target_regions = set(z.rsplit("-", 1)[0] for z in auto_zones)
        else:
            results["errors"].append("No regions or zones specified for flex advisory.")
            return results

    token = user_token or await get_gcloud_access_token()

    # Clamp max_run_secs between 600s (10 min) and 604800s (7 days)
    max_run_secs = min(604800, max(600, int(max_run_duration_hours) * 3600))

    tasks = []
    for region in sorted(target_regions):
        tasks.append(_query_flex_advisory_region(
            token, project, region, machine_type, size, max_run_secs
        ))

    region_results = await asyncio.gather(*tasks, return_exceptions=True)

    for region, result in zip(sorted(target_regions), region_results):
        if isinstance(result, Exception):
            results["errors"].append(f"{region}: {str(result)}")
        elif result:
            for rec in result:
                zone = rec.get("zone", "")
                if not allowed_zones or zone in allowed_zones or zone == "N/A":
                    results["recommendations"].append(rec)

    return results


async def _query_flex_advisory_region(
    token: str, project: str, region: str,
    machine_type: str, size: int, max_run_secs: int,
) -> list[dict]:
    """Query DWS Flex Start capacity advisory for a single region (alpha).
    Endpoint: POST .../compute/alpha/projects/{project}/regions/{region}/advice/capacity
    """
    import httpx
    from gpu_data import MACHINE_TYPES

    url = (
        f"https://compute.googleapis.com/compute/alpha/projects/{project}"
        f"/regions/{region}/advice/capacity"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    instance_props = {
        "scheduling": {
            "provisioningModel": "FLEX_START",
            "maxRunDuration": f"{max_run_secs}s",
        }
    }
    selection_spec: dict = {
        "machineTypes": [machine_type],
    }
    # IMPORTANT: Only attach guestAccelerators for true guest-attached GPU families (N1 / T4),
    # and place it on InstanceSelection (not InstanceProperties, where GCE ignores it).
    machine_info = MACHINE_TYPES.get(machine_type, {})
    if machine_info.get("guest_attached_gpu") and machine_info.get("accelerator_type"):
        gpu_count = machine_info.get("gpu_count", 1)
        selection_spec["guestAccelerators"] = [{
            "acceleratorType": machine_info["accelerator_type"],
            "acceleratorCount": gpu_count,
        }]

    body = {
        "instanceProperties": instance_props,
        "instanceFlexibilityPolicy": {
            "instanceSelections": {
                "instance-selection-1": selection_spec,
            }
        },
        "distributionPolicy": {"targetShape": "ANY_SINGLE_ZONE"},
        "size": max(1, int(size)),
    }

    recommendations = []

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=body, headers=headers)

            if resp.status_code == 200:
                data = resp.json()
                for rec in data.get("recommendations", []):
                    scores = rec.get("scores", {})
                    wait_secs = _parse_duration_seconds(scores.get("estimatedWaitDuration"))
                    availability, human_wait = _flex_wait_label(wait_secs)

                    shards = rec.get("shards", [])
                    if not shards:
                        recommendations.append({
                            "region": region,
                            "zone": "N/A",
                            "machineType": machine_type,
                            "instanceCount": size,
                            "availability": availability,
                            "estimatedWaitSeconds": wait_secs,
                            "estimatedWait": human_wait,
                            "provisioningModel": "FLEX_START",
                            "source": "Flex Start Capacity Advisory",
                        })
                    for shard in shards:
                        zone_url = shard.get("zone", "")
                        zone = zone_url.split("/zones/")[-1] if "/zones/" in zone_url else zone_url
                        recommendations.append({
                            "region": region,
                            "zone": zone,
                            "machineType": shard.get("machineType", machine_type),
                            "instanceCount": shard.get("instanceCount", size),
                            "availability": availability,
                            "estimatedWaitSeconds": wait_secs,
                            "estimatedWait": human_wait,
                            "provisioningModel": shard.get("provisioningModel", "FLEX_START"),
                            "source": "Flex Start Capacity Advisory",
                        })

                if not data.get("recommendations"):
                    recommendations.append({
                        "region": region,
                        "zone": "N/A",
                        "machineType": machine_type,
                        "instanceCount": size,
                        "availability": "NONE",
                        "estimatedWait": "No recommendation returned",
                        "provisioningModel": "FLEX_START",
                        "source": "Flex Start Capacity Advisory",
                    })
            elif resp.status_code == 400:
                error_msg = resp.text
                try:
                    error_msg = resp.json().get("error", {}).get("message", resp.text)
                except Exception:
                    pass
                raise RuntimeError(
                    f"{error_msg} (Flex Start Capacity Advisory is a Preview feature — "
                    f"your project may need to be whitelisted for this region.)"
                )
            elif resp.status_code == 403:
                error_msg = resp.text
                try:
                    error_msg = resp.json().get("error", {}).get("message", resp.text)
                except Exception:
                    pass
                if "Alpha Access" in error_msg:
                    raise RuntimeError(
                        f"{error_msg} (DWS Flex Start Capacity Advisory requires Compute Engine "
                        f"Alpha API access and Preview project allow-listing; use Spot Advisory "
                        f"or Scan & Deploy on non-allowlisted projects.)"
                    )
                raise RuntimeError(
                    f"Flex Start Capacity Advisory API returned 403: {error_msg}"
                )
            elif resp.status_code == 404:
                raise RuntimeError(
                    f"Flex Start Capacity Advisory not available for {region}. "
                    "This API is in Preview and requires project whitelisting."
                )
            else:
                error_msg = resp.text
                try:
                    error_msg = resp.json().get("error", {}).get("message", resp.text)
                except Exception:
                    pass
                raise RuntimeError(
                    f"Flex Start Capacity Advisory API returned {resp.status_code}: {error_msg}"
                )
    except httpx.TimeoutException:
        raise RuntimeError(f"Timeout querying flex advisory for {region}")
    except httpx.ConnectError:
        raise RuntimeError(f"Connection error querying flex advisory for {region}")

    return recommendations
