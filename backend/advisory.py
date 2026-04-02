"""
Advisory API handlers for DWS Calendar Mode and Spot VM Advisory.
Uses gcloud CLI and REST APIs to query capacity recommendations.
"""

import asyncio
import json
import subprocess
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def _get_adc_token() -> str:
    """Get access token using Application Default Credentials."""
    import google.auth
    import google.auth.transport.requests

    creds, _ = google.auth.default(
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token


async def get_gcloud_access_token() -> str:
    """Get access token using ADC (runs in thread to avoid blocking)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_adc_token)


def _compute_time_window(start_date: str, flexibility_days: int, duration_days: int):
    """Compute API time window from simplified user inputs.
    Returns (start_str, end_str) as ISO 8601 UTC strings.
    """
    if start_date:
        base = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        base = datetime.now(timezone.utc) + timedelta(days=1)

    start_str = base.strftime("%Y-%m-%dT00:00:00Z")
    end_date = base + timedelta(days=flexibility_days)
    end_str = end_date.strftime("%Y-%m-%dT23:59:59Z")
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


def _check_tpu(machine_type: str, results: dict, api_name: str = "calendar") -> bool:
    """Check if machine_type is a TPU. Returns True (skip) for all TPUs since the
    Calendar Advisory API does not support TPU machine families.
    """
    from gpu_data import TPU_TYPES
    is_tpu = any(machine_type in t.get("machine_types", {}) for t in TPU_TYPES.values())
    if not is_tpu:
        return False

    tpu_gen = next((k for k, v in TPU_TYPES.items() if machine_type in v.get("machine_types", {})), "")
    tpu_info = TPU_TYPES.get(tpu_gen, {})
    zones_list = tpu_info.get("zones", [])
    supported = tpu_info.get("supported", {})

    results["tpuInfo"] = {
        "type": tpu_gen,
        "name": tpu_info.get("gpu", f"Cloud TPU {tpu_gen}"),
        "machineType": machine_type,
        "zones": zones_list,
        "regions": sorted(set(z.rsplit("-", 1)[0] for z in zones_list)),
        "topologies": tpu_info.get("topologies", []),
        "supported": supported,
        "specs": tpu_info.get("machine_types", {}).get(machine_type, {}),
    }

    if supported.get("dws_calendar"):
        # TPU supports DWS Calendar reservations, but the Advisory API doesn't support TPU
        results["message"] = (
            f"The Calendar Advisory API does not support TPU machine types. "
            f"However, {tpu_info.get('gpu', tpu_gen)} ({machine_type}) fully supports "
            f"DWS Calendar reservations — you can create them directly using the Scan & Deploy tab. "
            f"Available in {len(zones_list)} zone(s) across "
            f"{len(set(z.rsplit('-', 1)[0] for z in zones_list))} region(s)."
        )
    else:
        results["message"] = (
            f"Calendar Advisory API is not available for {tpu_info.get('gpu', tpu_gen)} ({machine_type}). "
            f"This TPU type supports: "
            f"{'On-Demand, ' if supported.get('on_demand') else ''}"
            f"{'Spot, ' if supported.get('spot') else ''}"
            f"{'DWS Flex' if supported.get('dws_flex') else ''}"
            f". Available in {len(zones_list)} zone(s) across "
            f"{len(set(z.rsplit('-', 1)[0] for z in zones_list))} region(s)."
        )
    return True


def _get_tpu_info(machine_type: str):
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
            }
    return None


async def get_calendar_advisory(
    project: str,
    machine_type: str,
    vm_count: int,
    start_date: str = "",
    flexibility_days: int = 0,
    duration_days: int = 7,
    regions: list[str] | None = None,
    zones: list[str] | None = None,
) -> dict:
    """
    Query DWS Calendar Mode Advisory API.
    Returns capacity recommendations for the specified machine type.
    """
    results = {"recommendations": [], "errors": []}

    if _check_tpu(machine_type, results):
        return results

    start_str, end_str = _compute_time_window(start_date, flexibility_days, duration_days)

    target_regions, allowed_zones = _resolve_regions_zones(regions, zones)

    # Auto-resolve regions from TPU/GPU zone data if none specified
    if not target_regions:
        from gpu_data import get_zones_for_machine_type
        auto_zones = get_zones_for_machine_type(machine_type)
        if auto_zones:
            target_regions = set(z.rsplit("-", 1)[0] for z in auto_zones)
        else:
            results["errors"].append("No regions or zones specified for calendar advisory.")
            return results

    token = await get_gcloud_access_token()

    tasks = []
    for region in sorted(target_regions):
        tasks.append(_query_calendar_advisory_region(
            token, project, region, machine_type, vm_count,
            start_str, end_str, duration_days, duration_days
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
    vm_count: int,
    start_date: str = "",
    flexibility_days: int = 0,
    duration_days: int = 7,
    regions: list[str] | None = None,
    zones: list[str] | None = None,
) -> dict:
    """
    Query Calendar Advisory at multiple VM counts to find capacity splits.
    Returns a plan showing what's available at different VM count levels,
    so users can create multiple smaller reservations.
    """
    results = {"splits": [], "fullAvailability": [], "errors": [], "summary": ""}

    if _check_tpu(machine_type, results):
        return results

    start_str, end_str = _compute_time_window(start_date, flexibility_days, duration_days)
    target_regions, allowed_zones = _resolve_regions_zones(regions, zones)

    # Auto-resolve regions from TPU/GPU zone data if none specified
    if not target_regions:
        from gpu_data import get_zones_for_machine_type
        auto_zones = get_zones_for_machine_type(machine_type)
        if auto_zones:
            target_regions = set(z.rsplit("-", 1)[0] for z in auto_zones)
        else:
            results["errors"].append("No regions or zones specified.")
            return results

    token = await get_gcloud_access_token()

    # Build VM count levels to query: 100%, 75%, 50%, 25%, and 1
    levels = []
    seen = set()
    for pct in [100, 75, 50, 25]:
        count = max(1, int(vm_count * pct / 100))
        if count not in seen:
            seen.add(count)
            levels.append((count, pct))
    if 1 not in seen and vm_count > 1:
        levels.append((1, round(100 / vm_count)))

    # Query all levels x regions in parallel, with minDuration=1 to find any available sub-windows
    all_tasks = []
    task_meta = []
    for count, pct in levels:
        for region in sorted(target_regions):
            all_tasks.append(_query_calendar_advisory_region(
                token, project, region, machine_type, count,
                start_str, end_str, 1, duration_days
            ))
            task_meta.append((count, pct, region))

    all_results = await asyncio.gather(*all_tasks, return_exceptions=True)

    # Group results by VM count level
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

    # Build splits list ordered by VM count (highest first)
    for count, pct in levels:
        if count in level_recs:
            results["splits"].append(level_recs[count])

    # Full availability is the 100% level
    if vm_count in level_recs:
        results["fullAvailability"] = [
            r for r in level_recs[vm_count]["recommendations"]
            if r.get("status") == "RECOMMENDED"
        ]

    # Build summary
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

    url = (
        f"https://compute.googleapis.com/compute/v1/projects/{project}"
        f"/regions/{region}/advice/calendarMode"
    )

    # Convert days to seconds for API
    min_duration_secs = duration_min_days * 86400
    max_duration_secs = duration_max_days * 86400

    from gpu_data import MACHINE_TO_FAMILY
    tpu_info = _get_tpu_info(machine_type)

    # Both GPU and TPU use specificSkuResources with their machine type
    target_resources = {
        "specificSkuResources": {
            "instanceCount": str(vm_count),
            "machineType": machine_type,
        }
    }
    if tpu_info:
        logger.info(f"TPU Calendar Advisory: {machine_type} (chips={tpu_info['chips']}, count={vm_count})")

    family = MACHINE_TO_FAMILY.get(machine_type, "")
    dense_families = ("A4", "A3 Ultra", "A3 Mega", "A3 High", "A3 Edge")
    spec_body = {
        "targetResources": target_resources,
        "timeRangeSpec": {
            "minDuration": f"{min_duration_secs}s",
            "maxDuration": f"{max_duration_secs}s",
            "startTimeNotEarlierThan": start_time,
            "startTimeNotLaterThan": end_time,
        },
    }
    if not tpu_info and family in dense_families:
        spec_body["deploymentType"] = "DENSE"

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
                # Parse the response format from the API
                for rec_group in data.get("recommendations", []):
                    rps = rec_group.get("recommendationsPerSpec", {})
                    # rps is a map: arbitrary key -> FutureResourcesRecommendation
                    for _spec_key, spec in rps.items():
                        rec_id = spec.get("recommendationId", "")
                        rec_type = spec.get("recommendationType", "")

                        # Primary recommended location
                        location = spec.get("location", "")
                        if location:
                            zone = location.replace("zones/", "")
                            recommendations.append({
                                "region": region,
                                "zone": zone,
                                "machineType": machine_type,
                                "vmCount": vm_count,
                                "status": "RECOMMENDED",
                                "startTime": spec.get("startTime", start_time),
                                "endTime": spec.get("endTime", end_time),
                                "confidence": "HIGH",
                                "source": "DWS Calendar Advisory",
                                "recommendationType": rec_type,
                            })

                        # Other locations with their status
                        for loc_key, loc_data in spec.get("otherLocations", {}).items():
                            zone = loc_key.replace("zones/", "")
                            status = loc_data.get("status", "UNKNOWN")
                            details = loc_data.get("details", "")
                            if status == "RECOMMENDED":
                                confidence = "MODERATE"
                            elif status == "NO_CAPACITY":
                                confidence = "NONE"
                            elif status == "NOT_SUPPORTED":
                                confidence = "LOW"
                            else:
                                confidence = "LOW"
                            recommendations.append({
                                "region": region,
                                "zone": zone,
                                "machineType": machine_type,
                                "vmCount": vm_count,
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
                        "vmCount": vm_count,
                        "status": "NO_DATA",
                        "rawResponse": data,
                        "source": "DWS Calendar Advisory",
                    })
            elif resp.status_code == 404:
                return await _calendar_advisory_gcloud_fallback(
                    project, region, machine_type, vm_count, start_time, end_time
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
    cmd = [
        "gcloud", "beta", "compute", "advice", "calendar-mode",
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
) -> dict:
    """
    Query Spot VM Advisory API (Preview).
    Returns spot availability and preemption risk info.
    """
    results = {"recommendations": [], "errors": []}

    # TPU machine types are not supported by the Spot Advisory API
    from gpu_data import TPU_TYPES
    is_tpu = any(machine_type in t.get("machine_types", {}) for t in TPU_TYPES.values())
    if is_tpu:
        tpu_gen = next((k for k, v in TPU_TYPES.items() if machine_type in v.get("machine_types", {})), "")
        tpu_info = TPU_TYPES.get(tpu_gen, {})
        zones_list = tpu_info.get("zones", [])
        supported = tpu_info.get("supported", {})
        results["tpuInfo"] = {
            "type": tpu_gen,
            "name": tpu_info.get("gpu", f"Cloud TPU {tpu_gen}"),
            "machineType": machine_type,
            "zones": zones_list,
            "regions": sorted(set(z.rsplit("-", 1)[0] for z in zones_list)),
            "topologies": tpu_info.get("topologies", []),
            "supported": supported,
            "specs": tpu_info.get("machine_types", {}).get(machine_type, {}),
        }
        # Build spot recommendations from TPU zone data
        for z in zones_list:
            r = z.rsplit("-", 1)[0]
            results["recommendations"].append({
                "region": r,
                "zone": z,
                "machineType": machine_type,
                "spotAvailability": "SUPPORTED" if supported.get("spot") else "NOT_SUPPORTED",
                "preemptionRate": "UNKNOWN",
                "source": "TPU Zone Data (Advisory API not available for TPU)",
            })
        results["message"] = (
            f"Spot Advisory API is not available for TPU types. "
            f"Showing zone availability from TPU configuration data. "
            f"Spot VMs {'are' if supported.get('spot') else 'are NOT'} supported for {tpu_info.get('gpu', tpu_gen)}."
        )
        return results

    target_regions = set()
    allowed_zones = set(zones) if zones else set()
    if zones:
        for z in zones:
            region = z.rsplit("-", 1)[0]
            target_regions.add(region)
    if regions:
        target_regions.update(regions)

    if not target_regions:
        results["errors"].append("No regions or zones specified for spot advisory.")
        return results

    token = await get_gcloud_access_token()

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
            # Filter results to only include zones in the allowed zones list
            for rec in result:
                zone = rec.get("zone", "")
                if not allowed_zones or zone in allowed_zones:
                    results["recommendations"].append(rec)

    return results


async def _query_spot_advisory_region(
    token: str, project: str, region: str, machine_type: str
) -> list[dict]:
    """Query spot advisory using the Capacity Advisory API (alpha).
    Endpoint: POST .../regions/{region}/advice/capacity
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

    # Build instanceProperties with GPU accelerators if applicable
    # For guest accelerator GPUs (T4, L4), we must include the accelerator
    # in the request, otherwise the API only checks CPU VM availability
    instance_props = {
        "scheduling": {
            "provisioningModel": "SPOT",
        }
    }
    machine_info = MACHINE_TYPES.get(machine_type, {})
    accel_type = machine_info.get("accelerator_type")
    if accel_type:
        gpu_count = machine_info.get("gpu_count", 1)
        instance_props["guestAccelerators"] = [{
            "acceleratorType": accel_type,
            "acceleratorCount": gpu_count,
        }]

    body = {
        "distributionPolicy": {"targetShape": "ANY_SINGLE_ZONE"},
        "instanceFlexibilityPolicy": {
            "instanceSelections": {
                "instance-selection-1": {
                    "machineTypes": [machine_type],
                }
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
                    uptime_score = scores.get("uptimeScore", 0)
                    estimated_uptime = scores.get("estimatedUptime", "unknown")

                    # Map obtainability to availability label
                    if obtainability >= 0.8:
                        availability = "HIGH"
                    elif obtainability >= 0.5:
                        availability = "MODERATE"
                    elif obtainability >= 0.2:
                        availability = "LOW"
                    else:
                        availability = "VERY_LOW"

                    # Map uptime score to preemption risk
                    if uptime_score >= 0.8:
                        preemption = "LOW"
                    elif uptime_score >= 0.5:
                        preemption = "MODERATE"
                    else:
                        preemption = "HIGH"

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


async def _spot_advisory_gcloud_fallback(
    project: str, region: str, machine_type: str
) -> list[dict]:
    """Fallback to gcloud CLI for spot advisory."""
    cmd = [
        "gcloud", "alpha", "compute", "advice", "spot-resources",
        f"--project={project}",
        f"--region={region}",
        f"--instance-type={machine_type}",
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
        raise RuntimeError(f"gcloud spot advisory failed: {error}")

    try:
        data = json.loads(stdout.decode())
        recommendations = []
        if isinstance(data, list):
            for item in data:
                recommendations.append({
                    "region": region,
                    "zone": item.get("zone", "N/A"),
                    "machineType": machine_type,
                    "spotAvailability": item.get("availability", "UNKNOWN"),
                    "preemptionRate": item.get("preemptionRate", "UNKNOWN"),
                    "source": "Spot VM Advisory (gcloud)",
                })
        return recommendations
    except json.JSONDecodeError:
        return []
