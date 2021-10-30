import math
from cereal import car
from common.numpy_fast import clip, interp
from common.realtime import DT_MDL
from selfdrive.config import Conversions as CV
from selfdrive.modeld.constants import T_IDXS

# kph
V_CRUISE_MAX = 135
V_CRUISE_MIN = 30  # Chrysler min ACC when metric
V_CRUISE_DELTA = 5  # ACC increments (unit agnostic)
V_CRUISE_MIN_IMPERIAL = int(20 * CV.MPH_TO_KPH)
V_CRUISE_DELTA_IMPERIAL = int(V_CRUISE_DELTA * CV.MPH_TO_KPH)

LAT_MPC_N = 16
LON_MPC_N = 32
CONTROL_N = 17
CAR_ROTATION_RADIUS = 0.0

# this corresponds to 80deg/s and 20deg/s steering angle in a toyota corolla
MAX_CURVATURE_RATES = [0.03762194918267951, 0.003441203371932992]
MAX_CURVATURE_RATE_SPEEDS = [0, 35]

CRUISE_LONG_PRESS = 50
CRUISE_NEAREST_FUNC = {
  car.CarState.ButtonEvent.Type.accelCruise: math.ceil,
  car.CarState.ButtonEvent.Type.decelCruise: math.floor,
}
CRUISE_INTERVAL_SIGN = {
  car.CarState.ButtonEvent.Type.accelCruise: +1,
  car.CarState.ButtonEvent.Type.decelCruise: -1,
}


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
  return 10 if is_metric else int(5 * CV.MPH_TO_KPH)


def get_lag_adjusted_curvature(CP, v_ego, psis, curvatures, curvature_rates):
  if len(psis) != CONTROL_N:
    psis = [0.0 for i in range(CONTROL_N)]
    curvatures = [0.0 for i in range(CONTROL_N)]
    curvature_rates = [0.0 for i in range(CONTROL_N)]

  # TODO this needs more thought, use .2s extra for now to estimate other delays
  delay = CP.steerActuatorDelay + .2
  current_curvature = curvatures[0]
  psi = interp(delay, T_IDXS[:CONTROL_N], psis)
  desired_curvature_rate = curvature_rates[0]

  # MPC can plan to turn the wheel and turn back before t_delay. This means
  # in high delay cases some corrections never even get commanded. So just use
  # psi to calculate a simple linearization of desired curvature
  curvature_diff_from_psi = psi / (max(v_ego, 1e-1) * delay) - current_curvature
  desired_curvature = current_curvature + 2 * curvature_diff_from_psi

  max_curvature_rate = interp(v_ego, MAX_CURVATURE_RATE_SPEEDS, MAX_CURVATURE_RATES)
  safe_desired_curvature_rate = clip(desired_curvature_rate,
                                          -max_curvature_rate,
                                          max_curvature_rate)
  safe_desired_curvature = clip(desired_curvature,
                                     current_curvature - max_curvature_rate/DT_MDL,
                                     current_curvature + max_curvature_rate/DT_MDL)
  return safe_desired_curvature, safe_desired_curvature_rate
