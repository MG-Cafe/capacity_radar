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
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _get_adc_token)


async def get_calendar_advisory(
    project: str,
    machine_type: str,
    vm_count: int,
    duration_min_days: int = 1,
    duration_max_days: int = 7,
    start_from: str = "",
    start_to: str = "",
    regions: list[str] | None = None,
    zones: list[str] | None = None,
) -> dict:
    """
    Query DWS Calendar Mode Advisory API.
    Returns capacity recommendations for the specified machine type.
    """
    results = {"recommendations": [], "errors": []}

    # TPU machine types are not supported by the Calendar Advisory API
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
        results["message"] = (
            f"Calendar Advisory API is not available for TPU types. "
            f"However, {tpu_info.get('gpu', tpu_gen)} ({machine_type}) supports: "
            f"{'On-Demand, ' if supported.get('on_demand') else ''}"
            f"{'Spot, ' if supported.get('spot') else ''}"
            f"{'DWS Calendar, ' if supported.get('dws_calendar') else ''}"
            f"{'DWS Flex' if supported.get('dws_flex') else ''}"
            f". Available in {len(zones_list)} zone(s) across {len(set(z.rsplit('-', 1)[0] for z in zones_list))} region(s)."
        )
        return results

    # Calculate time window from dates
    if start_from:
        start_str = f"{start_from}T00:00:00Z"
    else:
        start_time = datetime.now(timezone.utc) + timedelta(days=1)
        start_str = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    if start_to:
        end_str = f"{start_to}T23:59:59Z"
    else:
        end_time = datetime.now(timezone.utc) + timedelta(days=14)
        end_str = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    # If zones provided, derive regions from zones
    target_regions = set()
    if zones:
        for z in zones:
            region = z.rsplit("-", 1)[0]
            target_regions.add(region)
    if regions:
        target_regions.update(regions)

    if not target_regions:
        results["errors"].append("No regions or zones specified for calendar advisory.")
        return results

    token = await get_gcloud_access_token()

    tasks = []
    for region in sorted(target_regions):
        tasks.append(_query_calendar_advisory_region(
            token, project, region, machine_type, vm_count,
            start_str, end_str, duration_min_days, duration_max_days
        ))

    region_results = await asyncio.gather(*tasks, return_exceptions=True)

    for region, result in zip(sorted(target_regions), region_results):
        if isinstance(result, Exception):
            results["errors"].append(f"{region}: {str(result)}")
        elif result:
            results["recommendations"].extend(result)

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

    body = {
        "futureResourcesSpecs": {
            "spec": {
                "deploymentType": "DENSE",
                "targetResources": {
                    "specificSkuResources": {
                        "instanceCount": str(vm_count),
                        "machineType": machine_type,
                    }
                },
                "timeRangeSpec": {
                    "minDuration": f"{min_duration_secs}s",
                    "maxDuration": f"{max_duration_secs}s",
                    "startTimeNotEarlierThan": start_time,
                    "startTimeNotLaterThan": end_time,
                },
            }
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
                    spec = rps.get("spec", {})
                    rec_id = spec.get("recommendationId", "")
                    rec_type = spec.get("recommendationType", "")

                    # Parse recommended locations
                    for loc_key, loc_data in spec.get("recommendedLocations", {}).items():
                        zone = loc_key.replace("zones/", "")
                        recommendations.append({
                            "region": region,
                            "zone": zone,
                            "machineType": machine_type,
                            "vmCount": vm_count,
                            "status": "RECOMMENDED",
                            "startTime": loc_data.get("startTime", start_time),
                            "endTime": loc_data.get("endTime", end_time),
                            "confidence": "HIGH",
                            "source": "DWS Calendar Advisory",
                            "recommendationType": rec_type,
                        })

                    # Parse other locations (no capacity)
                    for loc_key, loc_data in spec.get("otherLocations", {}).items():
                        zone = loc_key.replace("zones/", "")
                        status = loc_data.get("status", "UNKNOWN")
                        details = loc_data.get("details", "")
                        recommendations.append({
                            "region": region,
                            "zone": zone,
                            "machineType": machine_type,
                            "vmCount": vm_count,
                            "status": status,
                            "details": details,
                            "startTime": start_time,
                            "endTime": end_time,
                            "confidence": "NONE" if status == "NO_CAPACITY" else "LOW",
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
            results["recommendations"].extend(result)

    return results


async def _query_spot_advisory_region(
    token: str, project: str, region: str, machine_type: str
) -> list[dict]:
    """Query spot advisory using the Capacity Advisory API (alpha).
    Endpoint: POST .../regions/{region}/advice/capacity
    """
    import httpx

    url = (
        f"https://compute.googleapis.com/compute/alpha/projects/{project}"
        f"/regions/{region}/advice/capacity"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    body = {
        "distributionPolicy": {"targetShape": "ANY_SINGLE_ZONE"},
        "instanceFlexibilityPolicy": {
            "instanceSelections": {
                "instance-selection-1": {
                    "machineTypes": [machine_type],
                }
            }
        },
        "instanceProperties": {
            "scheduling": {
                "provisioningModel": "SPOT",
            }
        },
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
