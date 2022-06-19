import math

from cereal import car
from common.conversions import Conversions as CV
from common.numpy_fast import clip, interp
from common.realtime import DT_MDL
from selfdrive.modeld.constants import T_IDXS

# WARNING: this value was determined based on the model's training distribution,
#          model predictions above this speed can be unpredictable
V_CRUISE_MAX = 145  # kph
V_CRUISE_MIN = 30  # Chrysler min ACC when metric
V_CRUISE_DELTA = 5  # ACC increments (unit agnostic)
V_CRUISE_MIN_IMPERIAL = int(20 * CV.MPH_TO_KPH)
V_CRUISE_DELTA_IMPERIAL = int(V_CRUISE_DELTA * CV.MPH_TO_KPH)

LAT_MPC_N = 16
LON_MPC_N = 32
CONTROL_N = 17
CAR_ROTATION_RADIUS = 0.0

# EU guidelines
MAX_LATERAL_JERK = 5.0

ButtonType = car.CarState.ButtonEvent.Type
CRUISE_LONG_PRESS = 50
CRUISE_NEAREST_FUNC = {
  ButtonType.accelCruise: math.ceil,
  ButtonType.decelCruise: math.floor,
}
CRUISE_INTERVAL_SIGN = {
  ButtonType.accelCruise: +1,
  ButtonType.decelCruise: -1,
}


class MPC_COST_LAT:
  PATH = 1.0
  HEADING = 1.0
  STEER_RATE = 1.0


def rate_limit(new_value, last_value, dw_step, up_step):
  return clip(new_value, last_value + dw_step, last_value + up_step)

def update_v_cruise(v_cruise_kph, v_ego, gas_pressed, buttonEvents, button_timers, enabled, is_metric, reverse_acc_button_change):
  # handle button presses. TODO: this should be in state_control, but a decelCruise press
  # would have the effect of both enabling and changing speed is checked after the state transition
  v_cruise_min = cruise_min(is_metric)
  if enabled:
    for b in buttonEvents:
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


def get_lag_adjusted_curvature(CP, v_ego, psis, curvatures, curvature_rates):
  if len(psis) != CONTROL_N:
    psis = [0.0]*CONTROL_N
    curvatures = [0.0]*CONTROL_N
    curvature_rates = [0.0]*CONTROL_N

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

  v_ego = max(v_ego, 0.1)
  max_curvature_rate = MAX_LATERAL_JERK / (v_ego**2)
  safe_desired_curvature_rate = clip(desired_curvature_rate,
                                          -max_curvature_rate,
                                          max_curvature_rate)
  safe_desired_curvature = clip(desired_curvature,
                                     current_curvature - max_curvature_rate * DT_MDL,
                                     current_curvature + max_curvature_rate * DT_MDL)

  return safe_desired_curvature, safe_desired_curvature_rate
