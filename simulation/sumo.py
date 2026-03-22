"""
sumo.py — TraffiQ SUMO TraCI Interface
Auto-launches sumo-gui on startup, streams live data via TraCI.
Falls back to mock data if SUMO not available.
"""

import os
import sys
import time
import random
import threading
import subprocess

# ── TraCI import ──
try:
    import traci
    import traci.constants as tc
    TRACI_AVAILABLE = True
except ImportError:
    TRACI_AVAILABLE = False
    print("[TraffiQ] WARNING: traci not installed. Using mock data.")

# ── Config ──
SUMO_CFG    = os.path.join(os.path.dirname(__file__), "final.sumocfg")
SUMO_BINARY = "sumo-gui"     # launches the GUI automatically
TRACI_PORT  = 8813

# ── Global state ──
_sumo_started    = False
_sumo_process    = None
_sim_step        = 0
_mock_state      = {}
_lock            = threading.Lock()

# Fixed cycle state
_normal_cycle_index = 0
_normal_cycle_timer = 0
FIXED_GREEN_DURATION = 20   # seconds per lane


# ════════════════════════════════════════════
#  AUTO-LAUNCH sumo-gui
# ════════════════════════════════════════════

def start_sumo():
    """
    Launch sumo-gui as a subprocess, then connect TraCI to it.
    Called once at Flask startup.
    """
    global _sumo_started, _sumo_process

    if not TRACI_AVAILABLE:
        print("[TraffiQ] TraCI unavailable — mock mode.")
        return False

    if _sumo_started:
        return True

    if not os.path.exists(SUMO_CFG):
        print(f"[TraffiQ] Config not found: {SUMO_CFG} — mock mode.")
        return False

    try:
        print(f"[TraffiQ] Launching sumo-gui with config: {SUMO_CFG}")

        # Launch sumo-gui with --remote-port so TraCI can connect
        cmd = [
            SUMO_BINARY,
            "-c", SUMO_CFG,
            "--remote-port", str(TRACI_PORT),
            "--no-step-log", "true",
            "--collision.action", "none",
            "--start",              # auto-start simulation
            "--quit-on-end", "false"
        ]

        _sumo_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        print(f"[TraffiQ] sumo-gui PID: {_sumo_process.pid} — waiting for TraCI port...")

        # Wait for sumo-gui to open port (max 15 seconds)
        for attempt in range(30):
            time.sleep(0.5)
            try:
                traci.init(port=TRACI_PORT, numRetries=1)
                _sumo_started = True
                print(f"[TraffiQ] TraCI connected on port {TRACI_PORT} ✓")
                return True
            except Exception:
                pass

        print("[TraffiQ] TraCI connection timed out — mock mode.")
        return False

    except FileNotFoundError:
        print(f"[TraffiQ] '{SUMO_BINARY}' not found in PATH — mock mode.")
        return False
    except Exception as e:
        print(f"[TraffiQ] SUMO launch error: {e} — mock mode.")
        return False


def stop_sumo():
    """Cleanly close TraCI and terminate sumo-gui."""
    global _sumo_started, _sumo_process
    if TRACI_AVAILABLE and _sumo_started:
        try:
            traci.close()
        except Exception:
            pass
    if _sumo_process:
        try:
            _sumo_process.terminate()
        except Exception:
            pass
    _sumo_started = False
    _sumo_process = None


# ════════════════════════════════════════════
#  FIXED CYCLE (Normal Mode)
# ════════════════════════════════════════════

def tick_normal_cycle(lane_ids: list) -> tuple:
    """Returns (active_lane_id, green_time_remaining)."""
    global _normal_cycle_index, _normal_cycle_timer

    if not lane_ids:
        return None, 0

    _normal_cycle_index = _normal_cycle_index % len(lane_ids)
    active_lane = lane_ids[_normal_cycle_index]
    time_left   = max(0, FIXED_GREEN_DURATION - _normal_cycle_timer)

    _normal_cycle_timer += 2   # called every ~2 seconds from frontend poll

    if _normal_cycle_timer >= FIXED_GREEN_DURATION:
        _normal_cycle_timer  = 0
        _normal_cycle_index  = (_normal_cycle_index + 1) % len(lane_ids)

    return active_lane, round(time_left)


# ════════════════════════════════════════════
#  SMART ALGORITHM
# ════════════════════════════════════════════

def compute_priority(vehicles: int, emergency: bool, wait_time: float = 0) -> float:
    base  = vehicles * 5
    emg   = 200 if emergency else 0
    wait  = wait_time * 0.5
    return round(base + emg + wait, 1)


def decide_smart_signal(lanes: dict) -> str:
    best_lane, best_score = None, -1
    for lid, info in lanes.items():
        score = info.get("priority_score", 0)
        if score > best_score:
            best_score = score
            best_lane  = lid
    return best_lane


# ════════════════════════════════════════════
#  LIVE TRACI DATA
# ════════════════════════════════════════════

def _get_live_data() -> dict:
    global _sim_step

    try:
        traci.simulationStep()
        _sim_step += 1
    except Exception as e:
        print(f"[TraffiQ] simulationStep error: {e}")
        return {}

    lanes = {}
    try:
        all_lane_ids = traci.lane.getIDList()
        # Skip internal lanes
        lane_ids = [l for l in all_lane_ids if not l.startswith(":")]

        # Get traffic light phases from SUMO directly
        tl_phases = {}   # lane_id → 'green'|'amber'|'red'
        try:
            for tl_id in traci.trafficlight.getIDList():
                state = traci.trafficlight.getRedYellowGreenState(tl_id)
                controlled = traci.trafficlight.getControlledLanes(tl_id)
                for i, cl in enumerate(controlled):
                    if i < len(state):
                        c = state[i].lower()
                        if c in ('g', 'G'):
                            tl_phases[cl] = 'green'
                        elif c in ('y', 'Y'):
                            tl_phases[cl] = 'amber'
                        else:
                            tl_phases[cl] = 'red'
        except Exception:
            pass

        for lane_id in lane_ids:
            try:
                vehicle_ids   = traci.lane.getLastStepVehicleIDs(lane_id)
                vehicle_count = len(vehicle_ids)
                wait_time     = traci.lane.getWaitingTime(lane_id)

                # Detect emergency vehicles
                emergency      = False
                for vid in vehicle_ids:
                    try:
                        vtype = traci.vehicle.getTypeID(vid).lower()
                        if any(k in vtype for k in ["emergency","ambulance","police","fire"]):
                            emergency = True
                            break
                    except Exception:
                        pass

                priority = compute_priority(vehicle_count, emergency, wait_time)
                phase    = tl_phases.get(lane_id, None)  # actual SUMO phase

                lanes[lane_id] = {
                    "vehicles":       vehicle_count,
                    "emergency":      emergency,
                    "wait_time":      round(wait_time, 1),
                    "priority_score": priority,
                    "phase":          phase,   # 'green'|'amber'|'red'|None
                }

            except Exception as e:
                print(f"[TraffiQ] Lane {lane_id} error: {e}")

        lane_id_list             = list(lanes.keys())
        active_normal, time_left = tick_normal_cycle(lane_id_list)
        smart_active             = decide_smart_signal(lanes)

        for lid in lanes:
            lanes[lid]["normal_green_time"] = (
                time_left if lid == active_normal else 0
            )

        return {
            "lanes":              lanes,
            "sim_step":           _sim_step,
            "normal_active_lane": active_normal,
            "smart_active_lane":  smart_active,
            "source":             "traci",
        }

    except Exception as e:
        print(f"[TraffiQ] TraCI data error: {e}")
        return {}


# ════════════════════════════════════════════
#  MOCK DATA
# ════════════════════════════════════════════

MOCK_LANES = ["Lane_1", "Lane_2", "Lane_3", "Lane_4"]

def _get_mock_data() -> dict:
    global _mock_state, _sim_step, _normal_cycle_index, _normal_cycle_timer
    _sim_step += 1

    if not _mock_state:
        _mock_state = {
            lid: {
                "vehicles":    random.randint(2, 15),
                "emergency":   False,
                "wait_time":   random.uniform(0, 30),
                "emg_ttl":     0,
            }
            for lid in MOCK_LANES
        }

    for lid in MOCK_LANES:
        s = _mock_state[lid]
        s["vehicles"]  = max(0, min(25, s["vehicles"] + random.randint(-2, 3)))
        s["wait_time"] = max(0, s["wait_time"] + random.uniform(-1, 2))
        if not s["emergency"] and random.random() < 0.02:
            s["emergency"] = True
            s["emg_ttl"]   = 5
        elif s["emergency"]:
            s["emg_ttl"] -= 1
            if s["emg_ttl"] <= 0:
                s["emergency"] = False

    lanes = {}
    for lid in MOCK_LANES:
        s        = _mock_state[lid]
        priority = compute_priority(s["vehicles"], s["emergency"], s["wait_time"])
        lanes[lid] = {
            "vehicles":         s["vehicles"],
            "emergency":        s["emergency"],
            "wait_time":        round(s["wait_time"], 1),
            "priority_score":   priority,
            "phase":            None,   # client-side timer will handle
        }

    lane_id_list             = list(lanes.keys())
    active_normal, time_left = tick_normal_cycle(lane_id_list)
    smart_active             = decide_smart_signal(lanes)

    for lid in lanes:
        lanes[lid]["normal_green_time"] = (
            time_left if lid == active_normal else 0
        )

    return {
        "lanes":              lanes,
        "sim_step":           _sim_step,
        "normal_active_lane": active_normal,
        "smart_active_lane":  smart_active,
        "source":             "mock",
    }


# ════════════════════════════════════════════
#  PUBLIC API
# ════════════════════════════════════════════

def get_lane_data() -> dict:
    """Main entry point for app.py → /api/traffic"""
    with _lock:
        if TRACI_AVAILABLE and _sumo_started:
            data = _get_live_data()
            if data:
                return data
        return _get_mock_data()