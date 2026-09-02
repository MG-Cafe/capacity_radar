---
name: capacity-radar
description: >-
  Find, advise on, and deploy Google Cloud GPU/TPU capacity from chat. Use this
  skill whenever the user wants to check GPU/TPU availability, get capacity
  advice, compare consumption models (On-Demand, DWS Calendar, DWS Flex Start,
  Spot), or actually deploy/reserve/hunt for GPU or TPU capacity on Google Cloud
  (GCP). Triggers include: "find me H100s", "check spot availability", "reserve
  a3-highgpu-8g", "how long to wait for DWS Flex", "hunt for GPUs", "get me TPUs".
license: Not an official Google product. Use at your own risk.
---

# Capacity Radar Skill

Capacity Radar helps users **find and secure GPU/TPU capacity on Google Cloud**.
This skill lets you (the agent) drive every capability of the Capacity Radar app
through a single CLI, entirely via chat: authenticate, explore what's available,
run capacity advisories, and deploy using a priority-based strategy.

## What this skill can do (tell the user!)

Many users won't know the full capability. Proactively offer these:

1. **Authentication** — verify the user is logged into Google Cloud (ADC) and has
   access to their project; if not, help them log in (opens a browser).
2. **Catalog / discovery** — list supported GPU chips (H100, H200, B200, A100,
   L4, RTX PRO 6000, T4, GB200/GB300) and TPUs (v6e, v5p, v5e, v4, v3, v2),
   their machine types, supported zones, and which consumption models each
   supports.
3. **Capacity Advisories** (read-only, safe — no resources created):
   - **Spot VM Advisory** — availability + preemption risk per zone.
   - **DWS Calendar Advisory** — recommended zones/time-windows; plus a
     "best plan" mode that splits a large request across VM-count levels.
   - **DWS Flex Start Advisory** _(Preview — requires a whitelisted project)_ —
     estimated wait time in the queue before Flex Start capacity is granted.
4. **Scan & Deploy** — a priority-based hunt that tries consumption methods in
   order (or in parallel) across zones until capacity is secured. **This creates
   real, billable GCP resources** — always confirm with the user first.

## The one tool: `scripts/capacity_radar.py`

Everything is done by running this Python CLI. It reuses the app's own backend
modules, so results are identical to the web UI. Every command prints JSON to
stdout so you can parse it and decide the next step.

Run it with the repo's Python environment (see Setup). General shape:

```bash
python scripts/capacity_radar.py <group> <command> [flags...]
```

### Commands

| Command | Purpose |
|---|---|
| `auth check --project <ID>` | Check ADC auth + project access + Compute API status |
| `auth login` | Run `gcloud auth application-default login` (opens browser) |
| `catalog chips` | List GPU/TPU chips grouped, with machine types |
| `catalog machine-types` | Full machine-type list + support matrix |
| `catalog zones --machine-type <MT>` | Supported zones/regions for a machine type |
| `advise spot --project <ID> --machine-type <MT> [--regions r1,r2] [--zones z1,z2]` | Spot availability + preemption risk |
| `advise calendar --project <ID> --machine-type <MT> --vm-count N --start-date YYYY-MM-DD --flexibility-days 0..3 --duration-days D [--regions/--zones]` | DWS Calendar availability |
| `advise calendar-plan ... (same flags as calendar)` | DWS Calendar "best split" plan |
| `advise flex --project <ID> --machine-type <MT> --size N --max-run-hours H [--regions/--zones]` | DWS Flex Start wait-time advisory (Preview) |
| `deploy --project <ID> --machine-type <MT> --vm-count N --priority <spec> [--priority ...] [--parallel] [--yes]` | Priority-based scan & deploy (REAL resources) |

### `--priority` spec format (deploy)

Repeatable. `method[:zones][:max_retries][:retry_interval]`
- `method` = `on_demand` | `dws_calendar` | `dws_flex` | `spot`
- `zones` = comma-separated (omit → all supported zones for the machine type)
- Examples: `spot:us-central1-b,us-east4-a`  ·  `dws_flex:us-central1-b:3:60`

Extra deploy flags: `--name-prefix`, `--flex-max-wait-hours`, `--flex-usage-hours`,
`--calendar-start`/`--calendar-end` (ISO datetime), `--calendar-duration-hours`.

## How to behave (agent workflow)

Follow this loop and **ask follow-up questions whenever an input is missing** —
mirror how the app collects inputs. Never guess the project ID.

1. **Auth first.** Run `auth check --project <ID>`. If `authenticated` is false,
   offer to run `auth login` (tell them a browser will open). If the project is
   invalid or the Compute API is disabled, surface the `instructions` from the
   JSON and help them fix it.
2. **Clarify intent.** Ask what they want: *advice* (safe) or *deploy* (creates
   resources). Suggest capabilities they may not know about.
3. **Resolve the resource.** If they name a GPU loosely ("H100", "8x H100"),
   use `catalog chips` to map it to a machine type (e.g. `a3-highgpu-8g`). Use
   `catalog zones` to confirm/suggest regions & zones. Ask for any missing
   inputs (VM count, region/zone, duration, size, dates).
4. **Run the advisory** the user wants and summarize results clearly (which
   zones have capacity, estimated waits, preemption risk). For DWS Flex, note it
   is Preview/whitelisted; if you get `The service is not available for this
   project.`, explain the project needs allow-listing.
5. **For deploy:** build the priority strategy from the conversation, show the
   plan, and **require explicit user confirmation**. Only then run `deploy`
   with `--yes`. Without `--yes`, the CLI returns `requiresConfirmation: true`
   and a `plan` object — present that plan and ask the user to confirm. Stream
   progress (deploy writes live events to stderr and a full `events` array in
   the final JSON).

### Safety rules

- **Deploy creates real, billable resources.** Always confirm the exact plan
  (project, machine type, count, methods, zones) with the user before using
  `--yes`.
- Advisories are read-only and safe to run freely.
- Never fabricate project IDs, zones, or results — always run the CLI and report
  what it returns.

## Setup (one time)

The skill needs the Capacity Radar backend deps available to Python and the
gcloud SDK for auth.

```bash
# From the repo root:
pip install -r backend/requirements.txt
# Authenticate once (or use: python skills/capacity-radar/scripts/capacity_radar.py auth login)
gcloud auth application-default login
```

Then invoke the CLI from the repo root, e.g.:

```bash
python skills/capacity-radar/scripts/capacity_radar.py catalog chips
```

## Quick examples

```bash
# Check auth + project
python skills/capacity-radar/scripts/capacity_radar.py auth check --project my-project

# "Do you have H100s on spot in us-central1?"
python skills/capacity-radar/scripts/capacity_radar.py advise spot \
  --project my-project --machine-type a3-highgpu-8g --regions us-central1

# "How long would I wait for 4x H100 on DWS Flex?"
python skills/capacity-radar/scripts/capacity_radar.py advise flex \
  --project my-project --machine-type a3-highgpu-8g --size 4 --max-run-hours 24 --regions us-central1

# "Hunt for 2x H100: try spot first, then DWS Flex" (after user confirms)
python skills/capacity-radar/scripts/capacity_radar.py deploy \
  --project my-project --machine-type a3-highgpu-8g --vm-count 2 \
  --priority spot:us-central1-b,us-east4-a \
  --priority dws_flex:us-central1-b \
  --yes
```
