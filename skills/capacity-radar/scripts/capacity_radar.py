#!/usr/bin/env python3
"""
Capacity Radar CLI — a portable command-line wrapper around the Capacity Radar
engine so that AI agents (or humans) can drive ALL of the app's functionality
from the terminal / chat:

  • auth        — check / trigger Google Cloud authentication (ADC)
  • catalog     — list supported GPU/TPU machine types, chips, and zones
  • advise      — run capacity advisories (calendar | spot | flex)
  • deploy      — run a priority-based scan & deploy strategy (real resources!)

It reuses the exact same backend modules the web app uses (advisory.py,
hunter.py, gpu_data.py), so behavior is identical to the UI.

All commands print JSON to stdout so an agent can parse results and decide the
next step (e.g. ask the user a follow-up question).

Auth model: Google Application Default Credentials (ADC). Run
`gcloud auth application-default login` once, or use `capacity_radar.py auth login`.

Examples
--------
  # 1) Verify auth + project access
  python capacity_radar.py auth check --project my-project

  # 2) Discover what you can ask for
  python capacity_radar.py catalog chips
  python capacity_radar.py catalog zones --machine-type a3-highgpu-8g

  # 3) Advisories (any chip / region / zone / size)
  python capacity_radar.py advise spot     --project my-project --machine-type a3-highgpu-8g --regions us-central1
  python capacity_radar.py advise calendar --project my-project --machine-type a3-highgpu-8g --vm-count 4 --duration-days 7
  python capacity_radar.py advise flex      --project my-project --machine-type a3-highgpu-8g --size 4 --max-run-hours 24 --regions us-central1

  # 4) Deploy with a priority strategy (creates real GCP resources — costs money)
  python capacity_radar.py deploy \
      --project my-project --machine-type a3-highgpu-8g --vm-count 2 \
      --priority spot:us-central1-b,us-east4-a \
      --priority dws_flex:us-central1-b \
      --yes
"""

import argparse
import asyncio
import json
import os
import sys

# Make the backend importable regardless of where this script is invoked from.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.abspath(os.path.join(_HERE, "..", "..", "..", "backend"))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def _out(obj):
    """Print a JSON result to stdout."""
    print(json.dumps(obj, indent=2, default=str))


def _err(msg, **extra):
    payload = {"ok": False, "error": msg}
    payload.update(extra)
    print(json.dumps(payload, indent=2, default=str))
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# auth
# ─────────────────────────────────────────────────────────────────────────────
def cmd_auth_check(args):
    """Check ADC auth and (optionally) project access + Compute API status."""
    import httpx
    result = {
        "authenticated": False,
        "projectValid": False,
        "computeApiEnabled": False,
        "account": None,
        "project": args.project or None,
        "errors": [],
        "instructions": [],
    }
    try:
        import google.auth
        import google.auth.transport.requests
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        creds.refresh(google.auth.transport.requests.Request())
        token = creds.token
        result["authenticated"] = True
        result["account"] = getattr(creds, "service_account_email", None) or "user-adc"
    except Exception as e:
        result["errors"].append(f"Not authenticated: {e}")
        result["instructions"].append(
            "Run: gcloud auth application-default login "
            "(or: python capacity_radar.py auth login)"
        )
        _out(result)
        return

    if not args.project:
        result["instructions"].append(
            "Pass --project <PROJECT_ID> to also verify project access."
        )
        _out(result)
        return

    try:
        resp = httpx.get(
            f"https://compute.googleapis.com/compute/v1/projects/{args.project}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if resp.status_code == 200:
            result["projectValid"] = True
            result["computeApiEnabled"] = True
        elif resp.status_code == 403:
            msg = resp.json().get("error", {}).get("message", "")
            if "has not been used" in msg or "is disabled" in msg:
                result["projectValid"] = True
                result["computeApiEnabled"] = False
                result["errors"].append("Compute Engine API is not enabled for this project.")
                result["instructions"].append(
                    f"Enable it: gcloud services enable compute.googleapis.com --project={args.project}"
                )
            else:
                result["errors"].append(f"Permission denied on project '{args.project}'.")
                result["instructions"].append(
                    "Ensure your account has 'Compute Admin' or 'Editor' on the project."
                )
        elif resp.status_code == 404:
            result["errors"].append(f"Project '{args.project}' not found. Check the ID.")
        else:
            msg = resp.json().get("error", {}).get("message", f"HTTP {resp.status_code}")
            result["errors"].append(f"Project check failed: {msg}")
    except Exception as e:
        result["errors"].append(f"Failed to verify project: {e}")

    result["ok"] = result["authenticated"]
    _out(result)


def cmd_auth_login(args):
    """Trigger `gcloud auth application-default login` (opens a browser)."""
    import subprocess
    try:
        proc = subprocess.run(
            ["gcloud", "auth", "application-default", "login", "--launch-browser"],
            capture_output=True, text=True,
        )
        ok = proc.returncode == 0
        _out({
            "ok": ok,
            "message": "Authentication complete. Re-run `auth check --project ...` to verify."
            if ok else "Login process finished; verify with `auth check`.",
            "stderr": proc.stderr[-500:] if proc.stderr else "",
        })
    except FileNotFoundError:
        _err("gcloud CLI not found. Install the Google Cloud SDK first.")


# ─────────────────────────────────────────────────────────────────────────────
# catalog
# ─────────────────────────────────────────────────────────────────────────────
def cmd_catalog_machine_types(args):
    from gpu_data import get_all_machine_types_info
    _out({"ok": True, "machineTypes": get_all_machine_types_info()})


def cmd_catalog_chips(args):
    from gpu_data import get_chip_groups
    groups = get_chip_groups()
    groups["ok"] = True
    _out(groups)


def cmd_catalog_zones(args):
    from gpu_data import get_zones_for_machine_type
    zones = get_zones_for_machine_type(args.machine_type)
    if not zones:
        _err(f"Unknown machine type '{args.machine_type}'.")
    regions = sorted({z.rsplit("-", 1)[0] for z in zones})
    _out({"ok": True, "machineType": args.machine_type, "zones": zones, "regions": regions})


# ─────────────────────────────────────────────────────────────────────────────
# advise
# ─────────────────────────────────────────────────────────────────────────────
def cmd_advise(args):
    import advisory

    regions = [r for r in (args.regions or "").split(",") if r] or None
    zones = [z for z in (args.zones or "").split(",") if z] or None

    async def run():
        if args.kind == "spot":
            return await advisory.get_spot_advisory(
                project=args.project, machine_type=args.machine_type,
                regions=regions, zones=zones,
            )
        if args.kind == "calendar":
            return await advisory.get_calendar_advisory(
                project=args.project, machine_type=args.machine_type,
                vm_count=args.vm_count, start_date=args.start_date or "",
                flexibility_days=args.flexibility_days, duration_days=args.duration_days,
                regions=regions, zones=zones,
            )
        if args.kind == "calendar-plan":
            return await advisory.find_best_splits(
                project=args.project, machine_type=args.machine_type,
                vm_count=args.vm_count, start_date=args.start_date or "",
                flexibility_days=args.flexibility_days, duration_days=args.duration_days,
                regions=regions, zones=zones,
            )
        if args.kind == "flex":
            return await advisory.get_flex_advisory(
                project=args.project, machine_type=args.machine_type,
                size=args.size, max_run_duration_hours=args.max_run_hours,
                regions=regions, zones=zones,
            )
        raise ValueError(f"Unknown advisory kind: {args.kind}")

    try:
        result = asyncio.run(run())
        result["ok"] = True
        result["advisory"] = args.kind
        _out(result)
    except Exception as e:
        _err(str(e), advisory=args.kind)


# ─────────────────────────────────────────────────────────────────────────────
# deploy
# ─────────────────────────────────────────────────────────────────────────────
def _parse_priority(spec: str) -> dict:
    """Parse a --priority spec of the form:
        method[:zone1,zone2][:max_retries][:retry_interval]
    e.g. "spot:us-central1-b,us-east4-a", "dws_flex:us-central1-b:3:60"
    """
    parts = spec.split(":")
    method = parts[0].strip()
    zones = []
    max_retries = 5
    retry_interval = 60
    if len(parts) > 1 and parts[1]:
        zones = [z for z in parts[1].split(",") if z]
    if len(parts) > 2 and parts[2]:
        max_retries = int(parts[2])
    if len(parts) > 3 and parts[3]:
        retry_interval = int(parts[3])
    return {
        "method": method,
        "zones": zones,
        "max_retries": max_retries,
        "retry_interval": retry_interval,
        "name_prefix": "",
        "flex_max_wait_hours": 168,
        "flex_usage_duration_hours": 24,
        "calendar_start_time": "",
        "calendar_end_time": "",
    }


def cmd_deploy(args):
    import hunter
    from gpu_data import get_zones_for_machine_type

    valid_methods = {"on_demand", "dws_calendar", "dws_flex", "spot"}
    priorities = []
    for spec in args.priority:
        p = _parse_priority(spec)
        if p["method"] not in valid_methods:
            _err(f"Invalid method '{p['method']}'. Valid: {sorted(valid_methods)}")
        if not p["zones"]:
            # Default to all supported zones for the machine type.
            p["zones"] = get_zones_for_machine_type(args.machine_type)
        if args.name_prefix:
            p["name_prefix"] = args.name_prefix
        if args.calendar_start:
            p["calendar_start_time"] = args.calendar_start
        if args.calendar_end:
            p["calendar_end_time"] = args.calendar_end
        p["flex_max_wait_hours"] = args.flex_max_wait_hours
        p["flex_usage_duration_hours"] = args.flex_usage_hours
        priorities.append(p)

    if not priorities:
        _err("At least one --priority is required (e.g. --priority spot:us-central1-b).")

    if not args.yes:
        _err(
            "Refusing to deploy without confirmation. This creates REAL GCP resources "
            "that cost money. Re-run with --yes once the user has explicitly confirmed.",
            requiresConfirmation=True,
            plan={
                "project": args.project,
                "machineType": args.machine_type,
                "vmCount": args.vm_count,
                "mode": "parallel" if args.parallel else "sequential",
                "priorities": [
                    {"method": p["method"], "zones": p["zones"]} for p in priorities
                ],
            },
        )

    events = []

    async def send_update(update):
        events.append(update)
        # Stream a compact line to stderr so agents can show live progress.
        line = f"[{update.get('type','')}] {update.get('message','')}"
        print(line, file=sys.stderr, flush=True)

    async def run():
        session = hunter.create_session(
            project=args.project,
            machine_type=args.machine_type,
            vm_count=args.vm_count,
            priorities=priorities,
            send_update=send_update,
            dws_calendar_duration_hours=args.calendar_duration_hours,
        )
        await session.run(parallel=args.parallel)
        return session

    try:
        session = asyncio.run(run())
        _out({
            "ok": session.status.value == "success",
            "status": session.status.value,
            "sessionId": session.session_id,
            "result": session.result,
            "events": events,
        })
    except Exception as e:
        _err(str(e), events=events)


# ─────────────────────────────────────────────────────────────────────────────
# argument parser
# ─────────────────────────────────────────────────────────────────────────────
def build_parser():
    p = argparse.ArgumentParser(
        prog="capacity_radar.py",
        description="Capacity Radar CLI — auth, advisories, and priority-based deploy for GCP GPUs/TPUs.",
    )
    sub = p.add_subparsers(dest="group", required=True)

    # auth
    auth = sub.add_parser("auth", help="Authentication commands")
    auth_sub = auth.add_subparsers(dest="cmd", required=True)
    a_check = auth_sub.add_parser("check", help="Check ADC auth (+ optional project access)")
    a_check.add_argument("--project", default="")
    a_check.set_defaults(func=cmd_auth_check)
    a_login = auth_sub.add_parser("login", help="Run gcloud ADC login (opens browser)")
    a_login.set_defaults(func=cmd_auth_login)

    # catalog
    cat = sub.add_parser("catalog", help="List machine types, chips, and zones")
    cat_sub = cat.add_subparsers(dest="cmd", required=True)
    c_mt = cat_sub.add_parser("machine-types", help="All GPU/TPU machine types + support matrix")
    c_mt.set_defaults(func=cmd_catalog_machine_types)
    c_chips = cat_sub.add_parser("chips", help="Machine types grouped by chip")
    c_chips.set_defaults(func=cmd_catalog_chips)
    c_zones = cat_sub.add_parser("zones", help="Supported zones for a machine type")
    c_zones.add_argument("--machine-type", required=True)
    c_zones.set_defaults(func=cmd_catalog_zones)

    # advise
    adv = sub.add_parser("advise", help="Run a capacity advisory")
    adv_sub = adv.add_subparsers(dest="kind", required=True)

    def _common_advise(sp):
        sp.add_argument("--project", required=True)
        sp.add_argument("--machine-type", required=True)
        sp.add_argument("--regions", default="", help="Comma-separated regions")
        sp.add_argument("--zones", default="", help="Comma-separated zones (optional filter)")
        sp.set_defaults(func=cmd_advise)

    s_spot = adv_sub.add_parser("spot", help="Spot VM availability + preemption risk")
    _common_advise(s_spot)

    s_cal = adv_sub.add_parser("calendar", help="DWS Calendar availability")
    _common_advise(s_cal)
    s_cal.add_argument("--vm-count", type=int, default=1)
    s_cal.add_argument("--start-date", default="", help="YYYY-MM-DD")
    s_cal.add_argument("--flexibility-days", type=int, default=0)
    s_cal.add_argument("--duration-days", type=int, default=7)

    s_calp = adv_sub.add_parser("calendar-plan", help="DWS Calendar best split plan")
    _common_advise(s_calp)
    s_calp.add_argument("--vm-count", type=int, default=1)
    s_calp.add_argument("--start-date", default="", help="YYYY-MM-DD")
    s_calp.add_argument("--flexibility-days", type=int, default=0)
    s_calp.add_argument("--duration-days", type=int, default=7)

    s_flex = adv_sub.add_parser("flex", help="DWS Flex Start wait-time advisory (Preview/whitelisted)")
    _common_advise(s_flex)
    s_flex.add_argument("--size", type=int, default=1, help="Number of instances")
    s_flex.add_argument("--max-run-hours", type=int, default=24, help="Max run duration (<=168)")

    # deploy
    dep = sub.add_parser("deploy", help="Priority-based scan & deploy (creates REAL resources)")
    dep.add_argument("--project", required=True)
    dep.add_argument("--machine-type", required=True)
    dep.add_argument("--vm-count", type=int, default=1)
    dep.add_argument(
        "--priority", action="append", default=[],
        help="Repeatable. Format: method[:zones][:max_retries][:retry_interval]. "
             "method = on_demand|dws_calendar|dws_flex|spot. "
             "Example: spot:us-central1-b,us-east4-a",
    )
    dep.add_argument("--parallel", action="store_true", help="Run all priorities at once")
    dep.add_argument("--name-prefix", default="", help="Resource name prefix")
    dep.add_argument("--flex-max-wait-hours", type=int, default=168)
    dep.add_argument("--flex-usage-hours", type=int, default=24)
    dep.add_argument("--calendar-start", default="", help="ISO datetime for DWS Calendar")
    dep.add_argument("--calendar-end", default="", help="ISO datetime for DWS Calendar")
    dep.add_argument("--calendar-duration-hours", type=int, default=24)
    dep.add_argument("--yes", action="store_true",
                     help="Confirm real resource creation (required to actually deploy)")
    dep.set_defaults(func=cmd_deploy)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
