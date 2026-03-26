# Capacity Radar

**Priority-based GPU/TPU capacity scanning and deployment tool for Google Cloud Platform.**

Capacity Radar automates finding and securing GPU/TPU capacity across Google Cloud zones. It supports multiple consumption models — On-Demand Reservations, DWS Calendar, DWS Flex Start, and Spot VMs — and lets you define a priority-based strategy that tries each method in order until capacity is secured.

![Google Cloud](https://img.shields.io/badge/Google%20Cloud-GPU%20%2F%20TPU-4285F4?logo=google-cloud&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?logo=fastapi&logoColor=white)

---

## Features

### Scan & Deploy
- **Priority-based scanning** — Define up to 4 priorities (e.g., try On-Demand first, then DWS Calendar, then Spot)
- **Multi-zone scanning** — Automatically tries all supported zones for the chosen machine type
- **Real-time progress** — WebSocket-based live updates with detailed step-by-step logs
- **Sequential or Parallel** execution modes
- **Custom naming** — Set resource name prefixes for reservations and VMs
- **Cancel anytime** — Cancel a running scan and the tool stops gracefully

### Consumption Models

| Model | Description | GPU Families |
|-------|-------------|--------------|
| **On-Demand Reservation** | Reserve capacity at on-demand rates. Immediate if available. | A3 Edge/Mega/High, A2, G2, G4 |
| **DWS Calendar Mode** | Book capacity for a specific time window as a future reservation. Uses DENSE deployment for multi-node GPU families. | A4, A3 Ultra/Mega/High/Edge |
| **DWS Flex Start** | Queue for capacity; retries until GPUs become available. For TPUs, uses Queued Resources with configurable max wait time. | A4, A3, A4X |
| **Spot VMs** | Spare capacity at discount. Can be preempted at any time. | All GPU families |

### Capacity Advisory

- **DWS Calendar Advisory** — Query the Calendar Mode Advisory API to find optimal zones and time windows
  - **Check Availability** — Query with your exact parameters (start date, flexibility, duration)
  - **Find Best Plan** — Queries at multiple VM count levels (100%, 75%, 50%, 25%, 1 VM) to show how to split capacity across multiple smaller reservations
- **Spot VM Advisory** — Check spot capacity availability and preemption risk across zones

### Supported Hardware

**GPU Families:**

| Family | GPU | Machine Types | DWS Calendar | Spot | On-Demand |
|--------|-----|---------------|:------------:|:----:|:---------:|
| A4X Max | NVIDIA GB300 | `a4x-maxgpu-4g-metal` | - | Yes | - |
| A4X | NVIDIA GB200 | `a4x-highgpu-4g` | - | Yes | Yes |
| A4 | NVIDIA B200 | `a4-highgpu-8g` | Yes (DENSE) | Yes | - |
| A3 Ultra | NVIDIA H200 | `a3-ultragpu-8g` | Yes (DENSE) | Yes | - |
| A3 Edge | NVIDIA H100 | `a3-edgegpu-8g` | Yes (DENSE) | Yes | Yes |
| A3 Mega | NVIDIA H100 | `a3-megagpu-8g` | Yes (DENSE) | Yes | Yes |
| A3 High | NVIDIA H100 | `a3-highgpu-{1,2,4,8}g` | Yes (DENSE) | Yes | Yes |
| A2 Ultra | NVIDIA A100 80GB | `a2-ultragpu-{1,2,4,8}g` | - | Yes | Yes |
| A2 Standard | NVIDIA A100 40GB | `a2-highgpu-{1,2,4,8}g` | - | Yes | Yes |
| G4 | NVIDIA RTX PRO 6000 | `g4-standard-{6..384}` | - | Yes | Yes |
| G2 | NVIDIA L4 | `g2-standard-{4..96}` | - | Yes | Yes |

**TPU Types:**

| Type | Zones | DWS Calendar | Spot |
|------|-------|:------------:|:----:|
| v6e (Trillium) | 7 zones | Yes | Yes |
| v5p | 3 zones | Yes | Yes |
| v5e | 5 zones | Yes | Yes |
| v4 | 1 zone | - | Yes |
| v3 | 3 zones | - | Yes |
| v2 | 5 zones | - | Yes |

---

## Quick Start

### Prerequisites

- **Python 3.10+**
- **Node.js 18+** and npm
- **Google Cloud SDK** (`gcloud`) installed and configured
- A GCP project with **Compute Engine API** enabled

### 1. Clone the Repository

```bash
git clone https://github.com/MG-Cafe/capacity_radar.git
cd capacity_radar
```

### 2. Authenticate with Google Cloud

```bash
# Login with your Google account (sets up Application Default Credentials)
gcloud auth application-default login

# Set your project (optional — you can also enter it in the UI)
gcloud config set project YOUR_PROJECT_ID
```

### 3. Install Backend Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 4. Install Frontend Dependencies & Build

```bash
cd ../frontend
npm install
npm run build
```

### 5. Run the Application

```bash
cd ../backend
python main.py
```

The app will be available at **http://localhost:8000**

### Development Mode (Hot Reload)

For frontend development with hot reload:

```bash
# Terminal 1: Backend
cd backend && python main.py

# Terminal 2: Frontend dev server (proxied to backend)
cd frontend && npm run dev
```

Frontend dev server runs on http://localhost:3000 with API proxy to :8000.

---

## Architecture

```
capacity_radar/
├── backend/
│   ├── main.py              # FastAPI server — REST + WebSocket endpoints
│   ├── hunter.py            # Core scanning engine (GPU & TPU deployment)
│   ├── advisory.py          # DWS Calendar & Spot advisory API queries
│   ├── gpu_data.py          # Machine type catalog, zone mappings, consumption support
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Main app — auth drawer, tab navigation
│   │   └── components/
│   │       ├── AdvisoryPanel.jsx       # Calendar & Spot advisory queries
│   │       ├── ScanningPanel.jsx       # Scan & Deploy configuration + live logs
│   │       └── MachineTypeSelector.jsx # Category → Chip → Machine type picker
│   ├── vite.config.js       # Vite config with API proxy
│   └── package.json
└── README.md
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.10+, FastAPI, WebSocket, httpx |
| Frontend | React 18, Material UI v5, Vite |
| Auth | Google Application Default Credentials (ADC) |
| APIs | Compute Engine REST API (v1), TPU API (v2), Spot Advisory (alpha) |

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/auth/check` | Verify GCP auth and project access |
| `POST` | `/api/auth/login` | Trigger `gcloud auth application-default login` |
| `GET` | `/api/machine-types` | List all GPU/TPU machine types with zone info |
| `GET` | `/api/chip-groups` | Machine types grouped by chip for the selector |
| `GET` | `/api/machine-types/{type}/zones` | Zones for a specific machine type |
| `POST` | `/api/advisory/calendar` | Query DWS Calendar Advisory API |
| `POST` | `/api/advisory/calendar/splits` | Find best capacity split plan |
| `POST` | `/api/advisory/spot` | Query Spot VM Advisory API |
| `WS` | `/ws/scan` | WebSocket for real-time scan & deploy |

---

## Configuration

### Required GCP IAM Permissions

The authenticated user or service account needs:

| Role | Purpose |
|------|---------|
| `roles/compute.admin` | Create reservations, instances, future reservations |
| `roles/tpu.admin` | Create TPU nodes and queued resources (if using TPUs) |

### CORS Configuration

By default, the backend allows requests from `localhost:3000` and `localhost:5173` (Vite dev servers). To customize:

```bash
export CORS_ORIGINS="http://localhost:3000,https://your-domain.com"
```

### Changing the Port

Edit `backend/main.py`:

```python
uvicorn.run(app, host="0.0.0.0", port=8000)  # Change 8000
```

---

## Usage Guide

### Setting Up a Scan

1. **Authenticate** — Click "Authenticate with Google" to open browser sign-in
2. **Connect** — Enter your GCP Project ID and click "Connect"
3. **Select machine type** — Pick Category (GPU/TPU) → Chip → Machine Type
4. **Set VM count** — Min and Max VMs (system tries max first, scales down to min)
5. **Add priorities** — Each priority specifies:
   - Consumption method (On-Demand, DWS Calendar, DWS Flex, Spot)
   - Target zones (leave empty = try all available)
   - Retry rounds and interval
   - Optional resource name prefix
6. **Method-specific settings**:
   - **DWS Calendar**: Start/end times for the reservation window
   - **DWS Flex**: Max wait time and usage duration
7. Choose **Sequential** or **Parallel** execution
8. Click **Start Scan & Deploy**

### Using the Advisory Tab

#### Check Availability
1. Select a machine type and enter VM count
2. Pick a start date and flexibility window (0-3 days)
3. Set duration in days
4. Click **Check Availability** to see zone recommendations

#### Find Best Plan
1. Same inputs as above
2. Click **Find Best Plan** — queries at 100%, 75%, 50%, 25%, and 1 VM counts
3. View results grouped by VM count level to plan multiple reservations
4. Example: "No 20-GPU slot, but 15 GPUs available days 1-3, then 5 more days 4-7"

### Understanding Scan Results

| Status | Meaning |
|--------|---------|
| **Success** | Capacity secured. Logs show method, zone, and resource details. |
| **Failed** | All priorities exhausted. Try different zones, types, or methods. |
| **Cancelled** | You stopped the scan. Check GCP Console for partial resources. |

### DWS Calendar Behavior
Calendar future reservations use `reservationMode: CALENDAR` with DENSE deployment for multi-node GPU families (A3, A4). After submission, the tool polls until Google approves or rejects. Approval is typically within a minute for eligible projects.

### DWS Flex Behavior
- **GPUs**: Uses Compute Engine reservations with retry logic (no real queue — each attempt succeeds or fails immediately)
- **TPUs**: Uses the TPU Queued Resource API with actual server-side queuing

---

## Deployment

### Docker

```dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir -r backend/requirements.txt
RUN cd frontend && npm install && npm run build

EXPOSE 8000
CMD ["python", "backend/main.py"]
```

```bash
docker build -t capacity-radar .
docker run -p 8000:8000 \
  -v ~/.config/gcloud:/root/.config/gcloud \
  capacity-radar
```

> Mount your `gcloud` config directory to pass ADC credentials to the container.

### Cloud Run

```bash
gcloud run deploy capacity-radar \
  --source . \
  --port 8000 \
  --region us-central1 \
  --allow-unauthenticated \
  --service-account SA_NAME@PROJECT.iam.gserviceaccount.com
```

The Cloud Run service account needs `Compute Admin` and `TPU Admin` roles.

---

## Important Notes

- **Cost**: This tool creates real GCP resources (reservations, VMs, TPU nodes). Understand cost implications before deploying.
- **Cleanup**: If a scan is cancelled, check GCP Console for partially created resources that may still incur charges.
- **Quotas**: Ensure your project has sufficient quota for the machine types and zones you're targeting.
- **DWS Calendar**: Future reservations may require Google account team approval for DENSE deployment eligibility. If you get a "not available for this project" error, contact your account representative.
- **A4X Max**: Bare metal instances — cannot use on-demand reservations.
- **Token Refresh**: ADC tokens are automatically refreshed every 50 minutes during long scans.

---

## License

This project is provided as-is for internal use. See your organization's policies for distribution guidelines.
