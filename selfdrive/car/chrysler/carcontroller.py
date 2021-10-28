from selfdrive.car import apply_toyota_steer_torque_limits
from selfdrive.car.chrysler.chryslercan import create_lkas_hud, create_lkas_command, \
  create_wheel_buttons_command, create_lkas_heartbit, \
  acc_command
from selfdrive.car.chrysler.values import CAR, CarControllerParams
from opendbc.can.packer import CANPacker
from selfdrive.config import Conversions as CV

from selfdrive.controls.lib.drive_helpers import V_CRUISE_MIN, V_CRUISE_MIN_IMPERIAL
from common.cached_params import CachedParams
from common.op_params import opParams
from common.params import Params
from cereal import car
from numpy import interp
import cereal.messaging as messaging
ButtonType = car.CarState.ButtonEvent.Type

V_CRUISE_MIN_IMPERIAL_MS = V_CRUISE_MIN_IMPERIAL * CV.KPH_TO_MS
V_CRUISE_MIN_MS = V_CRUISE_MIN * CV.KPH_TO_MS
AUTO_FOLLOW_LOCK_MS = 3 * CV.MPH_TO_MS

ACC_BRAKE_THRESHOLD = 2 * CV.MPH_TO_MS

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
    self.last_acc_2_counter = 0
    self.last_brake = None
    self.last_gas = 0.
    self.accel_steady = 0.
    self.last_aEgo = None

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

    if self.last_aEgo is None:
      self.last_aEgo = CS.out.aEgo

    #*** control msgs ***
    can_sends = []
    self.lkas_control(CS, actuators, can_sends, enabled, hud_alert, c.jvePilotState)
    self.wheel_button_control(CS, can_sends, enabled, gas_resume_speed, c.jvePilotState, pcm_cancel_cmd)
    self.acc(CS, actuators, can_sends, enabled, c.jvePilotState)

    return can_sends

  def acc(self, CS, actuators, can_sends, enabled, jvepilot_state):
    ACCEL_TORQ_MAX = self.cachedParams.get_float('jvePilot.settings.longControl.maxAccelTorq', 500)
    ACCEL_TORQ_CHANGE_RATIO = self.cachedParams.get_float('jvePilot.settings.longControl.torqChangeRatio', 500)
    ACCEL_TORQ_START = self.cachedParams.get_float('jvePilot.settings.longControl.torqStart', 500)


    acc_2_counter = CS.acc_2['COUNTER']
    if acc_2_counter == self.last_acc_2_counter:
      return
    self.last_acc_2_counter = acc_2_counter

    aEgoChange = CS.aEgoRaw - self.last_aEgo
    self.last_aEgo = CS.aEgoRaw

    if not enabled:
      self.last_brake = None
      self.last_gas = ACCEL_TORQ_START
      return

    if jvepilot_state.carControl.useLaneLines:
      return

    # ECO
    if jvepilot_state.carControl.accEco == 1:
      ACCEL_TORQ_CHANGE_RATIO *= .75
    elif jvepilot_state.carControl.accEco == 2:
      ACCEL_TORQ_CHANGE_RATIO *= .5

    vTarget = jvepilot_state.carControl.vTargetFuture
    aTarget = actuators.accel

    COAST_WINDOW = CV.MPH_TO_MS * 3
    was_accelerating = self.last_gas is not None
    not_slowing_fast_enough = aTarget < CS.aEgoRaw + aEgoChange * 50 * 2  # not going to get there within 2 seconds
    speed_to_far_off = CS.out.vEgo - vTarget >= COAST_WINDOW  # speed gap is large, start braking

    brake_press = False
    brake_target = 0
    gas = 0

    spoof_brake = aTarget < 0 and (not was_accelerating or vTarget <= COAST_WINDOW or (speed_to_far_off and not_slowing_fast_enough))
    if CS.acc_2['ACC_DECEL_REQ'] == 1 and (CS.acc_2['ACC_DECEL'] < aTarget or not spoof_brake):
      brake_press = True
      brake_target = CS.acc_2['ACC_DECEL']
    elif spoof_brake:
      # todo: stay stopped
      brake_press = True
      brake_target = max(-2, round(aTarget, 2))
      if CS.acc_2['ACC_DECEL_REQ'] == 1:
        acc = round(CS.acc_2['ACC_DECEL'], 2)
        brake_target = min(brake_target, acc)
        if self.last_brake is None:
          self.last_brake = acc  # start here since ACC was already active
    else:
      if self.last_gas is None:
        self.last_gas = ACCEL_TORQ_START # TODO start someplace reasonable
      if aTarget > 0 and CS.out.vEgo < CV.MPH_TO_MS * 5:
        self.last_gas = max(self.last_gas, ACCEL_TORQ_START)

      vFutureEgo = CS.out.vEgo + CS.aEgoRaw + aEgoChange * 50

      aTarget, self.accel_steady = self.accel_hysteresis(max(0., min(aTarget, vTarget - vFutureEgo)), self.accel_steady)
      tChange = (aTarget - CS.aEgoRaw) * ACCEL_TORQ_CHANGE_RATIO
      if tChange > 0:
        tChange *= ACCEL_TORQ_CHANGE_RATIO
      if (aTarget > CS.out.aEgo and aEgoChange < 0) or (aTarget < CS.out.aEgo and aEgoChange > 0):
        tChange += (aEgoChange * 50)

      self.last_gas = max(0, min(ACCEL_TORQ_MAX, self.last_gas + tChange))

      gas = round(self.last_gas, 0)
      print(f"torq={self.last_gas}, tChange={tChange}, aEgoRaw={CS.aEgoRaw}m/s2, aTarget={aTarget}m/s2, aEgoChange={aEgoChange * 50}, vEgo={CS.out.vEgo}, vTarget={vTarget}, vFutureEgo={vFutureEgo}")

    if brake_press:
      self.last_gas = None
      if self.last_brake is None:
        self.last_brake = brake_target
      elif brake_target < self.last_brake:
        self.last_brake = round(max(self.last_brake - 0.02, brake_target), 2)
      elif brake_target > self.last_brake:
        self.last_brake = round(min(self.last_brake + 0.02, brake_target), 2)
    else:
      self.last_brake = None

    brake = self.last_brake if self.last_brake is not None else 4

    if CS.out.gasPressed or CS.out.brakePressed:  # stop sending ACC requests
      gas = 0
      brake = 4

    can_sends.append(acc_command(self.packer, acc_2_counter + 1, gas, brake, CS.acc_2))

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
    elif low_steer_models:
      self.moving_fast = not CS.out.steerError and CS.lkas_active
      self.torq_enabled = self.torq_enabled or CS.torq_status > 1
    else:
      self.moving_fast = CS.out.vEgo > CS.CP.minSteerSpeed  # for status message
      if CS.out.vEgo > (CS.CP.minSteerSpeed - 0.5):  # for command high bit
        self.torq_enabled = True
      elif CS.out.vEgo < (CS.CP.minSteerSpeed - 3.0):
        self.torq_enabled = False  # < 14.5m/s stock turns off this bit, but fine down to 13.5

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
    button_counter_offset = 1
    buttons_to_press = []
    if pcm_cancel_cmd:
      buttons_to_press = ['ACC_CANCEL']
    elif not CS.button_pressed(ButtonType.cancel):
      follow_inc_button = CS.button_pressed(ButtonType.followInc)
      follow_dec_button = CS.button_pressed(ButtonType.followDec)

      if jvepilot_state.carControl.autoFollow:
        follow_inc_button = CS.button_pressed(ButtonType.followInc, False)
        follow_dec_button = CS.button_pressed(ButtonType.followDec, False)
        if (follow_inc_button and follow_inc_button.pressedFrames < 50) or \
           (follow_dec_button and follow_dec_button.pressedFrames < 50):
          jvepilot_state.carControl.autoFollow = False
          jvepilot_state.notifyUi = True
      elif (follow_inc_button and follow_inc_button.pressedFrames >= 50) or \
           (follow_dec_button and follow_dec_button.pressedFrames >= 50):
        jvepilot_state.carControl.autoFollow = True
        jvepilot_state.notifyUi = True

      if enabled and not CS.out.brakePressed:
        button_counter_offset = [1, 1, 0, None][self.button_frame % 4]
        if button_counter_offset is not None:
          if (not CS.out.cruiseState.enabled) or CS.out.standstill:  # Stopped and waiting to resume
            buttons_to_press = [self.auto_resume_button(CS, gas_resume_speed)]
          elif CS.out.cruiseState.enabled:  # Control ACC
            buttons_to_press = [self.auto_follow_button(CS, jvepilot_state), self.hybrid_acc_button(CS, jvepilot_state)]

    buttons_to_press = list(filter(None, buttons_to_press))
    if buttons_to_press is not None and len(buttons_to_press) > 0:
      new_msg = create_wheel_buttons_command(self.packer, button_counter + button_counter_offset, buttons_to_press)
      can_sends.append(new_msg)

  def auto_resume_button(self, CS, gas_resume_speed):
    if self.auto_resume and CS.out.vEgo <= gas_resume_speed:  # Keep trying while under gas_resume_speed
      return 'ACC_RESUME'

  def hybrid_acc_button(self, CS, jvepilot_state):
    target = jvepilot_state.carControl.vMaxCruise

    # # Move the adaptive curse control to the target speed
    # eco_limit = None
    # if jvepilot_state.carControl.accEco == 1:  # if eco mode
    #   eco_limit = self.cachedParams.get_float('jvePilot.settings.accEco.speedAheadLevel1', 1000)
    # elif jvepilot_state.carControl.accEco == 2:  # if eco mode
    #   eco_limit = self.cachedParams.get_float('jvePilot.settings.accEco.speedAheadLevel2', 1000)
    #
    # if eco_limit:
    #   target = min(target, CS.out.vEgo + (eco_limit * CV.MPH_TO_MS))

    # ACC Braking
    diff = CS.out.vEgo - target
    if diff > ACC_BRAKE_THRESHOLD and abs(target - jvepilot_state.carControl.vMaxCruise) > ACC_BRAKE_THRESHOLD:  # ignore change in max cruise speed
      target -= diff

    # round to nearest unit
    target = round(target * self.round_to_unit)
    current = round(CS.out.cruiseState.speed * self.round_to_unit)

    if target < current and current > self.minAccSetting:
      return 'ACC_SPEED_DEC'
    elif target > current:
      return 'ACC_SPEED_INC'

  def auto_follow_button(self, CS, jvepilot_state):
    if jvepilot_state.carControl.autoFollow:
      crossover = [0,
                   self.cachedParams.get_float('jvePilot.settings.autoFollow.speed1-2Bars', 1000) * CV.MPH_TO_MS,
                   self.cachedParams.get_float('jvePilot.settings.autoFollow.speed2-3Bars', 1000) * CV.MPH_TO_MS,
                   self.cachedParams.get_float('jvePilot.settings.autoFollow.speed3-4Bars', 1000) * CV.MPH_TO_MS]

      if CS.out.vEgo < crossover[1]:
        target_follow = 0
      elif CS.out.vEgo < crossover[2]:
        target_follow = 1
      elif CS.out.vEgo < crossover[3]:
        target_follow = 2
      else:
        target_follow = 3

      if self.autoFollowDistanceLock is not None and abs(crossover[self.autoFollowDistanceLock] - CS.out.vEgo) > AUTO_FOLLOW_LOCK_MS:
        self.autoFollowDistanceLock = None  # unlock

      if jvepilot_state.carState.accFollowDistance != target_follow and (self.autoFollowDistanceLock or target_follow) == target_follow:
        self.autoFollowDistanceLock = target_follow  # going from close to far, use upperbound

        if jvepilot_state.carState.accFollowDistance > target_follow:
          return 'ACC_FOLLOW_DEC'
        else:
          return 'ACC_FOLLOW_INC'

  def accel_hysteresis(self, accel, accel_steady):
    ACCEL_HYST_GAP = self.cachedParams.get_float('jvePilot.settings.longControl.hystGap', 500)
    # for small accel oscillations within ACCEL_HYST_GAP, don't change the accel command
    if accel > accel_steady + ACCEL_HYST_GAP:
      accel_steady = accel - ACCEL_HYST_GAP
    elif accel < accel_steady - ACCEL_HYST_GAP:
      accel_steady = accel + ACCEL_HYST_GAP
    accel = accel_steady

    return accel, accel_steady