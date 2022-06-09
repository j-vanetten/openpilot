from selfdrive.car import apply_toyota_steer_torque_limits
from selfdrive.car.chrysler.chryslercan import create_lkas_hud, create_lkas_command, \
  create_wheel_buttons_command, create_lkas_heartbit, \
  acc_command, acc_hybrid_command, acc_log
from selfdrive.car.chrysler.values import CAR, CarControllerParams
from selfdrive.car.chrysler.interface import CarInterface
from opendbc.can.packer import CANPacker
from common.conversions import Conversions as CV

from selfdrive.controls.lib.drive_helpers import V_CRUISE_MIN, V_CRUISE_MIN_IMPERIAL
from common.cached_params import CachedParams
from common.params import Params, put_nonblocking
from cereal import car
import math

ButtonType = car.CarState.ButtonEvent.Type
LongCtrlState = car.CarControl.Actuators.LongControlState

V_CRUISE_MIN_IMPERIAL_MS = V_CRUISE_MIN_IMPERIAL * CV.KPH_TO_MS
V_CRUISE_MIN_MS = V_CRUISE_MIN * CV.KPH_TO_MS
AUTO_FOLLOW_LOCK_MS = 3 * CV.MPH_TO_MS
ACC_BRAKE_THRESHOLD = 2 * CV.MPH_TO_MS

# LONG PARAMS
LOW_WINDOW = CV.MPH_TO_MS * 5
SLOW_WINDOW = CV.MPH_TO_MS * 20
COAST_WINDOW = CV.MPH_TO_MS * 2

# accelerator
ACCEL_TORQ_SLOW = 40  # add this when going SLOW
# ACCEL_TORQ_MAX = 360
UNDER_ACCEL_MULTIPLIER = 1.
TORQ_RELEASE_CHANGE = 0.35
TORQ_ADJUST_THRESHOLD = 0.3
START_ADJUST_ACCEL_FRAMES = 100
ADJUST_ACCEL_COOLDOWN_MAX = 1
MIN_TORQ_CHANGE = 2
ACCEL_TO_NM = 1200
TORQ_BRAKE_MAX = -0.1

# braking
BRAKE_CHANGE = 0.06

class CarController():
  def __init__(self, dbc_name, CP, VM):
    self.CP = CP
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
    self.last_enabled = False
    self.torq_adjust = 0.
    self.under_accel_frame_count = 0
    self.ccframe = 0
    self.hybrid = self.car_fingerprint in (CAR.PACIFICA_2017_HYBRID, CAR.PACIFICA_2018_HYBRID, CAR.PACIFICA_2019_HYBRID)
    self.vehicleMass = CP.mass

    self.packer = CANPacker(dbc_name)

    self.params = Params()
    self.cachedParams = CachedParams()
    self.auto_resume = self.params.get_bool('jvePilot.settings.autoResume')
    self.minAccSetting = V_CRUISE_MIN_MS if self.params.get_bool("IsMetric") else V_CRUISE_MIN_IMPERIAL_MS
    self.round_to_unit = CV.MS_TO_KPH if self.params.get_bool("IsMetric") else CV.MS_TO_MPH
    self.autoFollowDistanceLock = None
    self.moving_fast = False

  def update(self, CC, CS, gas_resume_speed):
    self.ccframe += 1
    if CS.button_pressed(ButtonType.lkasToggle, False):
      CC.jvePilotState.carControl.useLaneLines = not CC.jvePilotState.carControl.useLaneLines
      self.params.put("EndToEndToggle", "0" if CC.jvePilotState.carControl.useLaneLines else "1")
      CC.jvePilotState.notifyUi = True

    # *** control msgs ***
    can_sends = []
    if CS.longControl:
      self.acc(CS, CC.actuators, can_sends, CC.enabled, CC.jvePilotState)
    actuators = self.lkas_control(CC, CS, can_sends)
    self.wheel_button_control(CS, can_sends, CC.enabled, gas_resume_speed, CC.jvePilotState, CC.cruiseControl.cancel)

    return actuators, can_sends

  # T = (mass x accel x velocity x 1000)/(.105 x Engine rpm)
  def acc(self, CS, actuators, can_sends, enabled, jvepilot_state):
    acc_2_counter = CS.acc_2['COUNTER']
    if self.last_enabled != enabled:
      self.last_enabled = enabled
      can_sends.append(acc_command(self.packer, acc_2_counter, enabled, None, None, None, None, CS.acc_2))

    counter_change = acc_2_counter != self.last_acc_2_counter
    self.last_acc_2_counter = acc_2_counter
    if not counter_change:
      return

    if not enabled:
      self.torq_adjust = 0
      self.last_brake = None
      self.last_torque = None
      return

    under_accel_frame_count = 0
    aTarget = actuators.accel
    vTarget = jvepilot_state.carControl.vTargetFuture
    long_stopping = actuators.longControlState == LongCtrlState.stopping

    override_request = CS.out.gasPressed or CS.out.brakePressed
    if not override_request:
      stop_req = long_stopping or (CS.out.standstill and aTarget == 0)
      go_req = not stop_req and CS.out.standstill

      if go_req:
        under_accel_frame_count = self.under_accel_frame_count = START_ADJUST_ACCEL_FRAMES  # ready to add torq
        self.last_brake = None

      currently_braking = self.last_brake is not None
      speed_to_far_off = abs(CS.out.vEgo - vTarget) > COAST_WINDOW
      engine_brake = TORQ_BRAKE_MAX < aTarget < 0 and not speed_to_far_off and vTarget > LOW_WINDOW \
                     and self.torque(CS, aTarget, vTarget) + self.torq_adjust > CS.torqMin

      if go_req or ((aTarget >= 0 or engine_brake) and not currently_braking):  # gas
        under_accel_frame_count = self.acc_gas(CS, aTarget, vTarget, under_accel_frame_count)

      elif aTarget < 0:  # brake
        self.acc_brake(CS, aTarget, vTarget, speed_to_far_off)

      elif self.last_brake is not None:  # let up on the brake
        self.last_brake += BRAKE_CHANGE
        if self.last_brake >= 0:
          self.last_brake = None

      elif self.last_torque is not None:  # let up on gas
        self.last_torque -= TORQ_RELEASE_CHANGE
        if self.last_torque <= max(0, CS.torqMin):
          self.last_torque = None

      if stop_req:
        brake = self.last_brake = -2.01 if acc_2_counter == 0 else -2.0  # keep from rolling forward when stopped
        torque = self.last_torque = None
      elif go_req:
        brake = self.last_brake = None
        torque = math.floor(self.last_torque * 100) / 100
      elif self.last_brake:
        brake = math.floor(self.last_brake * 100) / 100
        torque = self.last_torque = None
      elif self.last_torque:
        brake = self.last_brake = None
        torque = math.floor(self.last_torque * 100) / 100
      else:  # coasting
        brake = self.last_brake = None
        torque = self.last_torque = None
    else:
      self.last_torque = None
      self.last_brake = None
      stop_req = None
      brake = None
      go_req = None
      torque = None

    if under_accel_frame_count == 0 and aTarget < 0 and self.torq_adjust > 0:  # we are cooling down
      self.torq_adjust = max(0, self.torq_adjust - max(aTarget * 10, ADJUST_ACCEL_COOLDOWN_MAX))

    self.under_accel_frame_count = under_accel_frame_count
    self.last_aTarget = CS.out.aEgo

    can_sends.append(acc_log(self.packer, int(self.torq_adjust), aTarget, vTarget))

    can_sends.append(acc_command(self.packer, acc_2_counter + 1, True,
                                 go_req,
                                 torque,
                                 stop_req and acc_2_counter % 2 == 0,
                                 brake,
                                 CS.acc_2))
    if self.hybrid:
      can_sends.append(acc_hybrid_command(self.packer, acc_2_counter + 1, True,
                                          torque,
                                          CS.acc_1))

  def torque(self, CS, aTarget, vTarget):
    rpm = (self.vehicleMass * CS.out.aEgo * CS.out.vEgo) / (.105 * CS.hybridTorq) if CS.hybrid else CS.gasRpm

    return (self.vehicleMass * aTarget * vTarget) / (.105 * rpm)

  def acc_gas(self, CS, aTarget, vTarget, under_accel_frame_count):
    if self.hybrid:
      aSmoothTarget = (aTarget + CS.out.aEgo) / 2  # always smooth since hybrid has lots of torq?
      cruise = aSmoothTarget * ACCEL_TO_NM
    else:
      if CS.out.vEgo < SLOW_WINDOW:
        cruise = (self.vehicleMass * aTarget * vTarget) / (.105 * CS.gasRpm)
        cruise += ACCEL_TORQ_SLOW * (1 - (CS.out.vEgo / SLOW_WINDOW))
      else:
        accelerating = aTarget > 0 and vTarget > CS.out.vEgo + SLOW_WINDOW  # and CS.out.aEgo > 0 and CS.out.aEgo > self.last_aTarget
        if accelerating:
          vSmoothTarget = (vTarget + CS.out.vEgo) / 2
          aSmoothTarget = (aTarget + CS.out.aEgo) / 2
        else:
          vSmoothTarget = vTarget
          aSmoothTarget = aTarget

        cruise = (self.vehicleMass * aSmoothTarget * vSmoothTarget) / (.105 * CS.gasRpm)

    if aTarget > 0:
      # adjust for hills and towing
      offset = aTarget - CS.out.aEgo
      if offset > TORQ_ADJUST_THRESHOLD:
        under_accel_frame_count = self.under_accel_frame_count + 1  # inc under accelerating frame count
        if self.ccframe - self.under_accel_frame_count > START_ADJUST_ACCEL_FRAMES:
          self.torq_adjust += offset * (CarControllerParams.ACCEL_MAX / CarInterface.accel_max(CS))

    if cruise + self.torq_adjust > CS.torqMax:  # keep the adjustment in check
      self.torq_adjust = max(0, CS.torqMax - cruise)

    torque = cruise + self.torq_adjust
    self.last_torque = max(CS.torqMin + 1, min(CS.torqMax, torque))

    return under_accel_frame_count

  def acc_brake(self, CS, aTarget, vTarget, speed_to_far_off):
    brake_target = max(CarControllerParams.ACCEL_MIN, round(aTarget, 2))
    if self.last_brake is None:
      self.last_brake = min(0., brake_target / 2)
    else:
      tBrake = brake_target
      if not speed_to_far_off and 0 >= tBrake >= -1:  # let up on brake as we approach
        tBrake = (tBrake * 1.1) + .1

      lBrake = self.last_brake
      if tBrake < lBrake:
        diff = min(BRAKE_CHANGE, (lBrake - tBrake) / 2)
        self.last_brake = max(lBrake - diff, tBrake)
      elif tBrake - lBrake > 0.01:  # don't let up unless it's a big enough jump
        diff = min(BRAKE_CHANGE, (tBrake - lBrake) / 2)
        self.last_brake = min(lBrake + diff, tBrake)

  def lkas_control(self, CC, CS, can_sends):
    if self.prev_frame == CS.frame:
      return car.CarControl.Actuators.new_message()
    self.prev_frame = CS.frame

    actuators = CC.actuators

    self.lkas_frame += 1
    lkas_counter = CS.lkas_counter
    if self.prev_lkas_counter == lkas_counter:
      lkas_counter = (self.prev_lkas_counter + 1) % 16  # Predict the next frame
    self.prev_lkas_counter = lkas_counter

    # steer torque
    new_steer = int(round(actuators.steer * CarControllerParams.STEER_MAX))
    apply_steer = apply_toyota_steer_torque_limits(new_steer, self.apply_steer_last,
                                                   CS.out.steeringTorqueEps, CarControllerParams)
    self.steer_rate_limited = new_steer != apply_steer

    low_steer_models = self.car_fingerprint in (CAR.JEEP_CHEROKEE, CAR.PACIFICA_2017_HYBRID, CAR.PACIFICA_2018, CAR.PACIFICA_2018_HYBRID)
    if CS.no_steer_check:
      self.moving_fast = True
      self.torq_enabled = CC.enabled or low_steer_models
    else:
      self.moving_fast = CS.out.vEgo > CS.CP.minSteerSpeed  # for status message
      if CS.out.vEgo > (CS.CP.minSteerSpeed - 0.5):  # for command high bit
        self.torq_enabled = True
      elif not low_steer_models and CS.out.vEgo < (CS.CP.minSteerSpeed - 3.0):
        self.torq_enabled = False  # < 14.5m/s stock turns off this bit, but fine down to 13.5

    lkas_active = self.moving_fast and CC.enabled
    if not lkas_active:
      apply_steer = 0

    self.apply_steer_last = apply_steer

    if self.lkas_frame % 10 == 0:  # 0.1s period
      new_msg = create_lkas_heartbit(self.packer, 0 if CC.jvePilotState.carControl.useLaneLines else 1, CS.lkasHeartbit)
      can_sends.append(new_msg)

    if self.lkas_frame % 25 == 0:  # 0.25s period
      if CS.lkas_car_model != -1:
        new_msg = create_lkas_hud(
          self.packer, CS.out.gearShifter, lkas_active, CC.hudControl.visualAlert,
          self.hud_count, CS.lkas_car_model)
        can_sends.append(new_msg)
        self.hud_count += 1

    new_msg = create_lkas_command(self.packer, int(apply_steer), self.torq_enabled, lkas_counter)
    can_sends.append(new_msg)

    new_actuators = actuators.copy()
    new_actuators.steer = apply_steer / CarControllerParams.STEER_MAX

    return new_actuators

  def wheel_button_control(self, CS, can_sends, enabled, gas_resume_speed, jvepilot_state, pcm_cancel_cmd):
    button_counter = jvepilot_state.carState.buttonCounter
    if button_counter == self.last_button_counter:
      return
    self.last_button_counter = button_counter

    self.button_frame += 1

    if CS.longControl:
      if pcm_cancel_cmd or CS.button_pressed(ButtonType.cancel) or CS.out.brakePressed:
        CS.longEnabled = False
      elif CS.button_pressed(ButtonType.accelCruise) or \
          CS.button_pressed(ButtonType.decelCruise) or \
          CS.button_pressed(ButtonType.resumeCruise):
        CS.longEnabled = True

      accDiff = None
      if CS.button_pressed(ButtonType.followInc, False):
        if jvepilot_state.carControl.accEco < 2:
          accDiff = 1
      elif CS.button_pressed(ButtonType.followDec, False):
        if jvepilot_state.carControl.accEco > 0:
          accDiff = -1
      if accDiff is not None:
        jvepilot_state.carControl.accEco += accDiff
        put_nonblocking("jvePilot.carState.accEco", str(jvepilot_state.carControl.accEco))
        jvepilot_state.notifyUi = True

    else:
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
              buttons_to_press = [self.auto_follow_button(CS, jvepilot_state),
                                  self.hybrid_acc_button(CS, jvepilot_state)]

      buttons_to_press = list(filter(None, buttons_to_press))
      if button_counter_offset is not None and len(buttons_to_press) > 0:
        new_msg = create_wheel_buttons_command(self.packer, button_counter + button_counter_offset, buttons_to_press)
        can_sends.append(new_msg)

  def auto_resume_button(self, CS, gas_resume_speed):
    if self.auto_resume and CS.out.vEgo <= gas_resume_speed:  # Keep trying while under gas_resume_speed
      return 'ACC_RESUME'

  def hybrid_acc_button(self, CS, jvepilot_state):
    target = jvepilot_state.carControl.vTargetFuture + 2 * CV.MPH_TO_MS  # add extra speed so ACC does the limiting

    # Move the adaptive curse control to the target speed
    eco_limit = None
    if jvepilot_state.carControl.accEco == 1:  # if eco mode
      eco_limit = self.cachedParams.get_float('jvePilot.settings.accEco.speedAheadLevel1', 1000)
    elif jvepilot_state.carControl.accEco == 2:  # if eco mode
      eco_limit = self.cachedParams.get_float('jvePilot.settings.accEco.speedAheadLevel2', 1000)

    if eco_limit:
      target = min(target, CS.out.vEgo + (eco_limit * CV.MPH_TO_MS))

    # ACC Braking
    diff = CS.out.vEgo - target
    if diff > ACC_BRAKE_THRESHOLD and abs(target - jvepilot_state.carControl.vMaxCruise) > ACC_BRAKE_THRESHOLD:
      target -= diff

    # round to nearest unit
    target = round(min(jvepilot_state.carControl.vMaxCruise, target) * self.round_to_unit)
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

      if self.autoFollowDistanceLock is not None and abs(
          crossover[self.autoFollowDistanceLock] - CS.out.vEgo) > AUTO_FOLLOW_LOCK_MS:
        self.autoFollowDistanceLock = None  # unlock

      if jvepilot_state.carState.accFollowDistance != target_follow and (
          self.autoFollowDistanceLock or target_follow) == target_follow:
        self.autoFollowDistanceLock = target_follow  # going from close to far, use upperbound

        if jvepilot_state.carState.accFollowDistance > target_follow:
          return 'ACC_FOLLOW_DEC'
        else:
          return 'ACC_FOLLOW_INC'