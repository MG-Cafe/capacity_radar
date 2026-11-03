"""
GPU/TPU data: machine types, supported zones, calendar constraints, and consumption model compatibility.
Synchronized with Google Cloud Compute Engine & Cloud TPU production configurations.
"""

# Machine type families with their GPU and disk/network requirements
MACHINE_TYPES = {
    # A4X Max (GB300) — bare metal
    "a4x-maxgpu-4g-metal": {
        "gpu": "NVIDIA GB300",
        "chip": "GB300",
        "gpu_count": 4,
        "family": "A4X Max",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": True,
        "default_boot_disk_type": "hyperdisk-balanced",
    },
    # A4X (GB200)
    "a4x-highgpu-4g": {
        "gpu": "NVIDIA GB200",
        "chip": "GB200",
        "gpu_count": 4,
        "family": "A4X",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": True,
        "default_boot_disk_type": "hyperdisk-balanced",
    },
    # A4 (B200)
    "a4-highgpu-8g": {
        "gpu": "NVIDIA B200",
        "chip": "B200",
        "gpu_count": 8,
        "family": "A4",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": True,
        "default_boot_disk_type": "hyperdisk-balanced",
    },
    # A3 Ultra (H200)
    "a3-ultragpu-8g": {
        "gpu": "NVIDIA H200",
        "chip": "H200",
        "gpu_count": 8,
        "family": "A3 Ultra",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": True,
        "default_boot_disk_type": "hyperdisk-balanced",
    },
    # A3 Mega (H100 80GB)
    "a3-megagpu-8g": {
        "gpu": "NVIDIA H100 80GB",
        "chip": "H100",
        "gpu_count": 8,
        "family": "A3 Mega",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    # A3 Edge (H100 80GB)
    "a3-edgegpu-8g": {
        "gpu": "NVIDIA H100 80GB",
        "chip": "H100",
        "gpu_count": 8,
        "family": "A3 Edge",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    # A3 High (H100 80GB)
    "a3-highgpu-1g": {
        "gpu": "NVIDIA H100 80GB",
        "chip": "H100",
        "gpu_count": 1,
        "family": "A3 High",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "a3-highgpu-2g": {
        "gpu": "NVIDIA H100 80GB",
        "chip": "H100",
        "gpu_count": 2,
        "family": "A3 High",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "a3-highgpu-4g": {
        "gpu": "NVIDIA H100 80GB",
        "chip": "H100",
        "gpu_count": 4,
        "family": "A3 High",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "a3-highgpu-8g": {
        "gpu": "NVIDIA H100 80GB",
        "chip": "H100",
        "gpu_count": 8,
        "family": "A3 High",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    # A2 Ultra (A100 80GB)
    "a2-ultragpu-1g": {
        "gpu": "NVIDIA A100 80GB",
        "chip": "A100 80GB",
        "gpu_count": 1,
        "family": "A2 Ultra",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "a2-ultragpu-2g": {
        "gpu": "NVIDIA A100 80GB",
        "chip": "A100 80GB",
        "gpu_count": 2,
        "family": "A2 Ultra",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "a2-ultragpu-4g": {
        "gpu": "NVIDIA A100 80GB",
        "chip": "A100 80GB",
        "gpu_count": 4,
        "family": "A2 Ultra",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "a2-ultragpu-8g": {
        "gpu": "NVIDIA A100 80GB",
        "chip": "A100 80GB",
        "gpu_count": 8,
        "family": "A2 Ultra",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    # A2 Standard (A100 40GB)
    "a2-highgpu-1g": {
        "gpu": "NVIDIA A100 40GB",
        "chip": "A100 40GB",
        "gpu_count": 1,
        "family": "A2 Standard",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "a2-highgpu-2g": {
        "gpu": "NVIDIA A100 40GB",
        "chip": "A100 40GB",
        "gpu_count": 2,
        "family": "A2 Standard",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "a2-highgpu-4g": {
        "gpu": "NVIDIA A100 40GB",
        "chip": "A100 40GB",
        "gpu_count": 4,
        "family": "A2 Standard",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "a2-highgpu-8g": {
        "gpu": "NVIDIA A100 40GB",
        "chip": "A100 40GB",
        "gpu_count": 8,
        "family": "A2 Standard",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "a2-megagpu-16g": {
        "gpu": "NVIDIA A100 40GB",
        "chip": "A100 40GB",
        "gpu_count": 16,
        "family": "A2 Mega",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    # G4 (RTX PRO 6000) — built-in GPU in machine type; requires hyperdisk + GVNIC
    "g4-standard-6": {
        "gpu": "NVIDIA RTX PRO 6000",
        "chip": "RTX PRO 6000",
        "gpu_count": 1,
        "family": "G4",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": True,
        "default_boot_disk_type": "hyperdisk-balanced",
    },
    "g4-standard-12": {
        "gpu": "NVIDIA RTX PRO 6000",
        "chip": "RTX PRO 6000",
        "gpu_count": 1,
        "family": "G4",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": True,
        "default_boot_disk_type": "hyperdisk-balanced",
    },
    "g4-standard-24": {
        "gpu": "NVIDIA RTX PRO 6000",
        "chip": "RTX PRO 6000",
        "gpu_count": 1,
        "family": "G4",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": True,
        "default_boot_disk_type": "hyperdisk-balanced",
    },
    "g4-standard-48": {
        "gpu": "NVIDIA RTX PRO 6000",
        "chip": "RTX PRO 6000",
        "gpu_count": 1,
        "family": "G4",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": True,
        "default_boot_disk_type": "hyperdisk-balanced",
    },
    "g4-standard-96": {
        "gpu": "NVIDIA RTX PRO 6000",
        "chip": "RTX PRO 6000",
        "gpu_count": 2,
        "family": "G4",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": True,
        "default_boot_disk_type": "hyperdisk-balanced",
    },
    "g4-standard-192": {
        "gpu": "NVIDIA RTX PRO 6000",
        "chip": "RTX PRO 6000",
        "gpu_count": 4,
        "family": "G4",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": True,
        "default_boot_disk_type": "hyperdisk-balanced",
    },
    "g4-standard-384": {
        "gpu": "NVIDIA RTX PRO 6000",
        "chip": "RTX PRO 6000",
        "gpu_count": 8,
        "family": "G4",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": True,
        "default_boot_disk_type": "hyperdisk-balanced",
    },
    # G2 (L4) — built-in GPU in machine type (NOT guest-attached in Capacity Advisory / Instances API)
    "g2-standard-4": {
        "gpu": "NVIDIA L4",
        "chip": "L4",
        "gpu_count": 1,
        "family": "G2",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "g2-standard-8": {
        "gpu": "NVIDIA L4",
        "chip": "L4",
        "gpu_count": 1,
        "family": "G2",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "g2-standard-12": {
        "gpu": "NVIDIA L4",
        "chip": "L4",
        "gpu_count": 1,
        "family": "G2",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "g2-standard-16": {
        "gpu": "NVIDIA L4",
        "chip": "L4",
        "gpu_count": 1,
        "family": "G2",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "g2-standard-24": {
        "gpu": "NVIDIA L4",
        "chip": "L4",
        "gpu_count": 2,
        "family": "G2",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "g2-standard-32": {
        "gpu": "NVIDIA L4",
        "chip": "L4",
        "gpu_count": 1,
        "family": "G2",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "g2-standard-48": {
        "gpu": "NVIDIA L4",
        "chip": "L4",
        "gpu_count": 4,
        "family": "G2",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "g2-standard-96": {
        "gpu": "NVIDIA L4",
        "chip": "L4",
        "gpu_count": 8,
        "family": "G2",
        "category": "GPU",
        "accelerator_type": None,
        "guest_attached_gpu": False,
        "requires_gvnic": True,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    # N1 (T4) — true guest-attached accelerator GPUs
    "n1-standard-4": {
        "gpu": "NVIDIA T4",
        "chip": "T4",
        "gpu_count": 1,
        "family": "N1",
        "category": "GPU",
        "accelerator_type": "nvidia-tesla-t4",
        "guest_attached_gpu": True,
        "requires_gvnic": False,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "n1-standard-8": {
        "gpu": "NVIDIA T4",
        "chip": "T4",
        "gpu_count": 1,
        "family": "N1",
        "category": "GPU",
        "accelerator_type": "nvidia-tesla-t4",
        "guest_attached_gpu": True,
        "requires_gvnic": False,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "n1-standard-16": {
        "gpu": "NVIDIA T4",
        "chip": "T4",
        "gpu_count": 2,
        "family": "N1",
        "category": "GPU",
        "accelerator_type": "nvidia-tesla-t4",
        "guest_attached_gpu": True,
        "requires_gvnic": False,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
    "n1-standard-32": {
        "gpu": "NVIDIA T4",
        "chip": "T4",
        "gpu_count": 4,
        "family": "N1",
        "category": "GPU",
        "accelerator_type": "nvidia-tesla-t4",
        "guest_attached_gpu": True,
        "requires_gvnic": False,
        "requires_hyperdisk": False,
        "default_boot_disk_type": "pd-balanced",
    },
}

# GPU type to supported zones mapping
GPU_ZONES = {
    "A4X Max (GB300)": [
        "us-central1-b", "us-east4-b", "us-east5-c",
    ],
    "A4X (GB200)": [
        "europe-west4-b", "us-central1-a", "us-central1-b", "us-east1-d",
    ],
    "A4 (B200)": [
        "asia-northeast1-b", "asia-southeast1-b", "europe-north1-b",
        "europe-west4-a", "europe-west4-b", "me-central1-b",
        "us-central1-b", "us-east1-b", "us-east4-b", "us-east7-b",
        "us-south1-b", "us-west2-c", "us-west3-b", "us-west3-c",
    ],
    "A3 Ultra (H200)": [
        "asia-south1-b", "asia-south2-c", "europe-west1-b", "europe-west4-a",
        "us-central1-b", "us-east1-d", "us-east4-b", "us-east5-a",
        "us-east7-c", "us-south1-b", "us-west1-c",
    ],
    "A3 Edge (H100)": [
        "asia-east1-a", "asia-east1-b", "asia-east1-c",
        "asia-northeast1-b", "asia-southeast1-a", "asia-southeast1-b",
        "europe-west1-b", "europe-west1-c", "europe-west4-a", "europe-west4-b",
        "me-west1-b",
        "us-central1-a", "us-central1-b", "us-central1-c",
        "us-east1-b", "us-east1-c", "us-east4-a", "us-east4-b",
        "us-west1-a", "us-west1-b",
    ],
    "A3 Mega (H100)": [
        "asia-east1-c", "asia-northeast1-b", "asia-southeast1-b",
        "asia-southeast1-c", "australia-southeast1-c", "europe-west1-b",
        "europe-west1-c", "europe-west4-b", "europe-west4-c",
        "us-central1-a", "us-central1-b", "us-central1-c",
        "us-east4-a", "us-east4-b", "us-east4-c", "us-east5-a",
        "us-west1-a", "us-west1-b", "us-west4-a",
    ],
    "A3 High (H100)": [
        "asia-east1-c", "asia-northeast1-b", "asia-southeast1-b",
        "asia-southeast1-c", "europe-west1-b", "europe-west1-c",
        "europe-west4-b", "europe-west4-c",
        "us-central1-a", "us-central1-b", "us-central1-c",
        "us-east4-a", "us-east4-b", "us-east5-a",
        "us-west1-a", "us-west1-b", "us-west4-a",
    ],
    "A2 Ultra (A100 80GB)": [
        "asia-southeast1-c", "europe-west4-a", "us-central1-a",
        "us-central1-c", "us-east4-c", "us-east5-a",
    ],
    "A2 Standard (A100 40GB)": [
        "asia-northeast1-a", "asia-northeast1-c", "asia-northeast3-b",
        "asia-southeast1-b", "asia-southeast1-c", "europe-west4-a",
        "europe-west4-b", "me-west1-a", "me-west1-c",
        "us-central1-a", "us-central1-b", "us-central1-c", "us-central1-f",
        "us-east1-b", "us-west1-b", "us-west3-b", "us-west4-b",
    ],
    "G4 (RTX PRO 6000)": [
        "asia-south2-c", "asia-southeast1-b", "asia-southeast1-c",
        "asia-southeast2-b", "asia-southeast2-c", "europe-north1-a",
        "europe-west1-c", "europe-west2-b", "europe-west4-a", "europe-west4-b",
        "europe-west4-c", "europe-west8-b", "us-central1-b", "us-central1-f",
        "us-east1-b", "us-east4-c", "us-east5-a", "us-east5-b", "us-east5-c",
        "us-south1-a", "us-south1-b", "us-west1-b", "us-west1-c",
        "us-west3-a", "us-west4-a",
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
        "us-west4-a", "us-west4-c",
    ],
    "N1 (T4)": [
        "asia-east1-a", "asia-east1-c",
        "asia-east2-a", "asia-east2-c",
        "asia-northeast1-a", "asia-northeast1-c",
        "asia-northeast3-b", "asia-northeast3-c",
        "asia-south1-a", "asia-south1-b",
        "asia-southeast1-a", "asia-southeast1-b", "asia-southeast1-c",
        "asia-southeast2-a", "asia-southeast2-b",
        "australia-southeast1-a", "australia-southeast1-c",
        "europe-central2-b", "europe-central2-c",
        "europe-west1-b", "europe-west1-c", "europe-west1-d",
        "europe-west2-a", "europe-west2-b",
        "europe-west3-b",
        "europe-west4-a", "europe-west4-b", "europe-west4-c",
        "me-west1-b", "me-west1-c",
        "northamerica-northeast1-c",
        "southamerica-east1-a", "southamerica-east1-b", "southamerica-east1-c",
        "us-central1-a", "us-central1-b", "us-central1-c", "us-central1-f",
        "us-east1-b", "us-east1-c", "us-east1-d",
        "us-east4-a", "us-east4-b", "us-east4-c",
        "us-west1-a", "us-west1-b",
        "us-west2-b", "us-west2-c",
        "us-west3-b",
        "us-west4-a", "us-west4-b",
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
    "N1": "N1 (T4)",
}

# Consumption model support matrix (verified against Google3 vm_family_metadata & self_service_constraints)
CONSUMPTION_SUPPORT = {
    "on_demand": {
        "A4X Max": False, "A4X": False, "A4": False,
        "A3 Ultra": False, "A3 Edge": True, "A3 Mega": True, "A3 High": True,
        "A2 Ultra": True, "A2 Standard": True, "A2 Mega": True,
        "G4": True, "G2": True, "N1": True,
    },
    "spot": {
        "A4X Max": True, "A4X": True, "A4": True,
        "A3 Ultra": True, "A3 Edge": True, "A3 Mega": True, "A3 High": True,
        "A2 Ultra": True, "A2 Standard": True, "A2 Mega": True,
        "G4": True, "G2": True, "N1": True,
    },
    "dws_calendar": {
        "A4X Max": False, "A4X": True, "A4": True,
        "A3 Ultra": True, "A3 Edge": False, "A3 Mega": True, "A3 High": True,
        "A2 Ultra": False, "A2 Standard": False, "A2 Mega": False,
        "G4": False, "G2": False, "N1": False,
    },
    "dws_flex": {
        "A4X Max": True, "A4X": True, "A4": True,
        "A3 Ultra": True, "A3 Edge": True, "A3 Mega": True, "A3 High": True,
        "A2 Ultra": False, "A2 Standard": False, "A2 Mega": False,
        "G4": True, "G2": True, "N1": True,
    },
}

# Authoritative DWS Calendar Mode Zonal Overrides & Self-Service Constraints
CALENDAR_CONFIG = {
    "A4X": {
        "category": "GPU",
        "calendar_zones": ["us-central1-a", "us-central1-b", "us-east1-d"],
        "min_ahead_hours": 720,   # 30 days
        "max_ahead_days": 90,
        "min_duration_days": 7,
        "max_duration_days": 90,
        "min_vm_count": 16,
        "max_vm_count": 128,
        "vm_count_step": 16,
        "deployment_type": "DENSE",
    },
    "A4": {
        "category": "GPU",
        "calendar_zones": [
            "asia-northeast1-b", "asia-southeast1-b", "europe-north1-b",
            "europe-west4-a", "europe-west4-b", "me-central1-b",
            "us-central1-b", "us-east1-b", "us-east4-b", "us-east7-b",
            "us-south1-b", "us-west2-c", "us-west3-b", "us-west3-c",
        ],
        "min_ahead_hours": 87,    # 3d 15h
        "max_ahead_days": 90,
        "min_duration_days": 1,
        "max_duration_days": 90,
        "min_vm_count": 1,
        "max_vm_count": 64,
        "vm_count_step": 1,
        "deployment_type": "DENSE",
    },
    "A3 Ultra": {
        "category": "GPU",
        "calendar_zones": [
            "asia-south1-b", "asia-south2-c", "europe-west1-b", "europe-west4-a",
            "us-central1-b", "us-east1-d", "us-east4-b", "us-east7-c",
            "us-south1-b", "us-west1-c",
        ],
        "min_ahead_hours": 87,
        "max_ahead_days": 90,
        "min_duration_days": 1,
        "max_duration_days": 90,
        "min_vm_count": 1,
        "max_vm_count": 64,
        "vm_count_step": 1,
        "deployment_type": "DENSE",
    },
    "A3 Mega": {
        "category": "GPU",
        "calendar_zones": [
            "asia-east1-c", "asia-northeast1-b", "asia-southeast1-b",
            "asia-southeast1-c", "australia-southeast1-c", "europe-west1-b",
            "europe-west1-c", "europe-west4-b", "europe-west4-c",
            "us-central1-a", "us-central1-b", "us-central1-c",
            "us-east4-a", "us-east4-b", "us-east4-c", "us-east5-a",
            "us-west1-a", "us-west1-b", "us-west4-a",
        ],
        "min_ahead_hours": 87,
        "max_ahead_days": 90,
        "min_duration_days": 1,
        "max_duration_days": 90,
        "min_vm_count": 1,
        "max_vm_count": 64,
        "vm_count_step": 1,
        "deployment_type": "DENSE",
    },
    "A3 High": {
        "category": "GPU",
        "calendar_zones": [
            "asia-east1-c", "asia-northeast1-b", "asia-southeast1-b",
            "asia-southeast1-c", "europe-west1-b", "europe-west1-c",
            "europe-west4-c", "us-central1-a", "us-central1-b", "us-central1-c",
            "us-east4-a", "us-east4-b", "us-east5-a",
            "us-west1-a", "us-west1-b", "us-west4-a",
        ],
        "min_ahead_hours": 87,
        "max_ahead_days": 90,
        "min_duration_days": 1,
        "max_duration_days": 90,
        "min_vm_count": 1,
        "max_vm_count": 128,
        "vm_count_step": 1,
        "deployment_type": "DENSE",
    },
    "v6e": {
        "category": "TPU",
        "vm_family": "VM_FAMILY_CLOUD_TPU_LITE_POD_SLICE_CT6E",
        "gce_accelerator_type": "ct6e",
        "calendar_zones": [
            "asia-northeast1-b", "asia-south1-b", "asia-south1-c",
            "asia-southeast1-b", "europe-west4-a", "southamerica-west1-a",
            "us-east1-d", "us-east5-a", "us-east5-b",
        ],
        "min_ahead_hours": 1,
        "max_ahead_days": 90,
        "min_duration_days": 1,
        "max_duration_days": 90,
        "allowed_accelerator_counts": [1, 4, 8, 16, 32, 64, 128, 256],
    },
    "v5p": {
        "category": "TPU",
        "vm_family": "VM_FAMILY_CLOUD_TPU_POD_SLICE_CT5P",
        "gce_accelerator_type": "ct5p",
        "calendar_zones": [
            "europe-west4-b", "us-east5-a",
        ],
        "min_ahead_hours": 25,
        "max_ahead_days": 90,
        "min_duration_days": 1,
        "max_duration_days": 90,
        "allowed_accelerator_counts": [4, 8, 16, 32, 64, 128, 256, 512],
        "default_workload_type": "BATCH",
    },
    "v5e": {
        "category": "TPU",
        "vm_family": "VM_FAMILY_CLOUD_TPU_LITE_POD_SLICE_CT5LP",
        "gce_accelerator_type": "ct5lp",
        "calendar_zones": [
            "europe-west4-b", "us-central1-a", "us-south1-a",
            "us-west1-c", "us-west4-a",
        ],
        "min_ahead_hours": 1,
        "max_ahead_days": 90,
        "min_duration_days": 1,
        "max_duration_days": 90,
        "allowed_accelerator_counts": [1, 4, 8, 16, 32, 64, 128, 256],
        "requires_workload_type": True,
    },
}

# TPU types, zones, machine types, runtime versions, and consumption model support
TPU_TYPES = {
    "v7x": {
        "gpu": "Cloud TPU v7x (Ironwood)",
        "accelerator_prefix": "tpu7x",
        "runtime_version": "v2-alpha-tpu7",
        "cores_per_chip": 2,
        "valid_slice_cores": [2, 8, 16, 32, 64, 128, 256, 512, 1024, 2048],
        "zones": [
            "europe-west4-a", "us-central1-a", "us-central1-b", "us-central1-c",
            "us-east5-c", "us-south1-b", "us-west1-c", "us-west3-b", "us-west4-a",
        ],
        "machine_types": {
            "tpu7x-standard-1t": {"chips": 1, "vcpus": 48, "memory_gb": 192, "hbm_gb": 192},
            "tpu7x-standard-4t": {"chips": 4, "vcpus": 224, "memory_gb": 960, "hbm_gb": 768},
        },
        "topologies": ["2x2x1", "2x2x2", "2x2x4", "2x4x4", "4x4x4"],
        "supported": {"on_demand": True, "spot": True, "dws_calendar": False, "dws_flex": True},
    },
    "v6e": {
        "gpu": "Cloud TPU v6e (Trillium)",
        "accelerator_prefix": "v6e",
        "runtime_version": "v2-alpha-tpuv6e",
        "cores_per_chip": 1,
        "valid_slice_cores": [1, 4, 8, 16, 32, 64, 128, 256],
        "zones": [
            "asia-northeast1-b", "asia-south1-b", "asia-south1-c",
            "asia-southeast1-b", "europe-west4-a", "southamerica-west1-a",
            "us-central1-b", "us-east1-d", "us-east5-a", "us-east5-b", "us-west4-a",
        ],
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
        "runtime_version": "v2-alpha-tpuv5",
        "cores_per_chip": 2,
        "valid_slice_cores": [8, 16, 32, 64, 128, 256, 512, 1024, 2048],
        "zones": ["europe-west4-b", "us-central1-a", "us-east5-a"],
        "machine_types": {
            "ct5p-hightpu-4t": {"chips": 4, "vcpus": 208, "memory_gb": 448, "hbm_gb": 380},
        },
        "topologies": ["2x2x1", "2x2x2", "2x2x4", "2x4x4", "4x4x4"],
        "supported": {"on_demand": True, "spot": True, "dws_calendar": True, "dws_flex": True},
    },
    "v5e": {
        "gpu": "Cloud TPU v5e (Viperlite)",
        "accelerator_prefix": "v5litepod",
        "runtime_version": "v2-alpha-tpuv5-lite",
        "cores_per_chip": 1,
        "valid_slice_cores": [1, 4, 8, 16, 32, 64, 128, 256],
        "zones": [
            "europe-west4-b", "us-central1-a", "us-south1-a",
            "us-west1-c", "us-west4-a",
        ],
        "machine_types": {
            "ct5lp-hightpu-1t": {"chips": 1, "vcpus": 24, "memory_gb": 48, "hbm_gb": 16},
            "ct5lp-hightpu-4t": {"chips": 4, "vcpus": 112, "memory_gb": 192, "hbm_gb": 64},
            "ct5lp-hightpu-8t": {"chips": 8, "vcpus": 224, "memory_gb": 384, "hbm_gb": 128},
            # Legacy aliases kept for backwards compatibility
            "ct5e-hightpu-1t": {"chips": 1, "vcpus": 24, "memory_gb": 48, "hbm_gb": 16, "legacy_alias": True},
            "ct5e-hightpu-4t": {"chips": 4, "vcpus": 112, "memory_gb": 192, "hbm_gb": 64, "legacy_alias": True},
            "ct5e-hightpu-8t": {"chips": 8, "vcpus": 224, "memory_gb": 384, "hbm_gb": 128, "legacy_alias": True},
        },
        "topologies": ["1x1", "2x2", "2x4", "4x4", "4x8", "8x8", "8x16", "16x16"],
        "supported": {"on_demand": True, "spot": True, "dws_calendar": True, "dws_flex": True},
    },
    "v4": {
        "gpu": "Cloud TPU v4 (Pufferfish)",
        "accelerator_prefix": "v4",
        "runtime_version": "tpu-ubuntu2204-base",
        "cores_per_chip": 2,
        "valid_slice_cores": [8, 16, 32, 64, 128, 256, 512, 1024, 2048],
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
        "runtime_version": "tpu-ubuntu2204-base",
        "cores_per_chip": 2,
        "valid_slice_cores": [8, 32, 64, 128, 256, 512],
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
        "runtime_version": "tpu-ubuntu2204-base",
        "cores_per_chip": 2,
        "valid_slice_cores": [8, 32, 128, 256, 512],
        "zones": ["asia-east1-c", "europe-west4-a", "us-central1-a", "us-central1-b", "us-central1-c"],
        "machine_types": {
            "v2-8": {"chips": 4, "vcpus": 96, "memory_gb": 340, "hbm_gb": 32},
        },
        "topologies": ["2x2", "4x4", "4x8", "8x8"],
        "supported": {"on_demand": True, "spot": True, "dws_calendar": False, "dws_flex": False},
    },
}


def get_zones_for_machine_type(machine_type: str) -> list[str]:
    """Get supported zones for a given machine type (GPU or TPU)."""
    for _tpu_type, tpu_info in TPU_TYPES.items():
        if machine_type in tpu_info.get("machine_types", {}):
            return tpu_info["zones"]
    family = MACHINE_TO_FAMILY.get(machine_type)
    if not family:
        return []
    gpu_zone_key = FAMILY_TO_GPU_ZONE_KEY.get(family)
    if not gpu_zone_key:
        return []
    return GPU_ZONES.get(gpu_zone_key, [])


def get_calendar_config_for_machine_type(machine_type: str) -> dict | None:
    """Return the DWS Calendar Mode configuration for a GPU or TPU machine type, or None if unsupported."""
    for tpu_type, tpu_info in TPU_TYPES.items():
        if machine_type in tpu_info.get("machine_types", {}):
            if not tpu_info.get("supported", {}).get("dws_calendar", False):
                return None
            cfg = CALENDAR_CONFIG.get(tpu_type)
            if not cfg:
                return None
            mt_spec = tpu_info["machine_types"][machine_type]
            return {
                **cfg,
                "tpu_type": tpu_type,
                "chips_per_vm": mt_spec.get("chips", 1),
            }
    family = MACHINE_TO_FAMILY.get(machine_type)
    if not family or not CONSUMPTION_SUPPORT.get("dws_calendar", {}).get(family, False):
        return None
    return CALENDAR_CONFIG.get(family)


def get_calendar_zones_for_machine_type(machine_type: str) -> list[str]:
    """Return zones where DWS Calendar Mode is enabled in prod for this machine type."""
    cfg = get_calendar_config_for_machine_type(machine_type)
    if cfg and cfg.get("calendar_zones"):
        return cfg["calendar_zones"]
    return []


def get_tpu_spec(machine_type: str, vm_count: int = 1) -> dict | None:
    """Resolve Cloud TPU API acceleratorType, runtimeVersion, and multi-node parameters."""
    for tpu_type, tpu_info in TPU_TYPES.items():
        if machine_type in tpu_info.get("machine_types", {}):
            mt_spec = tpu_info["machine_types"][machine_type]
            chips_per_vm = mt_spec.get("chips", 1)
            cores_per_chip = tpu_info.get("cores_per_chip", 1)
            prefix = tpu_info.get("accelerator_prefix", tpu_type)
            runtime_version = tpu_info.get("runtime_version", "tpu-ubuntu2204-base")

            single_vm_cores = chips_per_vm * cores_per_chip
            total_chips = chips_per_vm * max(1, vm_count)
            total_cores = total_chips * cores_per_chip

            if tpu_type in ("v2", "v3"):
                single_accel = machine_type
            else:
                single_accel = f"{prefix}-{single_vm_cores}"

            canonical_mt = (
                machine_type.replace("ct5e-hightpu-", "ct5lp-hightpu-")
                if machine_type.startswith("ct5e-hightpu-")
                else machine_type
            )
            use_multi_node = vm_count > 1
            return {
                "tpu_type": tpu_type,
                "name": tpu_info.get("gpu", f"Cloud TPU {tpu_type}"),
                "canonical_machine_type": canonical_mt,
                "runtime_version": runtime_version,
                "chips_per_vm": chips_per_vm,
                "cores_per_chip": cores_per_chip,
                "total_chips": total_chips,
                "total_cores": total_cores,
                "single_accelerator_type": single_accel,
                "accelerator_type": single_accel,
                "use_multi_node": use_multi_node,
                "node_count": max(1, vm_count),
            }
    return None


def is_consumption_supported(machine_type: str, consumption_model: str) -> bool:
    """Check if a consumption model is supported for a given machine type."""
    for _tpu_type, tpu_info in TPU_TYPES.items():
        if machine_type in tpu_info.get("machine_types", {}):
            return tpu_info.get("supported", {}).get(consumption_model, False)
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
        cal_zones = get_calendar_zones_for_machine_type(mt)
        regions = sorted(set(z.rsplit("-", 1)[0] for z in zones))
        result.append({
            "machineType": mt,
            "gpu": info["gpu"],
            "chip": info.get("chip", ""),
            "gpuCount": info["gpu_count"],
            "family": family,
            "category": info.get("category", "GPU"),
            "zones": zones,
            "calendarZones": cal_zones,
            "regions": regions,
            "supported": {
                "on_demand": is_consumption_supported(mt, "on_demand"),
                "spot": is_consumption_supported(mt, "spot"),
                "dws_calendar": is_consumption_supported(mt, "dws_calendar"),
                "dws_flex": is_consumption_supported(mt, "dws_flex"),
            },
        })
    for tpu_type, tpu_info in TPU_TYPES.items():
        supported = tpu_info.get("supported", {})
        for mt_name, mt_spec in tpu_info.get("machine_types", {}).items():
            if mt_spec.get("legacy_alias"):
                continue
            cal_zones = get_calendar_zones_for_machine_type(mt_name)
            result.append({
                "machineType": mt_name,
                "gpu": tpu_info.get("gpu", f"Cloud TPU {tpu_type}"),
                "chip": tpu_type,
                "gpuCount": mt_spec["chips"],
                "family": f"TPU {tpu_type}",
                "category": "TPU",
                "zones": tpu_info["zones"],
                "calendarZones": cal_zones,
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
    gpu_chips = {}
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
            "gpu": tpu_info.get("gpu", f"Cloud TPU {tpu_type}"),
            "category": "TPU",
            "zones": tpu_info["zones"],
            "regions": sorted(set(z.rsplit("-", 1)[0] for z in tpu_info["zones"])),
        }

    return {
        "gpuChips": list(gpu_chips.values()),
        "tpuChips": list(tpu_chips.values()),
    }
