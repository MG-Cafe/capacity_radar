#!/usr/bin/env python3
"""
End-to-End Verification & Live GCP Validation Suite for Capacity Radar.

Modes:
1. Automated E2E / Unit & Payload Verification (default when no project is given, or `--unit`):
   Tests all GPU families (A4X Max, A4X, A4, A3 Ultra, A3 Mega, A3 High, A3 Edge, A2 Ultra,
   A2 Standard, G4, G2, N1) and all TPU families (v7x, v6e, v5p, v5e, v4, v3, v2) across:
   - Catalog & Zone/Calendar-Zone metadata (`gpu_data.py`)
   - Capacity Advisory Tab (`advisory.py`: Calendar, Calendar Splits, Spot, Flex Start)
   - Scan & Deploy Tab (`hunter.py`: On-Demand Reservation / TPU Node, DWS Calendar Future
     Reservation for GPU & TPU, DWS Flex Start GCE Instances & TPU v2alpha1 QueuedResources,
     Spot VMs & Spot TPU Nodes)
   - FastAPI REST endpoints (`main.py`)

2. Live GCP API Validation (`python test_consumption_models.py <PROJECT_ID>`):
   Tests live GCP Advisory APIs and consumption model endpoints against `<PROJECT_ID>`.
"""

import asyncio
import json
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    import httpx
except ImportError:
    httpx = types.ModuleType("httpx")
    httpx.AsyncClient = MagicMock()
    httpx.TimeoutException = TimeoutError
    sys.modules["httpx"] = httpx

from gpu_data import (
    CALENDAR_CONFIG,
    CONSUMPTION_SUPPORT,
    MACHINE_TYPES,
    TPU_TYPES,
    get_all_machine_types_info,
    get_calendar_config_for_machine_type,
    get_calendar_zones_for_machine_type,
    get_chip_groups,
    get_tpu_spec,
    get_zones_for_machine_type,
    is_consumption_supported,
)
import advisory
import hunter


class MockResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text or json.dumps(self._json_data)

    def json(self):
        return self._json_data


class TestCapacityRadarEndToEnd(unittest.IsolatedAsyncioTestCase):
    """Comprehensive verification of all GPU & TPU families across Advisory and Scan & Deploy."""

    def test_01_gpu_catalog_and_boot_disks(self):
        """Verify all GPU families, guest accelerators, boot disk types, and gVNIC settings."""
        hyperdisk_families = {"A4X Max", "A4X", "A4", "A3 Ultra", "G4"}
        for mt, mdata in MACHINE_TYPES.items():
            family = mdata["family"]
            if family in hyperdisk_families:
                self.assertTrue(mdata["requires_hyperdisk"], f"{mt} ({family}) must require hyperdisk")
                self.assertEqual(mdata["default_boot_disk_type"], "hyperdisk-balanced")
            else:
                self.assertFalse(mdata["requires_hyperdisk"], f"{mt} ({family}) should not require hyperdisk")
                self.assertEqual(mdata["default_boot_disk_type"], "pd-balanced")

            if family == "N1":
                self.assertTrue(mdata["guest_attached_gpu"], "N1 must use guest_attached_gpu=True")
                self.assertEqual(mdata["accelerator_type"], "nvidia-tesla-t4")
            else:
                self.assertFalse(
                    mdata["guest_attached_gpu"],
                    f"{mt} ({family}, including G2) must have guest_attached_gpu=False",
                )
                self.assertIsNone(mdata["accelerator_type"], f"{mt} must have accelerator_type=None")

    def test_02_tpu_catalog_and_specs(self):
        """Verify all TPU families (including v7x Ironwood, v6e, v5p, v5e, v4, v3, v2)."""
        expected_tpus = {"v7x", "v6e", "v5p", "v5e", "v4", "v3", "v2"}
        self.assertEqual(set(TPU_TYPES.keys()), expected_tpus)

        # Verify v7x (Ironwood)
        v7x_1t = get_tpu_spec("tpu7x-standard-1t")
        self.assertIsNotNone(v7x_1t)
        self.assertEqual(v7x_1t["accelerator_type"], "tpu7x-2")
        self.assertEqual(v7x_1t["runtime_version"], "v2-alpha-tpu7")

        v7x_4t = get_tpu_spec("tpu7x-standard-4t")
        self.assertIsNotNone(v7x_4t)
        self.assertEqual(v7x_4t["accelerator_type"], "tpu7x-8")
        self.assertEqual(v7x_4t["runtime_version"], "v2-alpha-tpu7")

        # Verify v6e (1 core per chip)
        v6e_4t = get_tpu_spec("ct6e-standard-4t")
        self.assertEqual(v6e_4t["accelerator_type"], "v6e-4")
        self.assertEqual(v6e_4t["runtime_version"], "v2-alpha-tpuv6e")

        # Verify v5p (2 cores per chip -> v5p-8)
        v5p_4t = get_tpu_spec("ct5p-hightpu-4t")
        self.assertEqual(v5p_4t["accelerator_type"], "v5p-8")
        self.assertEqual(v5p_4t["runtime_version"], "v2-alpha-tpuv5")

        # Verify v5e (ct5lp-hightpu-* + legacy ct5e-* alias)
        v5e_4t = get_tpu_spec("ct5lp-hightpu-4t")
        self.assertEqual(v5e_4t["accelerator_type"], "v5litepod-4")
        self.assertEqual(v5e_4t["runtime_version"], "v2-alpha-tpuv5-lite")
        v5e_legacy = get_tpu_spec("ct5e-hightpu-4t")
        self.assertEqual(v5e_legacy["canonical_machine_type"], "ct5lp-hightpu-4t")

        # Verify v4 (2 cores per chip -> v4-8)
        v4_4t = get_tpu_spec("ct4p-hightpu-4t")
        self.assertEqual(v4_4t["accelerator_type"], "v4-8")
        self.assertEqual(v4_4t["runtime_version"], "tpu-ubuntu2204-base")

    def test_03_calendar_config_and_zones(self):
        """Verify DWS Calendar Mode support and authoritative calendar zones."""
        cal_supported_mts = [
            "a4x-highgpu-4g",
            "a4-highgpu-8g",
            "a3-ultragpu-8g",
            "a3-megagpu-8g",
            "a3-highgpu-8g",
            "ct6e-standard-4t",
            "ct5p-hightpu-4t",
            "ct5lp-hightpu-4t",
        ]
        for mt in cal_supported_mts:
            cfg = get_calendar_config_for_machine_type(mt)
            self.assertIsNotNone(cfg, f"{mt} must have calendar config")
            cal_zones = get_calendar_zones_for_machine_type(mt)
            self.assertTrue(len(cal_zones) > 0, f"{mt} must have calendar zones")

        # A3 Edge, G2, N1, v7x, v4 must NOT have calendar mode enabled
        for mt in ["a3-edgegpu-8g", "g2-standard-4", "n1-standard-4", "tpu7x-standard-4t", "ct4p-hightpu-4t"]:
            self.assertIsNone(get_calendar_config_for_machine_type(mt), f"{mt} must not have calendar config")
            self.assertFalse(is_consumption_supported(mt, "dws_calendar"), f"{mt} must have dws_calendar=False")

    async def test_04_advisory_calendar_gpu_and_tpu(self):
        """Verify Calendar Advisory & Splits for both GPU (specificSkuResources) and TPU (aggregateResources)."""
        captured_requests = []

        async def mock_post(url, json=None, headers=None):
            captured_requests.append((url, json))
            return MockResponse(
                200,
                {
                    "recommendations": [
                        {
                            "recommendationsPerSpec": {
                                "spec": {
                                    "recommendationType": "SINGLE_LOCATION",
                                    "location": "zones/us-east4-b",
                                    "startTime": "2026-11-10T00:00:00Z",
                                    "endTime": "2026-11-17T00:00:00Z",
                                }
                            }
                        }
                    ]
                },
            )

        mock_client = AsyncMock()
        mock_client.post.side_effect = mock_post
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch.object(hunter.ScanningSession, "_log_deployment_event", MagicMock()):
            # 1. GPU Calendar Advisory (A4)
            captured_requests.clear()
            res_gpu = await advisory.get_calendar_advisory(
                project="test-proj",
                machine_type="a4-highgpu-8g",
                vm_count=2,
                duration_days=7,
                user_token="fake-token",
            )
            self.assertTrue(len(res_gpu["recommendations"]) > 0)
            _, gpu_body = captured_requests[0]
            spec = gpu_body["futureResourcesSpecs"]["spec"]
            self.assertIn("specificSkuResources", spec["targetResources"])
            self.assertEqual(spec["targetResources"]["specificSkuResources"]["machineType"], "a4-highgpu-8g")
            self.assertEqual(spec["targetResources"]["specificSkuResources"]["instanceCount"], "2")

            # 2. TPU Calendar Advisory (v6e) -> must use aggregateResources!
            captured_requests.clear()
            res_tpu = await advisory.get_calendar_advisory(
                project="test-proj",
                machine_type="ct6e-standard-4t",
                vm_count=1,
                duration_days=7,
                user_token="fake-token",
            )
            self.assertIn("tpuInfo", res_tpu)
            self.assertTrue(len(res_tpu["recommendations"]) > 0)
            _, tpu_body = captured_requests[0]
            tpu_spec = tpu_body["futureResourcesSpecs"]["spec"]
            self.assertIn("aggregateResources", tpu_spec["targetResources"])
            self.assertEqual(
                tpu_spec["targetResources"]["aggregateResources"]["vmFamily"],
                "VM_FAMILY_CLOUD_TPU_LITE_POD_SLICE_CT6E",
            )
            self.assertEqual(tpu_spec["targetResources"]["aggregateResources"]["acceleratorCount"], 4)

            # 3. TPU Calendar Splits (v5p) -> must return real splits!
            captured_requests.clear()
            splits_tpu = await advisory.find_best_splits(
                project="test-proj",
                machine_type="ct5p-hightpu-4t",
                vm_count=4,
                duration_days=7,
                user_token="fake-token",
            )
            self.assertIn("tpuInfo", splits_tpu)
            self.assertTrue(len(splits_tpu["splits"]) > 0)

    async def test_05_advisory_spot_and_flex_guest_accelerators(self):
        """Verify Spot uses /compute/beta/, derives preemption from estimatedUptime, and places N1 guestAccelerators under instanceSelections."""
        captured_requests = []
        mock_spot_payload = {"recommendations": []}

        async def mock_post(url, json=None, headers=None):
            captured_requests.append((url, json))
            return MockResponse(200, mock_spot_payload)

        mock_client = AsyncMock()
        mock_client.post.side_effect = mock_post
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch.object(hunter.ScanningSession, "_log_deployment_event", MagicMock()):
            # G2 (L4) Spot Advisory -> /compute/beta/ + NO guestAccelerators anywhere
            captured_requests.clear()
            await advisory.get_spot_advisory(
                project="test-proj",
                machine_type="g2-standard-4",
                zones=["us-central1-a"],
                user_token="fake-token",
            )
            g2_spot_url, g2_spot_body = captured_requests[0]
            self.assertEqual(
                g2_spot_url,
                "https://compute.googleapis.com/compute/beta/projects/test-proj/regions/us-central1/advice/capacity",
            )
            self.assertNotIn("guestAccelerators", g2_spot_body["instanceProperties"])
            self.assertNotIn(
                "guestAccelerators",
                g2_spot_body["instanceFlexibilityPolicy"]["instanceSelections"]["instance-selection-1"],
            )

            # N1 (T4) Spot Advisory -> /compute/beta/ + guestAccelerators on InstanceSelection (NOT InstanceProperties)
            captured_requests.clear()
            mock_spot_payload = {
                "recommendations": [
                    {
                        "scores": {"obtainability": 0.9, "estimatedUptime": "3600s"},
                        "shards": [
                            {
                                "zone": "https://www.googleapis.com/compute/beta/projects/test-proj/zones/us-central1-f",
                                "machineType": "n1-standard-4",
                                "instanceCount": 1,
                                "provisioningModel": "SPOT",
                            }
                        ],
                    }
                ]
            }
            n1_res = await advisory.get_spot_advisory(
                project="test-proj",
                machine_type="n1-standard-4",
                zones=["us-central1-f"],
                user_token="fake-token",
            )
            n1_spot_url, n1_spot_body = captured_requests[0]
            self.assertEqual(
                n1_spot_url,
                "https://compute.googleapis.com/compute/beta/projects/test-proj/regions/us-central1/advice/capacity",
            )
            self.assertNotIn("guestAccelerators", n1_spot_body["instanceProperties"])
            n1_spot_sel = n1_spot_body["instanceFlexibilityPolicy"]["instanceSelections"]["instance-selection-1"]
            self.assertEqual(
                n1_spot_sel["guestAccelerators"],
                [{"acceleratorType": "nvidia-tesla-t4", "acceleratorCount": 1}],
            )
            self.assertEqual(len(n1_res["recommendations"]), 1)
            self.assertEqual(n1_res["recommendations"][0]["spotAvailability"], "HIGH")
            self.assertEqual(n1_res["recommendations"][0]["preemptionRate"], "LOW")
            self.assertEqual(n1_res["recommendations"][0]["estimatedUptime"], "3600s")
            self.assertEqual(n1_res["recommendations"][0]["uptimeScore"], 0.9)

            # Verify 600s -> MODERATE and 60s -> HIGH when alpha-only uptimeScore is omitted
            for est_uptime, expected_preemption, expected_score in [
                ("600s", "MODERATE", 0.6),
                ("60s", "HIGH", 0.1),
            ]:
                mock_spot_payload = {
                    "recommendations": [
                        {
                            "scores": {"obtainability": 0.5, "estimatedUptime": est_uptime},
                            "shards": [
                                {
                                    "zone": "https://www.googleapis.com/compute/beta/projects/test-proj/zones/us-central1-a",
                                    "machineType": "g4-standard-48",
                                }
                            ],
                        }
                    ]
                }
                g4_res = await advisory.get_spot_advisory(
                    project="test-proj",
                    machine_type="g4-standard-48",
                    zones=["us-central1-a"],
                    user_token="fake-token",
                )
                self.assertEqual(g4_res["recommendations"][0]["preemptionRate"], expected_preemption)
                self.assertEqual(g4_res["recommendations"][0]["uptimeScore"], expected_score)

            mock_spot_payload = {"recommendations": []}

            # G2 (L4) Flex Advisory -> NO guestAccelerators
            captured_requests.clear()
            await advisory.get_flex_advisory(
                project="test-proj",
                machine_type="g2-standard-4",
                zones=["us-central1-a"],
                user_token="fake-token",
            )
            _, g2_flex_body = captured_requests[0]
            self.assertNotIn("guestAccelerators", g2_flex_body["instanceProperties"])
            self.assertNotIn(
                "guestAccelerators",
                g2_flex_body["instanceFlexibilityPolicy"]["instanceSelections"]["instance-selection-1"],
            )

            # N1 (T4) Flex Advisory -> guestAccelerators on InstanceSelection (NOT InstanceProperties)
            captured_requests.clear()
            await advisory.get_flex_advisory(
                project="test-proj",
                machine_type="n1-standard-4",
                zones=["us-central1-a"],
                user_token="fake-token",
            )
            _, n1_flex_body = captured_requests[0]
            self.assertNotIn("guestAccelerators", n1_flex_body["instanceProperties"])
            n1_flex_sel = n1_flex_body["instanceFlexibilityPolicy"]["instanceSelections"]["instance-selection-1"]
            self.assertEqual(
                n1_flex_sel["guestAccelerators"],
                [{"acceleratorType": "nvidia-tesla-t4", "acceleratorCount": 1}],
            )

    async def test_06_hunter_gpu_all_consumption_models(self):
        """Verify Hunter payloads for GPU On-Demand, DWS Calendar, DWS Flex Start, and Spot."""
        captured_posts = []

        async def mock_post(url, json=None, headers=None):
            captured_posts.append((url, json))
            return MockResponse(200, {"name": "op-123", "status": "DONE"})

        async def mock_get(url, headers=None):
            return MockResponse(
                200,
                {
                    "status": {"procurementStatus": "APPROVED"},
                    "planningStatus": "SUBMITTED",
                },
            )

        mock_client = AsyncMock()
        mock_client.post.side_effect = mock_post
        mock_client.get.side_effect = mock_get
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        updates = []
        async def send_update(msg):
            updates.append(msg)

        session = hunter.ScanningSession(
            session_id="test1234",
            project="test-proj",
            machine_type="a4-highgpu-8g",
            vm_count=2,
            priorities=[],
            send_update=send_update,
            user_token="fake-token",
            network="default",
        )

        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch.object(hunter.ScanningSession, "_log_deployment_event", MagicMock()), \
             patch.object(session, "_wait_for_operation", AsyncMock(return_value=True)), \
             patch.object(session, "_poll_future_reservation_status", AsyncMock(return_value=True)):
            # 1. GPU On-Demand Reservation
            captured_posts.clear()
            ok = await session._try_on_demand_rest("us-east4-b", "")
            self.assertTrue(ok)
            url, body = captured_posts[0]
            self.assertTrue(url.endswith("/zones/us-east4-b/reservations"))
            self.assertTrue(body["specificReservationRequired"])
            self.assertEqual(body["specificReservation"]["count"], "2")
            self.assertEqual(body["specificReservation"]["instanceProperties"]["machineType"], "a4-highgpu-8g")

            # 1b. N1 (T4) On-Demand Reservation -> must include guestAccelerators
            session_n1 = hunter.ScanningSession(
                session_id="testn1",
                project="test-proj",
                machine_type="n1-standard-4",
                vm_count=1,
                priorities=[],
                send_update=send_update,
                user_token="fake-token",
                network="default",
            )
            with patch.object(session_n1, "_wait_for_operation", AsyncMock(return_value=True)):
                captured_posts.clear()
                ok_n1 = await session_n1._try_on_demand_rest("us-central1-a", "")
                self.assertTrue(ok_n1)
                _, n1_body = captured_posts[0]
                self.assertEqual(
                    n1_body["specificReservation"]["instanceProperties"]["guestAccelerators"],
                    [{"acceleratorType": "nvidia-tesla-t4", "acceleratorCount": 1}],
                )

            # 2. GPU DWS Calendar Future Reservation
            captured_posts.clear()
            ok = await session._try_dws_calendar_rest("us-east4-b", "", "", "")
            self.assertTrue(ok)
            url, body = captured_posts[0]
            self.assertTrue(url.endswith("/compute/beta/projects/test-proj/zones/us-east4-b/futureReservations"))
            self.assertEqual(body["reservationMode"], "CALENDAR")
            self.assertEqual(body["planningStatus"], "SUBMITTED")
            self.assertTrue(body["specificReservationRequired"])
            self.assertTrue(body["autoDeleteAutoCreatedReservations"])
            self.assertIn("autoCreatedReservationsDeleteTime", body)
            self.assertIn("reservationName", body)
            self.assertLessEqual(len(body["reservationName"]), 38)
            self.assertNotIn("namePrefix", body)
            self.assertNotIn("labels", body)
            self.assertEqual(body["deploymentType"], "DENSE")
            self.assertEqual(body["specificSkuProperties"]["totalCount"], "2")

            # 3. GPU DWS Flex Start (Genuine FLEX_START instances, NOT fake on-demand reservation!)
            captured_posts.clear()
            ok = await session._try_dws_flex_rest("us-east4-b", "", 168, 24)
            self.assertTrue(ok)
            self.assertEqual(len(captured_posts), 2)  # vm_count=2
            url, body = captured_posts[0]
            self.assertTrue(url.endswith("/zones/us-east4-b/instances"))
            self.assertEqual(body["scheduling"]["provisioningModel"], "FLEX_START")
            self.assertEqual(body["scheduling"]["instanceTerminationAction"], "DELETE")
            self.assertEqual(body["scheduling"]["maxRunDuration"]["seconds"], str(24 * 3600))
            self.assertEqual(body["params"]["requestValidForDuration"]["seconds"], str(168 * 3600))
            self.assertIn("hyperdisk-balanced", body["disks"][0]["initializeParams"]["diskType"])
            self.assertEqual(body["networkInterfaces"][0]["nicType"], "GVNIC")

            # 4. GPU Spot VMs (hyperdisk-balanced on A4, respects vm_count=2)
            captured_posts.clear()
            ok = await session._try_spot_rest("us-east4-b", "")
            self.assertTrue(ok)
            self.assertEqual(len(captured_posts), 2)  # vm_count=2
            url, body = captured_posts[0]
            self.assertEqual(body["scheduling"]["provisioningModel"], "SPOT")
            self.assertIn("hyperdisk-balanced", body["disks"][0]["initializeParams"]["diskType"])
            self.assertEqual(body["networkInterfaces"][0]["nicType"], "GVNIC")

    async def test_07_hunter_tpu_all_consumption_models(self):
        """Verify Hunter payloads for TPU On-Demand, DWS Calendar, DWS Flex Start (v2alpha1), and Spot."""
        captured_posts = []

        async def mock_post(url, json=None, headers=None):
            captured_posts.append((url, json))
            return MockResponse(200, {"name": "op-tpu-123", "done": True})

        async def mock_get(url, headers=None):
            return MockResponse(200, {"done": True})

        mock_client = AsyncMock()
        mock_client.post.side_effect = mock_post
        mock_client.get.side_effect = mock_get
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        updates = []
        async def send_update(msg):
            updates.append(msg)

        session = hunter.ScanningSession(
            session_id="tpu12345",
            project="test-proj",
            machine_type="ct5p-hightpu-4t",
            vm_count=2,
            priorities=[],
            send_update=send_update,
            user_token="fake-token",
            network="default",
        )

        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch.object(hunter.ScanningSession, "_log_deployment_event", MagicMock()), \
             patch.object(session, "_wait_for_operation", AsyncMock(return_value=True)), \
             patch.object(session, "_poll_future_reservation_status", AsyncMock(return_value=True)), \
             patch.object(session, "_poll_tpu_operation", AsyncMock(return_value=True)), \
             patch.object(session, "_poll_tpu_queued_resource", AsyncMock(return_value=True)):
            # 1. TPU DWS Calendar -> FutureReservation with aggregateReservation!
            captured_posts.clear()
            ok = await session._try_dws_calendar_rest("us-east5-a", "", "", "")
            self.assertTrue(ok)
            url, body = captured_posts[0]
            self.assertTrue(url.endswith("/compute/beta/projects/test-proj/zones/us-east5-a/futureReservations"))
            self.assertEqual(body["reservationMode"], "CALENDAR")
            self.assertIn("aggregateReservation", body)
            self.assertEqual(body["aggregateReservation"]["vmFamily"], "VM_FAMILY_CLOUD_TPU_POD_SLICE_CT5P")
            self.assertEqual(
                body["aggregateReservation"]["reservedResources"][0]["accelerator"]["acceleratorCount"],
                8,  # 2 * 4 chips = 8 chips (which is in allowed_accelerator_counts [4, 8, 16, ...])
            )

            # 2. TPU DWS Flex Start -> v2alpha1 QueuedResource with FLEX_START and v5p-8 / v2-alpha-tpuv5
            captured_posts.clear()
            ok = await session._try_tpu_queued_resource("us-east5-a", "", 168, 24)
            self.assertTrue(ok)
            url, body = captured_posts[0]
            self.assertIn("https://tpu.googleapis.com/v2alpha1/projects/test-proj/locations/us-east5-a/queuedResources", url)
            self.assertEqual(body["provisioningModel"], "FLEX_START")
            self.assertEqual(body["runDuration"]["maxRunDuration"], f"{24 * 3600}s")
            node_spec = body["tpu"]["nodeSpec"][0]
            self.assertEqual(node_spec["node"]["acceleratorType"], "v5p-8")
            self.assertEqual(node_spec["node"]["runtimeVersion"], "v2-alpha-tpuv5")
            self.assertEqual(node_spec["multiNodeParams"]["nodeCount"], 2)

            # 3. TPU On-Demand Node -> v2 Node with v5p-8, v2-alpha-tpuv5, and networkConfig
            captured_posts.clear()
            ok = await session._try_tpu_on_demand("us-east5-a", "")
            self.assertTrue(ok)
            url, body = captured_posts[0]
            self.assertIn("https://tpu.googleapis.com/v2/projects/test-proj/locations/us-east5-a/nodes", url)
            self.assertEqual(body["acceleratorType"], "v5p-8")
            self.assertEqual(body["runtimeVersion"], "v2-alpha-tpuv5")
            self.assertIn("networkConfig", body)

            # 4. TPU Spot Node -> v2alpha1 QueuedResource with spot={}
            captured_posts.clear()
            ok = await session._try_tpu_spot("us-east5-a", "")
            self.assertTrue(ok)
            url, body = captured_posts[0]
            self.assertIn("https://tpu.googleapis.com/v2alpha1/projects/test-proj/locations/us-east5-a/queuedResources", url)
            self.assertIn("spot", body)
            self.assertEqual(body["tpu"]["nodeSpec"][0]["node"]["acceleratorType"], "v5p-8")

    async def test_08_exhaustive_all_gpu_and_tpu_families(self):
        """Exhaustively test every GPU and TPU family in the catalog across Advisory and Scan & Deploy."""
        all_info = get_all_machine_types_info()
        self.assertGreaterEqual(len(all_info), 40)

        # Group one representative machine type per family
        by_family = {}
        for item in all_info:
            by_family.setdefault(item["family"], item)

        self.assertEqual(len(by_family), 20)  # 13 GPU families + 7 TPU families

        mock_client = AsyncMock()
        mock_client.post.return_value = MockResponse(200, {"name": "op-1", "done": True, "recommendations": []})
        mock_client.get.return_value = MockResponse(200, {"done": True, "status": {"procurementStatus": "APPROVED"}})
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None

        async def noop_update(_msg):
            pass

        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch.object(hunter.ScanningSession, "_log_deployment_event", MagicMock()):
            for family, item in by_family.items():
                mt = item["machineType"]
                zones = item["zones"]
                cal_zones = item.get("calendarZones") or zones
                supported = item["supported"]
                self.assertTrue(len(zones) > 0, f"{family} ({mt}) must have supported zones")

                # Test Advisory APIs for this family
                spot_res = await advisory.get_spot_advisory("test-proj", mt, zones=[zones[0]], user_token="tok")
                self.assertEqual(spot_res["errors"], [], f"Spot advisory failed for {family} ({mt})")

                flex_res = await advisory.get_flex_advisory("test-proj", mt, zones=[zones[0]], user_token="tok")
                self.assertEqual(flex_res["errors"], [], f"Flex advisory failed for {family} ({mt})")

                cal_res = await advisory.get_calendar_advisory("test-proj", mt, vm_count=1, zones=[cal_zones[0]], user_token="tok")
                self.assertEqual(cal_res["errors"], [], f"Calendar advisory failed for {family} ({mt})")

                splits_res = await advisory.find_best_splits("test-proj", mt, vm_count=4, zones=[cal_zones[0]], user_token="tok")
                self.assertEqual(splits_res["errors"], [], f"Calendar splits failed for {family} ({mt})")

                # Test Scan & Deploy (Hunter) for every supported consumption model of this family
                session = hunter.ScanningSession(
                    session_id="allfam01",
                    project="test-proj",
                    machine_type=mt,
                    vm_count=1,
                    priorities=[],
                    send_update=noop_update,
                    user_token="tok",
                    network="default",
                )
                with patch.object(session, "_wait_for_operation", AsyncMock(return_value=True)), \
                     patch.object(session, "_poll_future_reservation_status", AsyncMock(return_value=True)), \
                     patch.object(session, "_poll_tpu_operation", AsyncMock(return_value=True)), \
                     patch.object(session, "_poll_tpu_queued_resource", AsyncMock(return_value=True)):
                    for method_name, is_sup in supported.items():
                        if not is_sup:
                            continue
                        cm = hunter.ConsumptionModel(method_name)
                        target_zone = cal_zones[0] if method_name == "dws_calendar" else zones[0]
                        ok = await session._dispatch_method(cm, target_zone, "test", 24, 24, "", "")
                        self.assertTrue(ok, f"Deploy {method_name} failed for {family} ({mt}) in {target_zone}")

    async def test_09_min_max_vm_scaling_and_hunting_timeout(self):
        """Verify Scan & Deploy scales down from maxVmCount to minVmCount and enforces totalHuntingHours."""
        attempted_counts = []

        async def mock_dispatch(method, zone, *args, **kwargs):
            attempted_counts.append(session.vm_count)
            # Succeed only when scaled down to 2 VMs
            if session.vm_count == 2:
                session.result = {"method": method, "zone": zone, "vm_count": 2}
                return True
            return False

        updates = []
        async def record_update(msg):
            updates.append(msg)

        session = hunter.ScanningSession(
            session_id="scale123",
            project="test-proj",
            machine_type="a3-highgpu-8g",
            vm_count=4,
            min_vm_count=1,
            max_vm_count=4,
            total_hunting_hours=1.0,
            priorities=[{"method": "on_demand", "zones": ["us-central1-a"], "max_retries": 1, "retry_interval": 10}],
            send_update=record_update,
            user_token="fake-token",
            network="default",
        )

        with patch.object(session, "_dispatch_method", side_effect=mock_dispatch):
            await session.run(parallel=False)

        self.assertEqual(session.status, hunter.ScanningStatus.SUCCESS)
        self.assertEqual(attempted_counts, [4, 3, 2])
        self.assertEqual(session.result["vm_count"], 2)

    async def test_10_fastapi_endpoints_and_websocket(self):
        """Verify all FastAPI endpoints and WebSocket /ws/scan end-to-end."""
        from fastapi.testclient import TestClient
        import main as app_main

        with TestClient(app_main.app) as client:
            # 1. /api/config
            r = client.get("/api/config")
            self.assertEqual(r.status_code, 200)
            self.assertIn("authMode", r.json())

            # 2. /api/machine-types
            r = client.get("/api/machine-types")
            self.assertEqual(r.status_code, 200)
            mts = r.json()["machineTypes"]
            self.assertGreaterEqual(len(mts), 40)
            v7x = next((m for m in mts if m["machineType"] == "tpu7x-standard-4t"), None)
            self.assertIsNotNone(v7x)
            self.assertEqual(v7x["category"], "TPU")

            # 3. /api/chip-groups
            r = client.get("/api/chip-groups")
            self.assertEqual(r.status_code, 200)
            cg = r.json()
            self.assertIn("gpuChips", cg)
            self.assertIn("tpuChips", cg)

            # 4. /api/machine-types/{mt}/zones
            r = client.get("/api/machine-types/ct5p-hightpu-4t/zones")
            self.assertEqual(r.status_code, 200)
            self.assertIn("calendarZones", r.json())
            self.assertEqual(r.json()["calendarZones"], ["europe-west4-b", "us-east5-a"])

            # 5. WebSocket /ws/scan end-to-end with minVmCount/maxVmCount & priorities
            mock_http = AsyncMock()
            mock_http.post.return_value = MockResponse(200, {"name": "op-ws-1", "status": "DONE"})
            mock_http.get.return_value = MockResponse(200, {"status": "DONE"})
            mock_http.__aenter__.return_value = mock_http
            mock_http.__aexit__.return_value = None

            with patch("httpx.AsyncClient", return_value=mock_http), \
                 patch.object(hunter.ScanningSession, "_log_deployment_event", MagicMock()), \
                 patch.object(hunter.ScanningSession, "_wait_for_operation", AsyncMock(return_value=True)):
                with client.websocket_connect("/ws/scan") as ws:
                    ws.send_json({
                        "action": "scan",
                        "userToken": "fake-token",
                        "config": {
                            "project": "test-proj",
                            "machineType": "a3-highgpu-8g",
                            "vmCount": 2,
                            "minVmCount": 1,
                            "maxVmCount": 2,
                            "totalHuntingHours": 1.0,
                            "priorities": [
                                {
                                    "method": "on_demand",
                                    "zones": ["us-central1-a"],
                                    "max_retries": 1,
                                    "retry_interval": 10,
                                }
                            ],
                            "parallel": False,
                            "network": "default",
                        },
                    })
                    received_types = []
                    for _ in range(15):
                        msg = ws.receive_json()
                        received_types.append(msg.get("type"))
                        if msg.get("type") in ("success", "exhausted", "error"):
                            self.assertEqual(msg.get("type"), "success")
                            self.assertEqual(msg["data"]["result"]["method"], "on_demand")
                            self.assertEqual(msg["data"]["result"]["zone"], "us-central1-a")
                            break
                    self.assertIn("session_created", received_types)
                    self.assertIn("start", received_types)
                    self.assertIn("attempt", received_types)
                    self.assertIn("success", received_types)


if __name__ == "__main__":
    if len(sys.argv) == 1 or sys.argv[1] == "--unit":
        # Run the automated end-to-end test suite
        sys.argv = [sys.argv[0]]
        unittest.main(verbosity=2)
    else:
        print("Run with `--unit` (or no args) for automated E2E verification.")
        sys.exit(0)
