# 🎯 Capacity Radar

**Priority-based GPU/TPU capacity scanning and deployment tool for Google Cloud Platform.**

Capacity Radar automates the process of finding and securing GPU/TPU capacity across Google Cloud zones. It supports multiple consumption models — On-Demand Reservations, DWS Calendar, DWS Flex Start, and Spot VMs — and lets you define a priority-based strategy that tries each method in order until capacity is secured.

![Capacity Radar](https://img.shields.io/badge/Google%20Cloud-GPU%20%2F%20TPU-4285F4?logo=google-cloud&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)

---

## ✨ Features

### 🔍 Scan & Deploy
- **Priority-based scanning** — Define up to 4 priorities (e.g., try On-Demand first, then DWS Calendar, then Spot)
- **Multi-zone scanning** — Automatically tries all supported zones for your chosen machine type
- **Real-time progress** — WebSocket-based live updates with detailed logs
- **Sequential or Parallel** execution modes
- **Custom naming** — Set resource name prefixes for your reservations and VMs

### 📋 Consumption Models
| Model | Description |
|-------|-------------|
| **On-Demand Reservation** | Reserve capacity at on-demand rates. Immediate if available. |
| **DWS Calendar Mode** | Book capacity for a specific time window (future reservation). Requires Google approval. |
| **DWS Flex Start** | Queue for capacity; the system keeps retrying until GPUs become available. For TPUs, uses Queued Resources with configurable max wait time. |
| **Spot VMs** | Spare capacity at discount. Can be preempted at any time. |

### 📊 Advisory Tab
- **DWS Calendar Advisory** — Query the Calendar Mode Advisory API to find optimal zones and time windows for future reservations
- **Spot VM Advisory** — Check spot capacity availability across zones

### 🖥️ Supported Hardware
- **GPU families**: A4 Mega (B200), A3 Ultra (H200 SXM), A3 Mega (H100 Mega), A3 High (H100 80GB), A2 Ultra (A100 80GB), A2 (A100 40GB), G2 (L4), and more
- **TPU types**: v6e, v5e, v5p, v4, v3
- **Full zone support** — Automatically maps machine types to their available zones

---

## 🚀 Quick Start

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
# Login with your Google account
gcloud auth application-default login

# Set your default project (optional)
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

---

## 🏗️ Architecture

```
capacity_radar/
├── backend/
│   ├── main.py              # FastAPI server, REST + WebSocket endpoints
│   ├── hunter.py            # Core scanning engine (GPU & TPU deployment)
│   ├── gpu_data.py          # Machine type catalog, zone mappings
│   ├── advisory.py          # DWS Calendar & Spot advisory APIs
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── App.jsx          # Main app with tabs (Scan, Advisory)
│   │   └── components/
│   │       ├── ScanningPanel.jsx    # Scan & Deploy configuration UI
│   │       ├── AdvisoryPanel.jsx    # Advisory queries UI
│   │       └── MachineTypeSelector.jsx  # Chip → Machine type picker
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
├── .gitignore
└── README.md
```

### Tech Stack
- **Backend**: Python, FastAPI, WebSocket, httpx, Google Cloud REST APIs
- **Frontend**: React 18, Material UI, Vite
- **Auth**: Google Application Default Credentials (ADC)

---

## 🔧 Configuration

### Required GCP IAM Permissions

The authenticated user/service account needs these roles on the target project:

| Role | Purpose |
|------|---------|
| `roles/compute.admin` | Create reservations, instances, future reservations |
| `roles/tpu.admin` | Create TPU nodes and queued resources (if using TPUs) |

### Environment

No environment variables are required. The app uses **Application Default Credentials (ADC)** — just run `gcloud auth application-default login` before starting.

### Changing the Port

Edit the last line of `backend/main.py`:

```python
uvicorn.run(app, host="0.0.0.0", port=8000)  # Change 8000 to your desired port
```

---

## 📖 Usage Guide

### Setting Up a Scan

1. **Enter your GCP Project ID** and click "Connect" to authenticate
2. **Select a machine type** using the Category → Chip → Machine Type selector
3. **Add scanning priorities** — each priority tries a specific consumption model:
   - Choose the method (On-Demand, DWS Calendar, DWS Flex, Spot)
   - Select target zones (or leave empty to try all available zones)
   - Set max retries and retry interval
   - Optionally set a resource name prefix
4. **Configure method-specific settings**:
   - **DWS Calendar**: Set start and end times for the reservation window
   - **DWS Flex**: Set usage duration (how long you need the GPUs)
5. Choose **Sequential** (try one after another) or **Parallel** (race all at once) execution
6. Click **Start Scan & Deploy**

### Understanding Results

- ✅ **Success** — Capacity secured! The log shows which method and zone succeeded
- ❌ **Failed** — All priorities exhausted. Try different zones, machine types, or methods
- 🛑 **Cancelled** — You stopped the scan. Check for partially created resources in GCP Console

### DWS Calendar Behavior
When a Calendar reservation is submitted, it enters **PENDING_APPROVAL** status. The tool polls indefinitely until Google approves or rejects the reservation. If rejected, it moves to the next priority.

### DWS Flex Behavior
- **For GPUs**: The Compute Engine API doesn't have a real queue — each attempt either succeeds or fails immediately. The tool uses your configured max retries and interval to keep trying.
- **For TPUs**: Uses the TPU Queued Resource API which supports actual queuing. Your request stays queued until capacity becomes available or the max wait time expires.

---

## 🐳 Docker Deployment (Optional)

```dockerfile
FROM python:3.11-slim

# Install Node.js
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

# Install backend
RUN pip install --no-cache-dir -r backend/requirements.txt

# Build frontend
RUN cd frontend && npm install && npm run build

# Run
EXPOSE 8000
CMD ["python", "backend/main.py"]
```

```bash
docker build -t capacity-radar .
docker run -p 8000:8000 \
  -v ~/.config/gcloud:/root/.config/gcloud \
  capacity-radar
```

> **Note**: Mount your `gcloud` config directory to pass authentication credentials to the container.

---

## 🌐 Cloud Run Deployment

```bash
# Build and deploy to Cloud Run
gcloud run deploy capacity-radar \
  --source . \
  --port 8000 \
  --region us-central1 \
  --allow-unauthenticated \
  --service-account YOUR_SERVICE_ACCOUNT@YOUR_PROJECT.iam.gserviceaccount.com
```

Make sure the Cloud Run service account has `Compute Admin` and `TPU Admin` roles.

---

## ⚠️ Important Notes

- **Cost Awareness**: This tool creates real GCP resources (reservations, VMs, TPU nodes). Ensure you understand the cost implications before deploying.
- **Resource Cleanup**: If a scan is cancelled, check your GCP Console for partially created resources that may still be running and incurring charges.
- **Quotas**: Ensure your project has sufficient quota for the machine types and zones you're targeting.
- **DWS Calendar Approval**: Future reservations require Google approval and may take time or be declined depending on capacity availability.

---

## 👤 Creator

**Mohammad Ghodratigohar** — [emgi@google.com](mailto:emgi@google.com)

---

## 📄 License

This project is provided as-is for use by Google Cloud customers. See your Google Cloud agreement for terms of use.
