import os
import traci

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SUMO_CONFIG = os.path.join(BASE_DIR, "final.sumocfg")

sumo_running = False

def start_sumo():
    global sumo_running

    if not sumo_running:
        sumoCmd = ["sumo-gui", "-c", SUMO_CONFIG]
        traci.start(sumoCmd)
        sumo_running = True


def get_lane_data():
    start_sumo()

    traci.simulationStep()

    lanes = traci.lane.getIDList()

    lane_data = {}

    for lane in lanes[:4]:
        lane_data[lane] = traci.lane.getLastStepVehicleNumber(lane)

    total = sum(lane_data.values())

    print("LANE DATA:", lane_data)

    return {
        "totalVehicles": total,
        "lanes": lane_data
    }