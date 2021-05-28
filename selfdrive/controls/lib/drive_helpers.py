from common.numpy_fast import clip, interp
from selfdrive.config import Conversions as CV
from cereal import car

# kph
V_CRUISE_MAX = 135
V_CRUISE_MIN = 30  # Chrysler min ACC when metric
V_CRUISE_DELTA = 5  # ACC increments (unit agnostic)

MPC_N = 16
CAR_ROTATION_RADIUS = 0.0

V_CRUISE_MIN_IMPERIAL = int(20 * CV.MPH_TO_KPH)
V_CRUISE_DELTA_IMPERIAL = int(V_CRUISE_DELTA * CV.MPH_TO_KPH)

# metric

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


def update_v_cruise(v_cruise_kph, button_events, enabled, reverse_acc_button_change, is_metric):
  # handle button presses. TODO: this should be in state_control, but a decelCruise press
  # would have the effect of both enabling and changing speed is checked after the state transition
  v_cruise_min = cruise_min(is_metric)
  if enabled:
    for b in button_events:
      short_press = not b.pressed and b.pressedFrames < 30
      long_press = b.pressed and b.pressedFrames == 30 \
                   or ((not reverse_acc_button_change) and b.pressedFrames % 50 == 0 and b.pressedFrames > 50)

      if reverse_acc_button_change:
        sp = short_press
        short_press = long_press
        long_press = sp

      if long_press:
        v_cruise_delta_5 = V_CRUISE_DELTA if is_metric else V_CRUISE_DELTA_IMPERIAL
        if b.type == car.CarState.ButtonEvent.Type.accelCruise:
          v_cruise_kph += v_cruise_delta_5 - (v_cruise_kph % v_cruise_delta_5)
        elif b.type == car.CarState.ButtonEvent.Type.decelCruise:
          v_cruise_kph -= v_cruise_delta_5 - ((v_cruise_delta_5 - v_cruise_kph) % v_cruise_delta_5)
        v_cruise_kph = clip(v_cruise_kph, v_cruise_min, V_CRUISE_MAX)
      elif short_press:
        v_cruise_delta_1 = 1 if is_metric else CV.MPH_TO_KPH
        if b.type == car.CarState.ButtonEvent.Type.accelCruise:
          v_cruise_kph += v_cruise_delta_1
        elif b.type == car.CarState.ButtonEvent.Type.decelCruise:
          v_cruise_kph -= v_cruise_delta_1

  return max(v_cruise_kph, v_cruise_min)


def initialize_v_cruise(v_ego, button_events, v_cruise_last, is_metric):
  # 250kph or above probably means we never had a set speed
  if v_cruise_last < 250:
    for b in button_events:
      if b.type == "resumeCruise":
        return v_cruise_last

  return int(round(clip(v_ego * CV.MS_TO_KPH, cruise_min(is_metric), V_CRUISE_MAX)))


def cruise_min(is_metric):
  return V_CRUISE_MIN if is_metric else V_CRUISE_MIN_IMPERIAL
