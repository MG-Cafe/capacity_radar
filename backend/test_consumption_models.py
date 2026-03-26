#!/usr/bin/env python3
"""
Test all GPU families × consumption models against GCP API.
Determines which combinations are truly supported vs not.
Immediately cleans up any resources that get created.
"""

import asyncio
import json
import sys
import uuid
import httpx
from datetime import datetime, timedelta, timezone

PROJECT = sys.argv[1] if len(sys.argv) > 1 else "northam-ce-mlai-tpu"

# One representative machine type per family + one zone
TEST_CASES = [
    {"family": "A4X Max", "mt": "a4x-maxgpu-4g-metal",  "zone": "us-central1-b"},
    {"family": "A4X",     "mt": "a4x-highgpu-4g",  "zone": "us-central1-a"},
    {"family": "A4",      "mt": "a4-highgpu-8g",   "zone": "us-east4-b"},
    {"family": "A3 Ultra","mt": "a3-ultragpu-8g",  "zone": "us-central1-b"},
    {"family": "A3 Mega", "mt": "a3-megagpu-8g",   "zone": "us-central1-a"},
    {"family": "A3 High", "mt": "a3-highgpu-8g",   "zone": "us-central1-a"},
    {"family": "A2 Ultra","mt": "a2-ultragpu-1g",  "zone": "us-central1-a"},
    {"family": "A2 Std",  "mt": "a2-highgpu-1g",   "zone": "us-central1-a"},
    {"family": "G4",      "mt": "g4-standard-48",  "zone": "us-central1-b"},
    {"family": "G2",      "mt": "g2-standard-4",   "zone": "us-central1-a"},
]

def get_token():
    import google.auth
    import google.auth.transport.requests
    creds, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    creds.refresh(google.auth.transport.requests.Request())
    return creds.token

def classify_error(status_code, error_msg):
    """Classify API error as SUPPORTED (capacity issue) or NOT_SUPPORTED."""
    error_lower = error_msg.lower()
    not_supported_keywords = [
        "not supported", "disallowed", "not available for",
        "is not valid", "unsupported", "not a valid",
        "machine type is not allowed", "not permitted",
        "invalid machine type", "does not support",
    ]
    for kw in not_supported_keywords:
        if kw in error_lower:
            return "NOT_SUPPORTED"
    
    capacity_keywords = [
        "stockout", "no capacity", "exhausted", "insufficient",
        "quota", "limit", "resource_already_exists", "already exists",
    ]
    for kw in capacity_keywords:
        if kw in error_lower:
            return "SUPPORTED"
    
    if status_code == 409:  # Conflict = resource exists = supported
        return "SUPPORTED"
    if status_code == 403:
        return "PERMISSION_ERROR"
    
    return f"UNKNOWN({status_code})"


async def test_on_demand(client, token, mt, zone):
    """Test on-demand reservation creation."""
    name = f"test-od-{uuid.uuid4().hex[:8]}"
    url = f"https://compute.googleapis.com/compute/v1/projects/{PROJECT}/zones/{zone}/reservations"
    body = {
        "name": name,
        "specificReservation": {
            "count": "1",
            "instanceProperties": {"machineType": mt}
        },
        "specificReservationRequired": False,
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    try:
        resp = await client.post(url, json=body, headers=headers)
        data = resp.json()
        
        if resp.status_code == 200:
            # Success! Clean up immediately
            op_name = data.get("name", "")
            # Wait for operation then delete
            await asyncio.sleep(3)
            del_url = f"https://compute.googleapis.com/compute/v1/projects/{PROJECT}/zones/{zone}/reservations/{name}"
            await client.delete(del_url, headers=headers)
            return "SUPPORTED", "Created successfully (cleaned up)"
        else:
            error_msg = data.get("error", {}).get("message", str(data))
            result = classify_error(resp.status_code, error_msg)
            return result, error_msg[:120]
    except Exception as e:
        return "ERROR", str(e)[:120]


async def test_dws_calendar(client, token, mt, zone):
    """Test DWS Calendar (future reservation) creation."""
    name = f"test-cal-{uuid.uuid4().hex[:8]}"
    region = zone.rsplit("-", 1)[0]
    start = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    url = f"https://compute.googleapis.com/compute/beta/projects/{PROJECT}/zones/{zone}/futureReservations"
    body = {
        "name": name,
        "specificSkuProperties": {
            "instanceProperties": {"machineType": mt},
            "totalCount": "1",
        },
        "timeWindow": {
            "startTime": start,
            "endTime": end,
        },
        "planningStatus": "DRAFT",
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    try:
        resp = await client.post(url, json=body, headers=headers)
        data = resp.json()
        
        if resp.status_code == 200:
            # Success! Clean up
            op_name = data.get("name", "")
            await asyncio.sleep(3)
            del_url = f"https://compute.googleapis.com/compute/beta/projects/{PROJECT}/zones/{zone}/futureReservations/{name}"
            await client.delete(del_url, headers=headers)
            return "SUPPORTED", "Created successfully (cleaned up)"
        else:
            error_msg = data.get("error", {}).get("message", str(data))
            result = classify_error(resp.status_code, error_msg)
            return result, error_msg[:120]
    except Exception as e:
        return "ERROR", str(e)[:120]


async def test_spot(client, token, mt, zone):
    """Test spot VM creation (will fail due to capacity, but tells us if supported)."""
    name = f"test-spot-{uuid.uuid4().hex[:8]}"
    url = f"https://compute.googleapis.com/compute/v1/projects/{PROJECT}/zones/{zone}/instances"
    body = {
        "name": name,
        "machineType": f"zones/{zone}/machineTypes/{mt}",
        "scheduling": {
            "provisioningModel": "SPOT",
            "onHostMaintenance": "TERMINATE",
        },
        "disks": [{
            "boot": True,
            "autoDelete": True,
            "initializeParams": {
                "sourceImage": "projects/debian-cloud/global/images/family/debian-12",
                "diskSizeGb": "50",
            }
        }],
        "networkInterfaces": [{
            "network": f"projects/{PROJECT}/global/networks/default",
            "accessConfigs": [{"type": "ONE_TO_ONE_NAT", "name": "External NAT"}]
        }],
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    try:
        resp = await client.post(url, json=body, headers=headers)
        data = resp.json()
        
        if resp.status_code == 200:
            # Success! Clean up immediately
            await asyncio.sleep(5)
            del_url = f"https://compute.googleapis.com/compute/v1/projects/{PROJECT}/zones/{zone}/instances/{name}"
            await client.delete(del_url, headers=headers)
            return "SUPPORTED", "Created successfully (cleaned up)"
        else:
            error_msg = data.get("error", {}).get("message", "")
            if not error_msg:
                # Check for errors array
                errors = data.get("error", {}).get("errors", [])
                if errors:
                    error_msg = errors[0].get("message", str(data))
            result = classify_error(resp.status_code, error_msg)
            return result, error_msg[:120]
    except Exception as e:
        return "ERROR", str(e)[:120]


async def test_dws_flex(client, token, mt, zone):
    """Test DWS Flex (resize request). Requires MIG, so we test via the resize API directly."""
    # DWS Flex requires creating an Instance Group Manager first, which is complex.
    # Instead, try creating a resize request directly and check the error.
    name = f"test-flex-{uuid.uuid4().hex[:8]}"
    mig_name = f"test-mig-{uuid.uuid4().hex[:8]}"
    
    # First create a minimal instance template
    tmpl_name = f"test-tmpl-{uuid.uuid4().hex[:8]}"
    tmpl_url = f"https://compute.googleapis.com/compute/v1/projects/{PROJECT}/global/instanceTemplates"
    tmpl_body = {
        "name": tmpl_name,
        "properties": {
            "machineType": mt,
            "disks": [{
                "boot": True,
                "autoDelete": True,
                "initializeParams": {
                    "sourceImage": "projects/debian-cloud/global/images/family/debian-12",
                    "diskSizeGb": "50",
                }
            }],
            "networkInterfaces": [{
                "network": f"projects/{PROJECT}/global/networks/default",
            }],
            "scheduling": {"onHostMaintenance": "TERMINATE"},
        }
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    try:
        # Create instance template
        resp = await client.post(tmpl_url, json=tmpl_body, headers=headers)
        if resp.status_code != 200:
            data = resp.json()
            error_msg = data.get("error", {}).get("message", str(data))
            result = classify_error(resp.status_code, error_msg)
            return result, f"Template creation failed: {error_msg[:100]}"
        
        await asyncio.sleep(5)
        
        # Create MIG
        mig_url = f"https://compute.googleapis.com/compute/v1/projects/{PROJECT}/zones/{zone}/instanceGroupManagers"
        mig_body = {
            "name": mig_name,
            "instanceTemplate": f"projects/{PROJECT}/global/instanceTemplates/{tmpl_name}",
            "targetSize": 0,
        }
        resp = await client.post(mig_url, json=mig_body, headers=headers)
        if resp.status_code != 200:
            data = resp.json()
            error_msg = data.get("error", {}).get("message", str(data))
            # Clean up template
            await client.delete(f"{tmpl_url}/{tmpl_name}", headers=headers)
            result = classify_error(resp.status_code, error_msg)
            return result, f"MIG creation failed: {error_msg[:100]}"
        
        await asyncio.sleep(8)
        
        # Create resize request (DWS Flex)
        rr_url = f"https://compute.googleapis.com/compute/beta/projects/{PROJECT}/zones/{zone}/instanceGroupManagers/{mig_name}/resizeRequests"
        rr_body = {
            "name": name,
            "resizeBy": 1,
            "requestedRunDuration": {"seconds": "86400"},  # 24 hours
        }
        resp = await client.post(rr_url, json=rr_body, headers=headers)
        data = resp.json()
        
        if resp.status_code == 200:
            result_status = "SUPPORTED"
            result_msg = "Created successfully (cleaning up)"
            # Cancel resize request
            await asyncio.sleep(3)
            cancel_url = f"{rr_url}/{name}/cancel"
            await client.post(cancel_url, headers=headers)
        else:
            error_msg = data.get("error", {}).get("message", str(data))
            result_status = classify_error(resp.status_code, error_msg)
            result_msg = error_msg[:120]
        
        # Clean up MIG and template
        await asyncio.sleep(3)
        await client.delete(f"{mig_url}/{mig_name}", headers=headers)
        await asyncio.sleep(5)
        await client.delete(f"{tmpl_url}/{tmpl_name}", headers=headers)
        
        return result_status, result_msg
    except Exception as e:
        return "ERROR", str(e)[:120]


async def main():
    token = get_token()
    print(f"\n{'='*100}")
    print(f"GPU CONSUMPTION MODEL VALIDATION — Project: {PROJECT}")
    print(f"{'='*100}\n")
    
    results = []
    
    async with httpx.AsyncClient(timeout=60) as client:
        for tc in TEST_CASES:
            family = tc["family"]
            mt = tc["mt"]
            zone = tc["zone"]
            print(f"\n{'─'*80}")
            print(f"Testing: {family} ({mt}) in {zone}")
            print(f"{'─'*80}")
            
            row = {"family": family, "mt": mt, "zone": zone}
            
            # Test On-Demand
            print(f"  🔹 On-Demand Reservation...", end=" ", flush=True)
            status, msg = await test_on_demand(client, token, mt, zone)
            row["on_demand"] = status
            print(f"{status} — {msg}")
            
            # Test DWS Calendar
            print(f"  🔹 DWS Calendar (Future Reservation)...", end=" ", flush=True)
            status, msg = await test_dws_calendar(client, token, mt, zone)
            row["dws_calendar"] = status
            print(f"{status} — {msg}")
            
            # Test Spot
            print(f"  🔹 Spot VM...", end=" ", flush=True)
            status, msg = await test_spot(client, token, mt, zone)
            row["spot"] = status
            print(f"{status} — {msg}")
            
            # Test DWS Flex
            print(f"  🔹 DWS Flex (Resize Request)...", end=" ", flush=True)
            status, msg = await test_dws_flex(client, token, mt, zone)
            row["dws_flex"] = status
            print(f"{status} — {msg}")
            
            results.append(row)
    
    # Summary table
    print(f"\n\n{'='*100}")
    print("SUMMARY TABLE")
    print(f"{'='*100}")
    print(f"{'Family':<12} {'Machine Type':<20} {'On-Demand':<16} {'DWS Calendar':<16} {'DWS Flex':<16} {'Spot':<16}")
    print(f"{'─'*12} {'─'*20} {'─'*16} {'─'*16} {'─'*16} {'─'*16}")
    for r in results:
        print(f"{r['family']:<12} {r['mt']:<20} {r['on_demand']:<16} {r['dws_calendar']:<16} {r['dws_flex']:<16} {r['spot']:<16}")
    
    print(f"\n{'='*100}")
    print("Legend: SUPPORTED = works or capacity issue | NOT_SUPPORTED = API rejects | PERMISSION_ERROR = need IAM role")
    print(f"{'='*100}\n")


if __name__ == "__main__":
    asyncio.run(main())
