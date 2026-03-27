"""
sumo.py — TraffiQ SUMO TraCI Interface
Streams exact TraCI data — phase, duration, vehicles, emergency.
No mock, no smart mode, no client-side logic.
"""

import os
import time
import threading
import subprocess

try:
    import traci
    TRACI_AVAILABLE = True
except ImportError:
    TRACI_AVAILABLE = False
    print("[TraffiQ] WARNING: traci not installed.")

SUMO_CFG    = os.path.join(os.path.dirname(__file__), "final.sumocfg")
SUMO_BINARY = "sumo-gui"
TRACI_PORT  = 8813

_sumo_started = False
_sumo_process = None
_sim_step     = 0
_lock         = threading.Lock()


def start_sumo():
    global _sumo_started, _sumo_process, _lane_ids
    if not TRACI_AVAILABLE:
        print("[TraffiQ] TraCI unavailable.")
        return False
    if _sumo_started:
        return True
    if not os.path.exists(SUMO_CFG):
        print(f"[TraffiQ] Config not found: {SUMO_CFG}")
        return False
    try:
        print(f"[TraffiQ] Launching sumo-gui: {SUMO_CFG}")
        cmd = [
            SUMO_BINARY, "-c", SUMO_CFG,
            "--remote-port", str(TRACI_PORT),
            "--no-step-log", "true",
            "--collision.action", "none",
            "--start", "--quit-on-end", "false"
        ]
        _sumo_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[TraffiQ] sumo-gui PID: {_sumo_process.pid} — waiting for TraCI...")
        for _ in range(30):
            time.sleep(0.5)
            try:
                traci.init(port=TRACI_PORT, numRetries=1)
                _sumo_started = True
                print(f"[TraffiQ] TraCI connected ✓")

                # ── DEBUG: print all lane IDs on connect ──
                all_lanes = traci.lane.getIDList()
                filtered  = [l for l in all_lanes if not l.startswith(':')]
                print(f"[TraffiQ] ALL LANES: {all_lanes}")
                print(f"[TraffiQ] FILTERED LANES (no junctions): {filtered}")
                print(f"[TraffiQ] TL controlled lanes: {list(traci.trafficlight.getControlledLanes(traci.trafficlight.getIDList()[0]))}")

                return True
            except Exception:
                pass
        print("[TraffiQ] TraCI timed out.")
        return False
    except Exception as e:
        print(f"[TraffiQ] Error: {e}")
        return False


def stop_sumo():
    global _sumo_started, _sumo_process
    if TRACI_AVAILABLE and _sumo_started:
        try: traci.close()
        except: pass
    if _sumo_process:
        try: _sumo_process.terminate()
        except: pass
    _sumo_started = False
    _sumo_process = None


def get_lane_data():
    global _sim_step
    with _lock:
        if not (TRACI_AVAILABLE and _sumo_started):
            return {"error": "SUMO not connected", "lanes": {}, "source": "none"}

        try:
            traci.simulationStep()
            _sim_step += 1
        except Exception as e:
            return {"error": str(e), "lanes": {}, "source": "none"}

        lanes = {}
        try:
            all_lane_ids = traci.lane.getIDList()
            tl_ids = traci.trafficlight.getIDList()
            lane_ids = list(traci.trafficlight.getControlledLanes(tl_ids[0]))[:4]

            # ── Get exact phase + remaining duration from SUMO ──
            tl_data = {}   # lane_id → { phase, time_remaining }
            try:
                for tl_id in traci.trafficlight.getIDList():
                    state          = traci.trafficlight.getRedYellowGreenState(tl_id)
                    controlled     = traci.trafficlight.getControlledLanes(tl_id)
                    time_remaining = traci.trafficlight.getNextSwitch(tl_id) - traci.simulation.getTime()
                    time_remaining = max(0, round(time_remaining))

                    for i, cl in enumerate(controlled):
                        if i < len(state):
                            c = state[i].lower()
                            if c == 'g':
                                ph = 'green'
                            elif c == 'y':
                                ph = 'amber'
                            else:
                                ph = 'red'
                            tl_data[cl] = {
                                "phase":          ph,
                                "time_remaining": time_remaining
                            }
            except Exception as e:
                print(f"[TraffiQ] TL error: {e}")

            for lane_id in lane_ids:
                try:
                    vehicle_ids   = traci.lane.getLastStepVehicleIDs(lane_id)
                    vehicle_count = len(vehicle_ids)
                    wait_time     = round(traci.lane.getWaitingTime(lane_id), 1)

                    # Emergency detection
                    emergency = False
                    for vid in vehicle_ids:
                        try:
                            vtype = traci.vehicle.getTypeID(vid).lower()
                            if any(k in vtype for k in ["emergency","ambulance","police","fire"]):
                                emergency = True
                                break
                        except: pass

                    tl_info = tl_data.get(lane_id, {"phase": "red", "time_remaining": 0})

                    lanes[lane_id] = {
                        "vehicles":       vehicle_count,
                        "emergency":      emergency,
                        "wait_time":      wait_time,
                        "phase":          tl_info["phase"],
                        "time_remaining": tl_info["time_remaining"],  # exact SUMO timer
                    }
                except Exception as e:
                    print(f"[TraffiQ] Lane {lane_id}: {e}")

            return {
                "lanes":    lanes,
                "sim_step": _sim_step,
                "source":   "traci",
            }

        except Exception as e:
            return {"error": str(e), "lanes": {}, "source": "none"}