from selfdrive.car import apply_toyota_steer_torque_limits
from selfdrive.car.chrysler.chryslercan import create_lkas_hud, create_lkas_command, \
                                               create_wheel_buttons_command, create_lkas_heartbit,\
                                               acc_command, acc_log
from selfdrive.car.chrysler.values import CAR, CarControllerParams
from opendbc.can.packer import CANPacker
from selfdrive.config import Conversions as CV

from selfdrive.controls.lib.drive_helpers import V_CRUISE_MIN, V_CRUISE_MIN_IMPERIAL
from common.cached_params import CachedParams
from common.op_params import opParams
from common.params import Params
from cereal import car
import math
from random import randrange

ButtonType = car.CarState.ButtonEvent.Type
LongCtrlState = car.CarControl.Actuators.LongControlState

V_CRUISE_MIN_IMPERIAL_MS = V_CRUISE_MIN_IMPERIAL * CV.KPH_TO_MS
V_CRUISE_MIN_MS = V_CRUISE_MIN * CV.KPH_TO_MS
AUTO_FOLLOW_LOCK_MS = 3 * CV.MPH_TO_MS


class CarController():
  def __init__(self, dbc_name, CP, VM):
    self.apply_steer_last = 0
    self.prev_frame = -1
    self.lkas_frame = -1
    self.prev_lkas_counter = -1
    self.hud_count = 0
    self.car_fingerprint = CP.carFingerprint
    self.torq_enabled = False
    self.steer_rate_limited = False
    self.last_button_counter = -1
    self.button_frame = -1
    self.last_acc_2_counter = -1
    self.accel_steady = 0
    self.last_brake = None
    self.last_torque = 0.
    self.last_aTarget = 0.

    self.packer = CANPacker(dbc_name)

    self.params = Params()
    self.cachedParams = CachedParams()
    self.opParams = opParams()
    self.auto_resume = self.params.get_bool('jvePilot.settings.autoResume')
    self.minAccSetting = V_CRUISE_MIN_MS if self.params.get_bool("IsMetric") else V_CRUISE_MIN_IMPERIAL_MS
    self.round_to_unit = CV.MS_TO_KPH if self.params.get_bool("IsMetric") else CV.MS_TO_MPH
    self.autoFollowDistanceLock = None
    self.moving_fast = False
    self.min_steer_check = self.opParams.get("steer.checkMinimum")

  def update(self, enabled, CS, actuators, pcm_cancel_cmd, hud_alert, gas_resume_speed, c):
    if CS.button_pressed(ButtonType.lkasToggle, False):
      c.jvePilotState.carControl.useLaneLines = not c.jvePilotState.carControl.useLaneLines
      self.params.put("EndToEndToggle", "0" if c.jvePilotState.carControl.useLaneLines else "1")
      c.jvePilotState.notifyUi = True

    #*** control msgs ***
    can_sends = []
    self.lkas_control(CS, actuators, can_sends, enabled, hud_alert, c.jvePilotState)
    self.wheel_button_control(CS, can_sends, enabled, gas_resume_speed, c.jvePilotState, pcm_cancel_cmd)
    self.acc(CS, actuators, can_sends, enabled, c.jvePilotState)

    return can_sends

  # T = (mass x accel x velocity x 1000)/(.105 x Engine rpm)
  def acc(self, CS, actuators, can_sends, enabled, jvepilot_state):
    ACCEL_TORQ_MIN = 20
    ACCEL_TORQ_MAX = 360
    ACCEL_TORQ_START = 100
    VEHICLE_MASS = 2268
    LOW_WINDOW = CV.MPH_TO_MS * 3
    COAST_WINDOW = CV.MPH_TO_MS * 2
    BRAKE_CHANGE = 0.05

    acc_2_counter = CS.acc_2['COUNTER']
    if acc_2_counter == self.last_acc_2_counter:
      return
    self.last_acc_2_counter = acc_2_counter

    aTarget, self.accel_steady = self.accel_hysteresis(actuators.accel, self.accel_steady)
    override_request = CS.out.gasPressed or CS.out.brakePressed
    if not enabled or override_request:
      self.last_brake = None
      self.last_torque = ACCEL_TORQ_START
      self.last_aTarget = CS.out.aEgo
      can_sends.append(acc_command(self.packer, acc_2_counter + 1, False, False, 0, False, 0, CS.acc_2))
      return  # out of our control

    vTarget = jvepilot_state.carControl.vTargetFuture

    long_starting = actuators.longControlState == LongCtrlState.starting
    go_req = long_starting and CS.out.standstill
    long_stopping = actuators.longControlState == LongCtrlState.stopping
    stop_req = long_stopping or (CS.out.standstill and aTarget == 0 and not go_req)

    already_braking = self.last_brake is not None
    speed_to_far_off = CS.out.vEgo - vTarget > CV.MPH_TO_MS * 1  # gap
    not_slowing_fast_enough = not already_braking and speed_to_far_off and vTarget < CS.out.vEgo + CS.out.aEgo  # not going to get there

    torque = 0
    if aTarget > 0 and self.last_brake is None:
      vSmoothTarget = (vTarget + CS.out.vEgo) / 2
      accelerating = vTarget - COAST_WINDOW * CV.MS_TO_MPH > CS.out.vEgo and aTarget > 0 and CS.out.aEgo > 0 and CS.out.aEgo > self.last_aTarget
      if accelerating:
        aSmoothTarget = (aTarget + CS.out.aEgo) / 2
      else:
        aSmoothTarget = aTarget

      rpm = CS.gasRpm
      if CS.out.vEgo < LOW_WINDOW:
        cruise = (VEHICLE_MASS * aSmoothTarget * vSmoothTarget) / (.105 * rpm)
        if aTarget > 0.5:
          cruise = max(cruise, ACCEL_TORQ_START)  # give it some oomph
      elif CS.out.vEgo < 20 * CV.MPH_TO_MS:
        cruise = (VEHICLE_MASS * aTarget * vTarget) / (.105 * rpm)
      else:
        cruise = (VEHICLE_MASS * aSmoothTarget * vSmoothTarget) / (.105 * rpm)

      self.last_torque = max(ACCEL_TORQ_MIN, min(ACCEL_TORQ_MAX, cruise))
      torque = math.floor(self.last_torque * 100) / 100 if cruise > ACCEL_TORQ_MIN else 0.
    elif aTarget < 0 and (already_braking or not_slowing_fast_enough):
      brake_target = max(CarControllerParams.ACCEL_MIN, round(aTarget, 2))
      if self.last_brake is None:
        self.last_brake = min(0., brake_target / 2)
      else:
        tBrake = brake_target
        if not speed_to_far_off:  # let up on brake as we approach
          tBrake *= (CS.out.vEgo - vTarget) / COAST_WINDOW

        lBrake = self.last_brake
        if tBrake < lBrake:
          diff = min(BRAKE_CHANGE, (lBrake - tBrake) / 2)
          self.last_brake = max(lBrake - diff, tBrake)
        elif tBrake - lBrake > 0.01:  # don't let up unless it's a big enough jump
          diff = min(BRAKE_CHANGE, (tBrake - lBrake) / 2)
          self.last_brake = min(lBrake + diff, tBrake)

      self.last_brake = math.floor(self.last_brake * 100) / 100 if self.last_brake is not None else None
    elif self.last_brake is not None:  # let up on the brake
      self.last_brake += BRAKE_CHANGE
      if self.last_brake < 0:
        self.last_brake = math.floor(self.last_brake * 100) / 100
      else:
        self.last_brake = None

    self.last_aTarget = CS.out.aEgo
    brake = math.floor(self.last_brake * 100) / 100 if self.last_brake is not None else 4

    can_sends.append(acc_log(self.packer, actuators.accel, vTarget, long_starting, long_stopping))
    can_sends.append(acc_command(self.packer, acc_2_counter + 1, True, go_req, torque, stop_req, brake, CS.acc_2))

  def lkas_control(self, CS, actuators, can_sends, enabled, hud_alert, jvepilot_state):
    if self.prev_frame == CS.frame:
      return
    self.prev_frame = CS.frame

    self.lkas_frame += 1
    lkas_counter = CS.lkas_counter
    if self.prev_lkas_counter == lkas_counter:
      lkas_counter = (self.prev_lkas_counter + 1) % 16  # Predict the next frame
    self.prev_lkas_counter = lkas_counter

    # *** compute control surfaces ***
    # steer torque
    new_steer = int(round(actuators.steer * CarControllerParams.STEER_MAX))
    apply_steer = apply_toyota_steer_torque_limits(new_steer, self.apply_steer_last,
                                                   CS.out.steeringTorqueEps, CarControllerParams)
    self.steer_rate_limited = new_steer != apply_steer

    low_steer_models = self.car_fingerprint in (CAR.JEEP_CHEROKEE, CAR.PACIFICA_2017_HYBRID, CAR.PACIFICA_2018, CAR.PACIFICA_2018_HYBRID)
    if not self.min_steer_check:
      self.moving_fast = True
      self.torq_enabled = enabled or low_steer_models
    # elif low_steer_models:
    #   self.moving_fast = not CS.out.steerError and CS.lkas_active
    #   self.torq_enabled = self.torq_enabled or CS.torq_status > 1
    else:
      self.moving_fast = CS.out.vEgo > CS.CP.minSteerSpeed # for status message
      if CS.out.vEgo > (CS.CP.minSteerSpeed - 0.5):  # for command high bit
        self.torq_enabled = True
      elif CS.out.vEgo < (CS.CP.minSteerSpeed - 3.0):
        self.torq_enabled = (low_steer_models and self.torq_enabled)  # < 14.5m/s stock turns off this bit, but fine down to 13.5

    lkas_active = self.moving_fast and enabled
    if not lkas_active:
      apply_steer = 0

    self.apply_steer_last = apply_steer

    if self.lkas_frame % 10 == 0:  # 0.1s period
      new_msg = create_lkas_heartbit(self.packer, 0 if jvepilot_state.carControl.useLaneLines else 1, CS.lkasHeartbit)
      can_sends.append(new_msg)

    if self.lkas_frame % 25 == 0:  # 0.25s period
      if CS.lkas_car_model != -1:
        new_msg = create_lkas_hud(
          self.packer, CS.out.gearShifter, lkas_active, hud_alert,
          self.hud_count, CS.lkas_car_model)
        can_sends.append(new_msg)
        self.hud_count += 1

    new_msg = create_lkas_command(self.packer, int(apply_steer), self.torq_enabled, lkas_counter)
    can_sends.append(new_msg)

  def wheel_button_control(self, CS, can_sends, enabled, gas_resume_speed, jvepilot_state, pcm_cancel_cmd):
    button_counter = jvepilot_state.carState.buttonCounter
    if button_counter == self.last_button_counter:
      return
    self.last_button_counter = button_counter

    self.button_frame += 1

    if pcm_cancel_cmd or CS.button_pressed(ButtonType.cancel):
      CS.accEnabled = False
    elif CS.button_pressed(ButtonType.accelCruise) or CS.button_pressed(ButtonType.decelCruise) or CS.button_pressed(ButtonType.resumeCruise):
      CS.accEnabled = True

    if CS.reallyEnabled:
      new_msg = create_wheel_buttons_command(self.packer, button_counter + 1, ['ACC_CANCEL'])
      can_sends.append(new_msg)

  def accel_hysteresis(self, accel, accel_steady):
    ACCEL_HYST_GAP = 0.06

    if accel > accel_steady + ACCEL_HYST_GAP:
      accel_steady = accel - ACCEL_HYST_GAP
    elif accel < accel_steady - ACCEL_HYST_GAP:
      accel_steady = accel + ACCEL_HYST_GAP
    accel = accel_steady

    return accel, accel_steady