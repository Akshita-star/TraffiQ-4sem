import traci
import os
import sys

SUMO_CONFIG = "simulation/final.sumocfg"   

sumo_running = False

def start_simulation():
    global sumo_running

    if not sumo_running:
        sumo_cmd = ["sumo", "-c", SUMO_CONFIG]
        traci.start(sumo_cmd)
        sumo_running = True


def get_lane_data():
    start_simulation()

    traci.simulationStep()

    lanes = {}

    for lane in traci.lane.getIDList():
        vehicle_count = traci.lane.getLastStepVehicleNumber(lane)

        emergency = False
        vehicles = traci.lane.getLastStepVehicleIDs(lane)

        for v in vehicles:
            if "ambulance" in v or "emergency" in v:
                emergency = True
                break

        lanes[lane] = {
            "vehicles": vehicle_count,
            "emergency": emergency
        }

    return {"lanes": lanes}