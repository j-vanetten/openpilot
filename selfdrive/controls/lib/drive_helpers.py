from common.numpy_fast import clip, interp
from selfdrive.config import Conversions as CV
from cereal import car
from common.op_params import opParams

# kph
V_CRUISE_MAX = 144
V_CRUISE_MIN = 8
V_CRUISE_DELTA = 8
V_CRUISE_ENABLE_MIN = 32 # FCA gets down to 32
V_CRUISE_REVERSE_INCREMENTS = opParams().get('reverse_acc_increments')

class MPC_COST_LAT:
  PATH = 1.0
  LANE = 3.0
  HEADING = 1.0
  STEER_RATE = 1.0


class MPC_COST_LONG:
  TTC = 5.0
  DISTANCE = 0.1
  ACCELERATION = 10.0
  JERK = 20.0


def rate_limit(new_value, last_value, dw_step, up_step):
  return clip(new_value, last_value + dw_step, last_value + up_step)


def get_steer_max(CP, v_ego):
  return interp(v_ego, CP.steerMaxBP, CP.steerMaxV)

def update_v_cruise(v_cruise_kph, buttonEvents, enabled, buttonPressTimes):
  V_CRUISE_SINGLE_INCREMENTS = True

  # handle button presses. TODO: this should be in state_control, but a decelCruise press
  # would have the effect of both enabling and changing speed is checked after the state transition
  if enabled:
    for b in buttonEvents:
      if b in buttonPressTimes:
        speedAdjust = None
        if b.type == car.CarState.ButtonEvent.Type.accelCruise:
          speedAdjust = [CV.MPH_TO_KPH, V_CRUISE_DELTA - (v_cruise_kph % V_CRUISE_DELTA)]
        elif b.type == car.CarState.ButtonEvent.Type.decelCruise:
          speedAdjust = [-CV.MPH_TO_KPH, -(V_CRUISE_DELTA - ((V_CRUISE_DELTA - v_cruise_kph) % V_CRUISE_DELTA))]

        if speedAdjust is not None:
          pressTime = buttonPressTimes[b]
          if pressTime < 100:
            if not b.pressed:
              v_cruise_kph += speedAdjust[0 if V_CRUISE_REVERSE_INCREMENTS else 1]
          elif b.pressed and pressTime % 50 == 0:
            v_cruise_kph += speedAdjust[1 if V_CRUISE_REVERSE_INCREMENTS else 0]

          v_cruise_kph = clip(v_cruise_kph, V_CRUISE_MIN, V_CRUISE_MAX)

  return v_cruise_kph


def initialize_v_cruise(v_ego, buttonEvents, v_cruise_last):
  for b in buttonEvents:
    # 250kph or above probably means we never had a set speed
    if (b.type == car.CarState.ButtonEvent.Type.accelCruise or b.type == car.CarState.ButtonEvent.Type.resumeCruise) and v_cruise_last < 250:
      return v_cruise_last

  return int(round(clip(v_ego * CV.MS_TO_KPH, V_CRUISE_ENABLE_MIN, V_CRUISE_MAX)))
