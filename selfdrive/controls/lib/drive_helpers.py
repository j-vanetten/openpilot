from common.numpy_fast import clip, interp
from selfdrive.config import Conversions as CV
from cereal import car

# kph
V_CRUISE_MAX = 135
V_CRUISE_MIN = 8
V_CRUISE_DELTA = 8
V_CRUISE_ENABLE_MIN = 32 # FCA gets down to 32
MPC_N = 16
CAR_ROTATION_RADIUS = 0.0

class MPC_COST_LAT:
  PATH = 1.0
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


def update_v_cruise(v_cruise_kph, button_events, enabled, acc_button_long_press, reverse_acc_button_change):
  # handle button presses. TODO: this should be in state_control, but a decelCruise press
  # would have the effect of both enabling and changing speed is checked after the state transition
  for b in button_events:
    if enabled:
      short_press = not b.pressed and b.pressedFrames < acc_button_long_press
      long_press = b.pressed and b.pressedFrames == acc_button_long_press \
                   or ((not reverse_acc_button_change) and b.pressedFrames % 50 == 0 and b.pressedFrames > acc_button_long_press)

      if reverse_acc_button_change:
        short_press = not short_press
        long_press = not long_press

      if long_press:
        if b.type == car.CarState.ButtonEvent.Type.accelCruise:
          v_cruise_kph += V_CRUISE_DELTA - (v_cruise_kph % V_CRUISE_DELTA)
        elif b.type == car.CarState.ButtonEvent.Type.decelCruise:
          v_cruise_kph -= V_CRUISE_DELTA - ((V_CRUISE_DELTA - v_cruise_kph) % V_CRUISE_DELTA)
        v_cruise_kph = clip(v_cruise_kph, V_CRUISE_MIN, V_CRUISE_MAX)
      elif short_press:
        if b.type == car.CarState.ButtonEvent.Type.accelCruise:
          v_cruise_kph += CV.MPH_TO_KPH
        elif b.type == car.CarState.ButtonEvent.Type.decelCruise:
          v_cruise_kph -= CV.MPH_TO_KPH

  return max(v_cruise_kph, V_CRUISE_ENABLE_MIN)


def initialize_v_cruise(v_ego, button_events, v_cruise_last):
  # 250kph or above probably means we never had a set speed
  if v_cruise_last < 250:
    for b in button_events:
      if b.type == "resumeCruise":
        return v_cruise_last

  return int(round(clip(v_ego * CV.MS_TO_KPH, V_CRUISE_ENABLE_MIN, V_CRUISE_MAX)))