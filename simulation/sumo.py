import os
import time
import threading #to accept one  requuest at a tiem
import subprocess #start sumo from python
import heapq #priority quuee

try:
    import traci
    TRACI_AVAILABLE = True
except ImportError:
    TRACI_AVAILABLE = False
    print("traci not working properly(line11).")

SUMO_CFG    = os.path.join(os.path.dirname(__file__), "final.sumocfg")
SUMO_BINARY = "sumo-gui"
TRACI_PORT  = 8813

_sumo_started = False
_sumo_process = None
_sim_step     = 0
_lock         = threading.Lock()


def calculate_priority(lane_data):
    score = 0
    score += lane_data["vehicles"] * 2
    score += lane_data["wait_time"] * 0.5
    return score


def start_sumo():
    global _sumo_started, _sumo_process, _lane_ids
    if not TRACI_AVAILABLE:
        print("TraCI unavailable.")
        return False
    if _sumo_started: #ie.e. if sumo already running and is true then  it doesnt run multiple times
        return True
    if not os.path.exists(SUMO_CFG):#check file exists
        print("not found dile")
        return False
    try:
        print(f"[TraffiQ] Launching sumo-gui: {SUMO_CFG}")
        cmd = [ #officislly laucn sumo
            SUMO_BINARY, "-c", SUMO_CFG,
            "--remote-port", str(TRACI_PORT),#8813
            "--no-step-log", "true",
            "--collision.action", "none",
            "--start", "--quit-on-end", "false"
        ]
        _sumo_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[TraffiQ] sumo-gui PID: {_sumo_process.pid} — waiting for TraCI")
        for _ in range(30):
            time.sleep(0.5)
            try:
                traci.init(port=TRACI_PORT, numRetries=1)
                _sumo_started = True
                print("TraCI connected ")

                all_lanes = traci.lane.getIDList()
                filtered  = [l for l in all_lanes if not l.startswith(':')]
                print(f"ALL LANES: {all_lanes}")
                print(f"FILTERED LANES (no junctions): {filtered}")
                print(f"TL controlled lanes: {list(traci.trafficlight.getControlledLanes(traci.trafficlight.getIDList()[0]))}")
                return True
            except Exception:
                pass
        print("TraCI timed out.")#if not connected with 30tries
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False


def stop_sumo():
    global _sumo_started, _sumo_process
    if TRACI_AVAILABLE and _sumo_started:
        try: 
            traci.close()
        except: 
            pass
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
            tl_ids   = traci.trafficlight.getIDList()
            lane_ids = list(traci.trafficlight.getControlledLanes(tl_ids[0]))[:4]

            # ── Traffic light phase + timer ──
            tl_data = {}
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

            # ── Lane data fetch ──
            for lane_id in lane_ids:
                try:
                    vehicle_ids   = traci.lane.getLastStepVehicleIDs(lane_id)
                    vehicle_count = len(vehicle_ids)
                    wait_time     = round(traci.lane.getWaitingTime(lane_id), 1)

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
                        "time_remaining": tl_info["time_remaining"],
                    }
                except Exception as e:
                    print(f"[TraffiQ] Lane {lane_id}: {e}")
#akshita
            heap = []
            for lane_id, data in lanes.items():
                score = calculate_priority(data)
                heapq.heappush(heap, (-score, lane_id))

            # sorted priority order — index 0 = highest priority
            priority_order = []
            temp_heap = heap.copy()
            while temp_heap:
                priority_order.append(heapq.heappop(temp_heap)[1])

            top_priority_lane = priority_order[0] if priority_order else None

            # score bhi attach karo har lane ke saath — dashboard pe dikhega
            for rank, lane_id in enumerate(priority_order):
                if lane_id in lanes:
                    lanes[lane_id]["priority_rank"] = rank + 1
                    lanes[lane_id]["priority_score"] = round(
                        calculate_priority(lanes[lane_id]), 1
                    )

            return {
                "lanes":             lanes,
                "sim_step":          _sim_step,
                "source":            "traci",
                "priority_order":    priority_order,
                "top_priority_lane": top_priority_lane,
            }

        except Exception as e:
            return {"error": str(e), "lanes": {}, "source": "none"}