import math
from common.numpy_fast import clip, mean
from opendbc.can import CANPacker
from opendbc.car import Bus
from opendbc.car.lateral import apply_meas_steer_torque_limits
from opendbc.car.car_helpers import button_pressed
from opendbc.car.chrysler import chryslercan
from opendbc.car.chrysler.values import RAM_CARS, JEEPS, CarControllerParams, ChryslerFlags, DRIVE_PERSONALITY
from opendbc.car.interfaces import CarControllerBase

from openpilot.selfdrive.car.cruise import V_CRUISE_MIN, V_CRUISE_MIN_IMPERIAL
from opendbc.car.chrysler.long_carcontroller_v1 import LongCarControllerV1
from opendbc.car.common.conversions import Conversions as CV
from openpilot.common.cached_params import CachedParams
from openpilot.common.params import Params
from cereal import car, messaging

GearShifter = car.CarState.GearShifter
ButtonType = car.CarState.ButtonEvent.Type

V_CRUISE_MIN_IMPERIAL_MS = V_CRUISE_MIN_IMPERIAL * CV.KPH_TO_MS
V_CRUISE_MIN_MS = V_CRUISE_MIN * CV.KPH_TO_MS
AUTO_FOLLOW_LOCK_MS = 3 * CV.MPH_TO_MS
EXTEND_FUTURE_MAX = 10 * CV.MPH_TO_MS

cachedParams = CachedParams()

class CarController(CarControllerBase):
  ACCEL_MAX = 2.  # m/s2, high to not limit stock ACC
  ACCEL_MIN = -3.5  # m/s2

  def __init__(self, dbc_names, CP):
    super().__init__(dbc_names, CP)
    self.apply_torque_last = 0

    self.hud_count = 0
    self.next_lkas_control_change = 0
    self.lkas_control_bit_prev = False
    self.last_button_frame = 0

    self.packer = CANPacker(dbc_names[Bus.pt])
    self.params = CarControllerParams(CP)

    self.sm = messaging.SubMaster(['longitudinalPlan', 'selfdriveState'])
    self.settingsParams = Params()
    self.cachedParams = CachedParams()
    self.minAccSetting = V_CRUISE_MIN_MS if self.settingsParams.get_bool("IsMetric") else V_CRUISE_MIN_IMPERIAL_MS
    self.round_to_unit = CV.MS_TO_KPH if self.settingsParams.get_bool("IsMetric") else CV.MS_TO_MPH
    self.steerNoMinimum = CP.minSteerSpeed < 0
    self.auto_enable_acc = self.settingsParams.get_bool("jvePilot.settings.autoEnableAcc")
    self.last_das_3_counter = -1

    self.autoFollowDistanceLock = None
    self.button_frame = 0
    self.last_target = 0
    self.last_personality = None
    self.low_steer = not self.CP.flags & ChryslerFlags.HIGHER_MIN_STEERING_SPEED
    self.steer_gap = 0.5 if self.CP.carFingerprint in RAM_CARS else 3.0

    self.brake_hold_enabled = self.settingsParams.get_bool("jvePilot.settings.brakeHold") and self.CP.carFingerprint in JEEPS
    self.brake_hold_decel = 0

    self.long_controller = LongCarControllerV1(CarController, self.CP, self.params, self.packer)

  def update(self, CC, CS, now_nanos):
    can_sends = []
    self.sm.update(0)

    # cruise buttons
    das_bus = 2 if self.CP.carFingerprint in RAM_CARS else 0

    # ACC cancellation
    # if CC.cruiseControl.cancel:
    #   self.last_button_frame = self.frame
    #   can_sends.append(chryslercan.create_cruise_buttons(self.packer, CS.button_counter + 1, das_bus, cancel=True))
    #
    # # ACC resume from standstill
    # elif CC.cruiseControl.resume:
    #   self.last_button_frame = self.frame
    #   can_sends.append(chryslercan.create_cruise_buttons(self.packer, CS.button_counter + 1, das_bus, resume=True))

    # jvePilot
    if button_pressed(CS.out, ButtonType.lkasToggle, False):
      CS.lkas_disabled = not CS.lkas_disabled
      self.settingsParams.put_nonblocking("jvePilot.carstate.lkasDisabled", CS.lkas_disabled)
    if self.frame % 10 == 0:
      lkas_disabled = CS.lkas_disabled or CS.out.steerFaultPermanent
      new_msg = chryslercan.create_lkas_heartbit(self.packer, lkas_disabled, CS.lkasHeartbit)
      can_sends.append(new_msg)
    self.wheel_button_control(CC, CS, can_sends, CC.enabled, das_bus, CC.cruiseControl.cancel, CC.cruiseControl.resume)

    # autoFollow
    if CS.auto_follow:
      follow_inc_button = button_pressed(CS.out, ButtonType.followInc, False)
      follow_dec_button = button_pressed(CS.out, ButtonType.followDec, False)
      if (follow_inc_button and follow_inc_button.pressedFrames < 50) or \
        (follow_dec_button and follow_dec_button.pressedFrames < 50):
        CS.auto_follow = False
    else:
      follow_inc_button = button_pressed(CS.out, ButtonType.followInc)
      follow_dec_button = button_pressed(CS.out, ButtonType.followDec)
      if (follow_inc_button and follow_inc_button.pressedFrames >= 50) or \
        (follow_dec_button and follow_dec_button.pressedFrames >= 50):
        CS.auto_follow = True

    # HUD alerts
    if self.frame % 25 == 0:
      if CS.lkas_car_model != -1:
        can_sends.append(chryslercan.create_lkas_hud(self.packer, self.CP, CC.latActive and self.lkas_control_bit_prev, CC.hudControl.visualAlert,
                                                     self.hud_count, CS.lkas_car_model, CS.auto_high_beam,
                                                     CC.enabled or CS.out.jvePilotCarState.aolcReady, CS.out.cruiseState.available))
        self.hud_count += 1

    # steering
    new_steer = int(round(CC.actuators.torque * self.params.STEER_MAX))
    if self.frame % self.params.STEER_STEP == 0:
      lkas_control_bit = self.lkas_control_bit_prev
      if CS.out.vEgo > self.CP.minSteerSpeed or self.steerNoMinimum:
        lkas_control_bit = CC.latActive
      elif CS.out.vEgo < (self.CP.minSteerSpeed - self.steer_gap):
        lkas_control_bit = False

      if self.low_steer and self.lkas_control_bit_prev:
        # low steer vehicles never turn this off
        lkas_control_bit = True
      else:
        # EPS faults if LKAS enables too quickly
        if lkas_control_bit and self.lkas_control_bit_prev != lkas_control_bit:
          if self.next_lkas_control_change == 0:
            self.next_lkas_control_change = self.frame + 70
        else:
          self.next_lkas_control_change = 0
        lkas_control_bit = lkas_control_bit and (self.frame > self.next_lkas_control_change)

      self.lkas_control_bit_prev = lkas_control_bit

      apply_steer = 0
      if CC.latActive and lkas_control_bit:
        apply_steer = apply_meas_steer_torque_limits(new_steer, self.apply_torque_last, CS.out.steeringTorqueEps, self.params)

      self.apply_torque_last = apply_steer

      can_sends.append(chryslercan.create_lkas_command(self.packer, self.CP, int(apply_steer), lkas_control_bit, CC.latActive))

    if CC.enabled:
      # auto set profile
      follow_distance = CS.out.jvePilotCarState.accFollowDistance or 0
      acc_eco = CS.out.jvePilotCarState.accEco or 0
      personality = acc_eco if CS.longControl else DRIVE_PERSONALITY[acc_eco][follow_distance]
      if personality != self.last_personality:
        self.last_personality = personality
        self.settingsParams.put_nonblocking('LongitudinalPersonality', personality)

    self.brake_hold(CS, CC, can_sends)
    self.long_controller.acc(self.sm['longitudinalPlan'], self.frame, CC, CS, can_sends)

    self.frame += 1

    new_actuators = CC.actuators.as_builder()
    new_actuators.torque = self.apply_torque_last / self.params.STEER_MAX
    new_actuators.torqueOutputCan = self.apply_torque_last

    return new_actuators, can_sends

  def brake_hold(self, CS, CC, can_sends):
    counter_das_3_changed = CS.das_3['COUNTER'] != self.last_das_3_counter
    self.last_das_3_counter = CS.das_3['COUNTER']

    if not CS.brake_hold \
      and CS.cruise_active_actual and CS.acc_decelerating and CS.out.standstill \
      and self.brake_hold_enabled:
      CS.brake_hold = True

    if CS.brake_hold and \
      (not CC.enabled or not CS.out.cruiseState.enabled
       or CS.acc_accelerating or not CS.out.standstill
       or CC.cruiseControl.cancel or button_pressed(CS.out, ButtonType.cancel)
       or CS.out.gasPressed or CS.out.brakePressed or not CS.forward_gear):
      CS.brake_hold = False
      return

    if CS.brake_hold:
      if CS.cruise_active_actual:
        self.brake_hold_decel = min(self.brake_hold_decel, CS.das_3['ACC_DECEL']) if CS.out.standstill else -2.0
      else:
        can_sends.append(chryslercan.das_3_command(self.packer,
                                                   2 if counter_das_3_changed else 3,
                                                   False,
                                                   False,
                                                   None,
                                                   2,
                                                   False,
                                                   self.brake_hold_decel,
                                                   False,
                                                   CS.das_3))

  def wheel_button_control(self, CC, CS, can_sends, enabled, das_bus, cancel, resume):
    button_counter = CS.button_counter
    if button_counter == self.last_button_frame:
      return
    self.last_button_frame = button_counter

    if not self.long_controller.button_control(CC, CS):
      self.button_frame += 1
      button_counter_offset = 1
      buttons_to_press = []
      if cancel:
        buttons_to_press = ['ACC_Cancel']
        CS.brake_hold = False
      elif not button_pressed(CS.out, ButtonType.cancel):
        if enabled and not CS.out.brakePressed:
          button_counter_offset = [1, 1, 0, None][self.button_frame % 4]
          if button_counter_offset is not None:
            if resume:
              buttons_to_press = ["ACC_Resume"]
            elif CS.cruise_active_actual:  # Control ACC
              buttons_to_press = [self.auto_follow_button(CC, CS), self.hybrid_acc_button(CC, CS)]

      # ACC Auto enable
      if self.auto_enable_acc and self.frame < 500 and self.frame % 5 == 0:
        if not CS.out.cruiseState.available:
          buttons_to_press.append("ACC_OnOff")
        else:
          self.auto_enable_acc = False

      buttons_to_press = list(filter(None, buttons_to_press))
      if buttons_to_press is not None and len(buttons_to_press) > 0:
        new_msg = chryslercan.create_wheel_buttons_command(self.packer, das_bus, button_counter + button_counter_offset, buttons_to_press)
        can_sends.append(new_msg)

  def hybrid_acc_button(self, CC, CS):
    # Move the adaptive curse control to the target speed
    eco_limit = None
    if CS.out.jvePilotCarState.accEco == 1:
      eco_limit = self.cachedParams.get_float('jvePilot.settings.accEco.speedAheadLevel1', 1000)
    elif CS.out.jvePilotCarState.accEco == 2:
      eco_limit = self.cachedParams.get_float('jvePilot.settings.accEco.speedAheadLevel2', 1000)

    if len(self.sm['longitudinalPlan'].speeds):
      extendFuture = clip(mean(self.sm['longitudinalPlan'].accels) * 4, -EXTEND_FUTURE_MAX, EXTEND_FUTURE_MAX)
      targetFuture = mean(self.sm['longitudinalPlan'].speeds) + extendFuture + CV.KPH_TO_MS / 2
    else:
      targetFuture = 0

    if not self.sm['longitudinalPlan'].allowThrottle: # coasting?
      targetFuture = CS.out.vEgo - CV.MPH_TO_MS * 4

    target = self.acc_hysteresis(targetFuture)

    if eco_limit:
      rate = self.cachedParams.get_float('jvePilot.settings.accEco.reductionRate', 1000)
      diff = (CS.out.vEgo - CV.MPH_TO_MS * 20) * rate
      if 0 < diff < eco_limit:
        eco_limit = max(2, eco_limit - diff)

      target = min(target, CS.out.vEgo + (eco_limit * CV.MPH_TO_MS))

    target = math.floor(min(CS.out.vCruise, target) * self.round_to_unit)
    current = round(CS.out.cruiseState.speed * self.round_to_unit)
    minSetting = round(self.minAccSetting * self.round_to_unit)

    if target < current and current > minSetting:
      return 'ACC_Decel'
    elif target > current:
      return 'ACC_Accel'

  def auto_follow_button(self, CC, CS):
    if CS.out.jvePilotCarState.autoFollow:
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

      if CS.out.jvePilotCarState.accFollowDistance != target_follow and (self.autoFollowDistanceLock or target_follow) == target_follow:
        self.autoFollowDistanceLock = target_follow  # going from close to far, use upperbound

        if CS.out.jvePilotCarState.accFollowDistance > target_follow:
          return 'ACC_Distance_Dec'
        else:
          return 'ACC_Distance_Inc'

  def acc_hysteresis(self, new_target):
    if new_target > self.last_target:
      self.last_target = new_target
    elif new_target < self.last_target - 0.75 * CV.MPH_TO_MS:
      self.last_target = new_target

    return self.last_target

  @staticmethod
  def get_pid_accel_limits(CS, CP, current_speed, cruise_speed):
    return CarController.ACCEL_MIN, CarController.accel_max(CS)

  @staticmethod
  def accel_max(CS):
    maxAccel = CarController.ACCEL_MAX
    if CS.longControl:
      eco = CS.out.jvePilotCarState.accEco
      if eco == 1:
        maxAccel = cachedParams.get_float('jvePilot.settings.accEco.longAccelLevel1', 1000)
      elif eco == 2:
        maxAccel = cachedParams.get_float('jvePilot.settings.accEco.longAccelLevel2', 1000)
      else:
        maxAccel = 2

    return maxAccel
