from common.numpy_fast import clip, interp
from selfdrive.config import Conversions as CV
from cereal import car

# kph
V_CRUISE_MAX = 135
V_CRUISE_MIN = 8
V_CRUISE_DELTA = 8
V_CRUISE_ENABLE_MIN = 32  # FCA gets down to 32
MPC_N = 16
CAR_ROTATION_RADIUS = 0.0

# metric
V_CRUISE_MIN_METRIC = 10
V_CRUISE_DELTA_METRIC = 5
V_CRUISE_ENABLE_MIN_METRIC = 30  # FCA gets down to 30

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
  if enabled:
    v_cruise_delta = cruise_delta_5(is_metric)
    v_cruise_min = cruise_min(is_metric)
    for b in button_events:
      short_press = not b.pressed and b.pressedFrames < 30
      long_press = b.pressed and b.pressedFrames == 30 \
                   or ((not reverse_acc_button_change) and b.pressedFrames % 50 == 0 and b.pressedFrames > 50)

      if reverse_acc_button_change:
        sp = short_press
        short_press = long_press
        long_press = sp

      if long_press:
        if b.type == car.CarState.ButtonEvent.Type.accelCruise:
          v_cruise_kph += v_cruise_delta - (v_cruise_kph % v_cruise_delta)
        elif b.type == car.CarState.ButtonEvent.Type.decelCruise:
          v_cruise_kph -= v_cruise_delta - ((v_cruise_delta - v_cruise_kph) % v_cruise_delta)
        v_cruise_kph = clip(v_cruise_kph, v_cruise_min, V_CRUISE_MAX)
      elif short_press:
        if b.type == car.CarState.ButtonEvent.Type.accelCruise:
          v_cruise_kph += cruise_delta_1(is_metric)
        elif b.type == car.CarState.ButtonEvent.Type.decelCruise:
          v_cruise_kph -= cruise_delta_1(is_metric)

  return max(v_cruise_kph, cruise_min(is_metric))


def initialize_v_cruise(v_ego, button_events, v_cruise_last, is_metric):
  # 250kph or above probably means we never had a set speed
  if v_cruise_last < 250:
    for b in button_events:
      if b.type == "resumeCruise":
        return v_cruise_last

  return int(round(clip(v_ego * CV.MS_TO_KPH, cruise_enabled(is_metric), V_CRUISE_MAX)))


def cruise_min(is_metric):
  return V_CRUISE_MIN_METRIC if is_metric else V_CRUISE_MIN


def cruise_delta_5(is_metric):
  return V_CRUISE_DELTA_METRIC if is_metric else V_CRUISE_DELTA


def cruise_delta_1(is_metric):
  return 1 if is_metric else CV.MPH_TO_KPH


def cruise_enabled(is_metric):
  return V_CRUISE_ENABLE_MIN_METRIC if is_metric else V_CRUISE_ENABLE_MIN
