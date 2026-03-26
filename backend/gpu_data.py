"""
GPU/TPU data: machine types, supported zones, and consumption model compatibility.
Source: Reservation_Script.docx reference tables.
"""

# Machine type families with their GPU info
MACHINE_TYPES = {
    # A4X Max (GB300) — bare metal
    "a4x-maxgpu-4g-metal": {
        "gpu": "NVIDIA GB300",
        "chip": "GB300",
        "gpu_count": 4,
        "family": "A4X Max",
        "category": "GPU",
        "accelerator_type": None,
    },
    # A4X (GB200)
    "a4x-highgpu-4g": {
        "gpu": "NVIDIA GB200",
        "chip": "GB200",
        "gpu_count": 4,
        "family": "A4X",
        "category": "GPU",
        "accelerator_type": None,
    },
    # A4 (B200)
    "a4-highgpu-8g": {
        "gpu": "NVIDIA B200",
        "chip": "B200",
        "gpu_count": 8,
        "family": "A4",
        "category": "GPU",
        "accelerator_type": None,
    },
    # A3 Ultra (H200)
    "a3-ultragpu-8g": {
        "gpu": "NVIDIA H200",
        "chip": "H200",
        "gpu_count": 8,
        "family": "A3 Ultra",
        "category": "GPU",
        "accelerator_type": None,
    },
    # A3 Mega (H100 80GB)
    "a3-megagpu-8g": {
        "gpu": "NVIDIA H100 80GB",
        "chip": "H100",
        "gpu_count": 8,
        "family": "A3 Mega",
        "category": "GPU",
        "accelerator_type": None,
    },
    # A3 Edge (H100 80GB)
    "a3-edgegpu-8g": {
        "gpu": "NVIDIA H100 80GB",
        "chip": "H100",
        "gpu_count": 8,
        "family": "A3 Edge",
        "category": "GPU",
        "accelerator_type": None,
    },
    # A3 High (H100 80GB)
    "a3-highgpu-1g": {
        "gpu": "NVIDIA H100 80GB",
        "chip": "H100",
        "gpu_count": 1,
        "family": "A3 High",
        "category": "GPU",
        "accelerator_type": None,
    },
    "a3-highgpu-2g": {
        "gpu": "NVIDIA H100 80GB",
        "chip": "H100",
        "gpu_count": 2,
        "family": "A3 High",
        "category": "GPU",
        "accelerator_type": None,
    },
    "a3-highgpu-4g": {
        "gpu": "NVIDIA H100 80GB",
        "chip": "H100",
        "gpu_count": 4,
        "family": "A3 High",
        "category": "GPU",
        "accelerator_type": None,
    },
    "a3-highgpu-8g": {
        "gpu": "NVIDIA H100 80GB",
        "chip": "H100",
        "gpu_count": 8,
        "family": "A3 High",
        "category": "GPU",
        "accelerator_type": None,
    },
    # A2 Ultra (A100 80GB)
    "a2-ultragpu-1g": {
        "gpu": "NVIDIA A100 80GB",
        "chip": "A100 80GB",
        "gpu_count": 1,
        "family": "A2 Ultra",
        "category": "GPU",
        "accelerator_type": None,
    },
    "a2-ultragpu-2g": {
        "gpu": "NVIDIA A100 80GB",
        "chip": "A100 80GB",
        "gpu_count": 2,
        "family": "A2 Ultra",
        "category": "GPU",
        "accelerator_type": None,
    },
    "a2-ultragpu-4g": {
        "gpu": "NVIDIA A100 80GB",
        "chip": "A100 80GB",
        "gpu_count": 4,
        "family": "A2 Ultra",
        "category": "GPU",
        "accelerator_type": None,
    },
    "a2-ultragpu-8g": {
        "gpu": "NVIDIA A100 80GB",
        "chip": "A100 80GB",
        "gpu_count": 8,
        "family": "A2 Ultra",
        "category": "GPU",
        "accelerator_type": None,
    },
    # A2 Standard (A100 40GB)
    "a2-highgpu-1g": {
        "gpu": "NVIDIA A100 40GB",
        "chip": "A100 40GB",
        "gpu_count": 1,
        "family": "A2 Standard",
        "category": "GPU",
        "accelerator_type": None,
    },
    "a2-highgpu-2g": {
        "gpu": "NVIDIA A100 40GB",
        "chip": "A100 40GB",
        "gpu_count": 2,
        "family": "A2 Standard",
        "category": "GPU",
        "accelerator_type": None,
    },
    "a2-highgpu-4g": {
        "gpu": "NVIDIA A100 40GB",
        "chip": "A100 40GB",
        "gpu_count": 4,
        "family": "A2 Standard",
        "category": "GPU",
        "accelerator_type": None,
    },
    "a2-highgpu-8g": {
        "gpu": "NVIDIA A100 40GB",
        "chip": "A100 40GB",
        "gpu_count": 8,
        "family": "A2 Standard",
        "category": "GPU",
        "accelerator_type": None,
    },
    "a2-megagpu-16g": {
        "gpu": "NVIDIA A100 40GB",
        "chip": "A100 40GB",
        "gpu_count": 16,
        "family": "A2 Mega",
        "category": "GPU",
        "accelerator_type": None,
    },
    # G4 (RTX PRO 6000)
    "g4-standard-6": {
        "gpu": "NVIDIA RTX PRO 6000",
        "chip": "RTX PRO 6000",
        "gpu_count": 1,
        "family": "G4",
        "category": "GPU",
        "accelerator_type": None,
    },
    "g4-standard-12": {
        "gpu": "NVIDIA RTX PRO 6000",
        "chip": "RTX PRO 6000",
        "gpu_count": 1,
        "family": "G4",
        "category": "GPU",
        "accelerator_type": None,
    },
    "g4-standard-24": {
        "gpu": "NVIDIA RTX PRO 6000",
        "chip": "RTX PRO 6000",
        "gpu_count": 1,
        "family": "G4",
        "category": "GPU",
        "accelerator_type": None,
    },
    "g4-standard-48": {
        "gpu": "NVIDIA RTX PRO 6000",
        "chip": "RTX PRO 6000",
        "gpu_count": 1,
        "family": "G4",
        "category": "GPU",
        "accelerator_type": None,
    },
    "g4-standard-96": {
        "gpu": "NVIDIA RTX PRO 6000",
        "chip": "RTX PRO 6000",
        "gpu_count": 2,
        "family": "G4",
        "category": "GPU",
        "accelerator_type": None,
    },
    "g4-standard-192": {
        "gpu": "NVIDIA RTX PRO 6000",
        "chip": "RTX PRO 6000",
        "gpu_count": 4,
        "family": "G4",
        "category": "GPU",
        "accelerator_type": None,
    },
    "g4-standard-384": {
        "gpu": "NVIDIA RTX PRO 6000",
        "chip": "RTX PRO 6000",
        "gpu_count": 8,
        "family": "G4",
        "category": "GPU",
        "accelerator_type": None,
    },
    # G2 (L4)
    "g2-standard-4": {
        "gpu": "NVIDIA L4",
        "chip": "L4",
        "gpu_count": 1,
        "family": "G2",
        "category": "GPU",
        "accelerator_type": "nvidia-l4",
    },
    "g2-standard-8": {
        "gpu": "NVIDIA L4",
        "chip": "L4",
        "gpu_count": 1,
        "family": "G2",
        "category": "GPU",
        "accelerator_type": "nvidia-l4",
    },
    "g2-standard-12": {
        "gpu": "NVIDIA L4",
        "chip": "L4",
        "gpu_count": 1,
        "family": "G2",
        "category": "GPU",
        "accelerator_type": "nvidia-l4",
    },
    "g2-standard-16": {
        "gpu": "NVIDIA L4",
        "chip": "L4",
        "gpu_count": 1,
        "family": "G2",
        "category": "GPU",
        "accelerator_type": "nvidia-l4",
    },
    "g2-standard-24": {
        "gpu": "NVIDIA L4",
        "chip": "L4",
        "gpu_count": 2,
        "family": "G2",
        "category": "GPU",
        "accelerator_type": "nvidia-l4",
    },
    "g2-standard-32": {
        "gpu": "NVIDIA L4",
        "chip": "L4",
        "gpu_count": 1,
        "family": "G2",
        "category": "GPU",
        "accelerator_type": "nvidia-l4",
    },
    "g2-standard-48": {
        "gpu": "NVIDIA L4",
        "chip": "L4",
        "gpu_count": 4,
        "family": "G2",
        "category": "GPU",
        "accelerator_type": "nvidia-l4",
    },
    "g2-standard-96": {
        "gpu": "NVIDIA L4",
        "chip": "L4",
        "gpu_count": 8,
        "family": "G2",
        "category": "GPU",
        "accelerator_type": "nvidia-l4",
    },
}

# GPU type to supported zones mapping
GPU_ZONES = {
    "A4X Max (GB300)": [
        "us-central1-b", "us-east4-b", "us-east5-c"
    ],
    "A4X (GB200)": [
        "us-central1-a"
    ],
    "A4 (B200)": [
        "asia-northeast1-b", "asia-southeast1-b", "europe-west4-b",
        "us-central1-b", "us-east1-b", "us-east4-b", "us-south1-b",
        "us-west2-c", "us-west3-b", "us-west3-c"
    ],
    "A3 Ultra (H200)": [
        "asia-south1-b", "asia-south2-c", "europe-west1-b", "europe-west4-a",
        "us-central1-b", "us-east1-d", "us-east4-b", "us-east5-a",
        "us-south1-b", "us-west1-c"
    ],
    "A3 Edge (H100)": [
        "asia-east1-a", "asia-east1-b", "asia-east1-c",
        "asia-northeast1-b", "asia-southeast1-a", "asia-southeast1-b",
        "europe-west1-b", "europe-west1-c", "europe-west4-a", "europe-west4-b",
        "me-west1-b",
        "us-central1-a", "us-central1-b", "us-central1-c",
        "us-east1-b", "us-east1-c", "us-east4-a", "us-east4-b",
        "us-west1-a", "us-west1-b"
    ],
    "A3 Mega (H100)": [
        "asia-east1-c", "asia-northeast1-b", "asia-southeast1-b",
        "asia-southeast1-c", "australia-southeast1-c", "europe-west1-b",
        "europe-west1-c", "europe-west4-b", "europe-west4-c",
        "us-central1-a", "us-central1-b", "us-central1-c",
        "us-east4-a", "us-east4-b", "us-east4-c", "us-east5-a",
        "us-west1-a", "us-west1-b", "us-west4-a"
    ],
    "A3 High (H100)": [
        "asia-east1-c", "asia-northeast1-b", "asia-southeast1-b",
        "asia-southeast1-c", "europe-west1-b", "europe-west1-c",
        "europe-west4-c", "us-central1-a", "us-central1-c",
        "us-east4-a", "us-east4-b", "us-east5-a",
        "us-west1-a", "us-west1-b", "us-west4-a"
    ],
    "A2 Ultra (A100 80GB)": [
        "asia-southeast1-c", "europe-west4-a", "us-central1-a",
        "us-central1-c", "us-east4-c", "us-east5-a"
    ],
    "A2 Standard (A100 40GB)": [
        "asia-northeast1-a", "asia-northeast1-c", "asia-northeast3-b",
        "asia-southeast1-b", "asia-southeast1-c", "europe-west4-a",
        "europe-west4-b", "me-west1-a", "me-west1-c",
        "us-central1-a", "us-central1-b", "us-central1-c", "us-central1-f",
        "us-east1-b", "us-west1-b", "us-west3-b", "us-west4-b"
    ],
    "G4 (RTX PRO 6000)": [
        "asia-south2-c", "asia-southeast1-b", "asia-southeast1-c",
        "asia-southeast2-b", "asia-southeast2-c", "europe-north1-a",
        "europe-west1-c", "europe-west2-b", "europe-west4-a", "europe-west4-b",
        "europe-west4-c", "europe-west8-b", "us-central1-b", "us-central1-f",
        "us-east1-b", "us-east4-c", "us-east5-a", "us-east5-b", "us-east5-c",
        "us-south1-a", "us-south1-b", "us-west1-b", "us-west1-c",
        "us-west3-a", "us-west4-a"
    ],
    "G2 (L4)": [
        "asia-east1-a", "asia-east1-b", "asia-east1-c",
        "asia-northeast1-a", "asia-northeast1-b", "asia-northeast1-c",
        "asia-northeast3-a", "asia-northeast3-b",
        "asia-south1-a", "asia-south1-b", "asia-south1-c",
        "asia-southeast1-a", "asia-southeast1-b", "asia-southeast1-c",
        "europe-west1-b", "europe-west1-c",
        "europe-west2-a", "europe-west2-b",
        "europe-west3-a", "europe-west3-b",
        "europe-west4-a", "europe-west4-b", "europe-west4-c",
        "europe-west6-b", "europe-west6-c",
        "me-central2-a", "me-central2-c",
        "northamerica-northeast2-a", "northamerica-northeast2-b",
        "us-central1-a", "us-central1-b", "us-central1-c", "us-central1-f",
        "us-east1-b", "us-east1-c",
        "us-east4-a", "us-east4-c",
        "us-west1-a", "us-west1-b", "us-west1-c",
        "us-west4-a", "us-west4-c"
    ],
}

# Map machine type to its family for zone lookup
MACHINE_TO_FAMILY = {mt: info["family"] for mt, info in MACHINE_TYPES.items()}

# Which families map to which GPU_ZONES key
FAMILY_TO_GPU_ZONE_KEY = {
    "A4X Max": "A4X Max (GB300)",
    "A4X": "A4X (GB200)",
    "A4": "A4 (B200)",
    "A3 Ultra": "A3 Ultra (H200)",
    "A3 Edge": "A3 Edge (H100)",
    "A3 Mega": "A3 Mega (H100)",
    "A3 High": "A3 High (H100)",
    "A2 Ultra": "A2 Ultra (A100 80GB)",
    "A2 Standard": "A2 Standard (A100 40GB)",
    "A2 Mega": "A2 Standard (A100 40GB)",
    "G4": "G4 (RTX PRO 6000)",
    "G2": "G2 (L4)",
}

# Consumption model support matrix
CONSUMPTION_SUPPORT = {
    "on_demand": {
        "A4X Max": False, "A4X": True, "A4": False,
        "A3 Ultra": False, "A3 Edge": True, "A3 Mega": True, "A3 High": True,
        "A2 Ultra": True, "A2 Standard": True, "A2 Mega": True,
        "G4": True, "G2": True,
    },
    "spot": {
        "A4X Max": True, "A4X": True, "A4": True,
        "A3 Ultra": True, "A3 Edge": True, "A3 Mega": True, "A3 High": True,
        "A2 Ultra": True, "A2 Standard": True, "A2 Mega": True,
        "G4": True, "G2": True,
    },
    "dws_calendar": {
        "A4X Max": False, "A4X": False, "A4": True,
        "A3 Ultra": True, "A3 Edge": True, "A3 Mega": True, "A3 High": True,
        "A2 Ultra": False, "A2 Standard": False, "A2 Mega": False,
        "G4": False, "G2": False,
    },
    "dws_flex": {
        "A4X Max": True, "A4X": True, "A4": True,
        "A3 Ultra": True, "A3 Edge": True, "A3 Mega": True, "A3 High": True,
        "A2 Ultra": False, "A2 Standard": False, "A2 Mega": False,
        "G4": False, "G2": False,
    },
}

# TPU types, zones, machine types, and consumption model support
TPU_TYPES = {
    "v6e": {
        "gpu": "Cloud TPU v6e (Trillium)",
        "accelerator_prefix": "v6e",
        "zones": ["asia-northeast1-b", "europe-west4-a", "southamerica-west1-a",
                   "us-central1-b", "us-east1-d", "us-east5-a", "us-east5-b"],
        "machine_types": {
            "ct6e-standard-1t": {"chips": 1, "vcpus": 44, "memory_gb": 176, "hbm_gb": 32},
            "ct6e-standard-4t": {"chips": 4, "vcpus": 180, "memory_gb": 720, "hbm_gb": 128},
            "ct6e-standard-8t": {"chips": 8, "vcpus": 180, "memory_gb": 1440, "hbm_gb": 256},
        },
        "topologies": ["1x1", "2x2", "2x4", "4x4", "4x8", "8x8", "8x16", "16x16"],
        "supported": {"on_demand": True, "spot": True, "dws_calendar": True, "dws_flex": True},
    },
    "v5p": {
        "gpu": "Cloud TPU v5p (Viperfish)",
        "accelerator_prefix": "v5p",
        "zones": ["europe-west4-b", "us-central1-a", "us-east5-a"],
        "machine_types": {
            "ct5p-hightpu-1t": {"chips": 1, "vcpus": 52, "memory_gb": 112, "hbm_gb": 95},
            "ct5p-hightpu-2t": {"chips": 2, "vcpus": 104, "memory_gb": 224, "hbm_gb": 190},
            "ct5p-hightpu-4t": {"chips": 4, "vcpus": 208, "memory_gb": 448, "hbm_gb": 380},
        },
        "topologies": ["2x2x1", "2x2x2", "2x2x4", "2x4x4", "4x4x4"],
        "supported": {"on_demand": True, "spot": True, "dws_calendar": True, "dws_flex": True},
    },
    "v5e": {
        "gpu": "Cloud TPU v5e (Viperlite)",
        "accelerator_prefix": "v5litepod",
        "zones": ["europe-west4-b", "us-central1-a", "us-south1-a",
                   "us-west1-c", "us-west4-a"],
        "machine_types": {
            "ct5e-hightpu-1t": {"chips": 1, "vcpus": 24, "memory_gb": 48, "hbm_gb": 16},
            "ct5e-hightpu-4t": {"chips": 4, "vcpus": 112, "memory_gb": 192, "hbm_gb": 64},
            "ct5e-hightpu-8t": {"chips": 8, "vcpus": 224, "memory_gb": 384, "hbm_gb": 128},
        },
        "topologies": ["1x1", "2x2", "2x4", "4x4", "4x8", "8x8", "8x16", "16x16"],
        "supported": {"on_demand": True, "spot": True, "dws_calendar": True, "dws_flex": True},
    },
    "v4": {
        "gpu": "Cloud TPU v4 (Pufferfish)",
        "accelerator_prefix": "v4",
        "zones": ["us-central2-b"],
        "machine_types": {
            "ct4p-hightpu-4t": {"chips": 4, "vcpus": 240, "memory_gb": 408, "hbm_gb": 128},
        },
        "topologies": ["2x2x1", "2x2x2", "2x2x4", "2x4x4", "4x4x4"],
        "supported": {"on_demand": True, "spot": True, "dws_calendar": False, "dws_flex": True},
    },
    "v3": {
        "gpu": "Cloud TPU v3 (Dragonfish)",
        "accelerator_prefix": "v3",
        "zones": ["europe-west4-a", "us-central1-a", "us-central1-b"],
        "machine_types": {
            "v3-8": {"chips": 4, "vcpus": 96, "memory_gb": 340, "hbm_gb": 64},
        },
        "topologies": ["2x2", "4x4", "4x8", "8x8"],
        "supported": {"on_demand": True, "spot": True, "dws_calendar": False, "dws_flex": False},
    },
    "v2": {
        "gpu": "Cloud TPU v2 (Jellyfish)",
        "accelerator_prefix": "v2",
        "zones": ["asia-east1-c", "europe-west4-a", "us-central1-a",
                   "us-central1-b", "us-central1-c"],
        "machine_types": {
            "v2-8": {"chips": 4, "vcpus": 96, "memory_gb": 340, "hbm_gb": 32},
        },
        "topologies": ["2x2", "4x4", "4x8", "8x8"],
        "supported": {"on_demand": True, "spot": True, "dws_calendar": False, "dws_flex": False},
    },
}


def get_zones_for_machine_type(machine_type: str) -> list[str]:
    """Get supported zones for a given machine type (GPU or TPU)."""
    # Check TPU machine types (ct6e-standard-1t, ct5p-hightpu-4t, v3-8, etc.)
    for tpu_type, tpu_info in TPU_TYPES.items():
        if machine_type in tpu_info.get("machine_types", {}):
            return tpu_info["zones"]
    # GPU machine types
    family = MACHINE_TO_FAMILY.get(machine_type)
    if not family:
        return []
    gpu_zone_key = FAMILY_TO_GPU_ZONE_KEY.get(family)
    if not gpu_zone_key:
        return []
    return GPU_ZONES.get(gpu_zone_key, [])


def is_consumption_supported(machine_type: str, consumption_model: str) -> bool:
    """Check if a consumption model is supported for a given machine type."""
    # Check TPU types first
    for tpu_type, tpu_info in TPU_TYPES.items():
        if machine_type in tpu_info.get("machine_types", {}):
            return tpu_info.get("supported", {}).get(consumption_model, False)
    # GPU types
    family = MACHINE_TO_FAMILY.get(machine_type)
    if not family:
        return False
    model_support = CONSUMPTION_SUPPORT.get(consumption_model, {})
    return model_support.get(family, False)


def get_all_machine_types_info() -> list[dict]:
    """Return all machine types with their info for the frontend."""
    result = []
    for mt, info in MACHINE_TYPES.items():
        family = info["family"]
        gpu_zone_key = FAMILY_TO_GPU_ZONE_KEY.get(family, "")
        zones = GPU_ZONES.get(gpu_zone_key, [])
        regions = sorted(set(z.rsplit("-", 1)[0] for z in zones))
        result.append({
            "machineType": mt,
            "gpu": info["gpu"],
            "chip": info.get("chip", ""),
            "gpuCount": info["gpu_count"],
            "family": family,
            "category": info.get("category", "GPU"),
            "zones": zones,
            "regions": regions,
            "supported": {
                "on_demand": is_consumption_supported(mt, "on_demand"),
                "spot": is_consumption_supported(mt, "spot"),
                "dws_calendar": is_consumption_supported(mt, "dws_calendar"),
                "dws_flex": is_consumption_supported(mt, "dws_flex"),
            }
        })
    # Add TPU entries from machine_types
    for tpu_type, tpu_info in TPU_TYPES.items():
        supported = tpu_info.get("supported", {})
        for mt_name, mt_spec in tpu_info.get("machine_types", {}).items():
            result.append({
                "machineType": mt_name,
                "gpu": tpu_info.get("gpu", f"Cloud TPU {tpu_type}"),
                "chip": tpu_type,
                "gpuCount": mt_spec["chips"],
                "family": f"TPU {tpu_type}",
                "category": "TPU",
                "zones": tpu_info["zones"],
                "regions": sorted(set(z.rsplit("-", 1)[0] for z in tpu_info["zones"])),
                "vcpus": mt_spec.get("vcpus"),
                "memoryGb": mt_spec.get("memory_gb"),
                "hbmGb": mt_spec.get("hbm_gb"),
                "topologies": tpu_info.get("topologies", []),
                "supported": supported,
            })
    return result


def get_chip_groups() -> dict:
    """Return machine types grouped by chip for the multi-step selector."""
    gpu_chips = {}  # chip_name -> list of machine types
    for mt, info in MACHINE_TYPES.items():
        chip = info.get("chip", info["gpu"])
        category = info.get("category", "GPU")
        if category != "GPU":
            continue
        if chip not in gpu_chips:
            gpu_chips[chip] = {
                "chip": chip,
                "gpu": info["gpu"],
                "category": "GPU",
                "machineTypes": [],
            }
        family = info["family"]
        gpu_zone_key = FAMILY_TO_GPU_ZONE_KEY.get(family, "")
        zones = GPU_ZONES.get(gpu_zone_key, [])
        gpu_chips[chip]["machineTypes"].append({
            "machineType": mt,
            "gpuCount": info["gpu_count"],
            "family": family,
            "zones": zones,
            "regions": sorted(set(z.rsplit("-", 1)[0] for z in zones)),
        })

    tpu_chips = {}
    for tpu_type, tpu_info in TPU_TYPES.items():
        tpu_chips[tpu_type] = {
            "chip": tpu_type,
            "gpu": f"Cloud TPU {tpu_type}",
            "category": "TPU",
            "zones": tpu_info["zones"],
            "regions": sorted(set(z.rsplit("-", 1)[0] for z in tpu_info["zones"])),
        }

    return {
        "gpuChips": list(gpu_chips.values()),
        "tpuChips": list(tpu_chips.values()),
    }
