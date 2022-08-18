from opendbc.can.packer import CANPacker
from common.realtime import DT_CTRL
from selfdrive.car import apply_toyota_steer_torque_limits
from selfdrive.car.chrysler.chryslercan import create_lkas_hud, create_lkas_command, create_lkas_heartbit, create_wheel_buttons_command
from selfdrive.car.chrysler.values import CAR, RAM_CARS, PRE_2019, CarControllerParams

from selfdrive.controls.lib.drive_helpers import V_CRUISE_MIN, V_CRUISE_MIN_IMPERIAL
from common.conversions import Conversions as CV
from common.cached_params import CachedParams
from common.params import Params
from cereal import car
from selfdrive.car.chrysler.interface import GAS_RESUME_SPEED

GearShifter = car.CarState.GearShifter
ButtonType = car.CarState.ButtonEvent.Type

V_CRUISE_MIN_IMPERIAL_MS = V_CRUISE_MIN_IMPERIAL * CV.KPH_TO_MS
V_CRUISE_MIN_MS = V_CRUISE_MIN * CV.KPH_TO_MS
AUTO_FOLLOW_LOCK_MS = 3 * CV.MPH_TO_MS
ACC_BRAKE_THRESHOLD = 2 * CV.MPH_TO_MS

class CarController:
  def __init__(self, dbc_name, CP, VM):
    self.CP = CP
    self.apply_steer_last = 0
    self.frame = 0
    self.steer_rate_limited = False

    self.hud_count = 0
    self.next_lkas_control_change = 0
    self.lkas_control_bit_prev = False
    self.last_button_counter = 0

    self.packer = CANPacker(dbc_name)
    self.params = CarControllerParams(CP)

    self.settingsParams = Params()
    self.cachedParams = CachedParams()
    self.auto_resume = self.settingsParams.get_bool('jvePilot.settings.autoResume')
    self.minAccSetting = V_CRUISE_MIN_MS if self.settingsParams.get_bool("IsMetric") else V_CRUISE_MIN_IMPERIAL_MS
    self.round_to_unit = CV.MS_TO_KPH if self.settingsParams.get_bool("IsMetric") else CV.MS_TO_MPH
    self.steerNoMinimum = self.settingsParams.get_bool("jvePilot.settings.steer.noMinimum")

    self.autoFollowDistanceLock = None
    self.button_frame = 0

  def update(self, CC, CS):
    can_sends = []

    # TODO: can we make this more sane? why is it different for all the cars?
    low_steer_models = self.CP.carFingerprint in PRE_2019
    lkas_control_bit = self.lkas_control_bit_prev
    if self.steerNoMinimum:
      lkas_control_bit = CC.enabled or low_steer_models
    elif CS.out.vEgo > self.CP.minSteerSpeed:
      lkas_control_bit = True
    elif self.CP.carFingerprint in RAM_CARS:
      if CS.out.vEgo < (self.CP.minSteerSpeed - 0.5):
        lkas_control_bit = False
    elif not low_steer_models:
      if CS.out.vEgo < (self.CP.minSteerSpeed - 3.0):
        lkas_control_bit = False

    # EPS faults if LKAS re-enables too quickly
    lkas_control_bit = lkas_control_bit and (self.frame >= self.next_lkas_control_change)
    lkas_active = CC.latActive and self.lkas_control_bit_prev

    # *** control msgs ***

    self.wheel_button_control(CC, CS, can_sends, CC.enabled, CC.cruiseControl.cancel, CC.cruiseControl.resume)

    # Lane-less button
    if CS.button_pressed(ButtonType.lkasToggle, False):
      CC.jvePilotState.carControl.useLaneLines = not CC.jvePilotState.carControl.useLaneLines
      self.settingsParams.put("jvePilot.settings.useLaneLines", "1" if CC.jvePilotState.carControl.useLaneLines else "0")
      CC.jvePilotState.notifyUi = True
    if self.frame % 10 == 0:
      new_msg = create_lkas_heartbit(self.packer, 1 if CC.jvePilotState.carControl.useLaneLines else 0, CS.lkasHeartbit)
      can_sends.append(new_msg)

    # HUD alerts
    if self.frame % 25 == 0:
      if CS.lkas_car_model != -1:
        can_sends.append(create_lkas_hud(self.packer, self.CP, lkas_active, CC.hudControl.visualAlert, self.hud_count, CS.lkas_car_model, CS.auto_high_beam))
        self.hud_count += 1

    # steering
    if self.frame % 2 == 0:
      # steer torque
      new_steer = int(round(CC.actuators.steer * self.params.STEER_MAX))
      apply_steer = apply_toyota_steer_torque_limits(new_steer, self.apply_steer_last, CS.out.steeringTorqueEps, self.params)
      if not lkas_active:
        apply_steer = 0
      self.steer_rate_limited = new_steer != apply_steer
      self.apply_steer_last = apply_steer

      idx = self.frame // 2
      can_sends.append(create_lkas_command(self.packer, self.CP, int(apply_steer), lkas_control_bit, idx))

    self.frame += 1
    if not lkas_control_bit and self.lkas_control_bit_prev:
      self.next_lkas_control_change = self.frame + 200
    self.lkas_control_bit_prev = lkas_control_bit

    new_actuators = CC.actuators.copy()
    new_actuators.steer = self.apply_steer_last / self.params.STEER_MAX

    return new_actuators, can_sends

  def wheel_button_control(self, CC, CS, can_sends, enabled, cancel, resume):
    button_counter = CS.button_counter
    if button_counter == self.last_button_counter:
      return
    self.last_button_counter = button_counter

    self.button_frame += 1
    button_counter_offset = 1
    buttons_to_press = []
    if cancel:
      buttons_to_press = ['ACC_Cancel']
    elif not CS.button_pressed(ButtonType.cancel):
      follow_inc_button = CS.button_pressed(ButtonType.followInc)
      follow_dec_button = CS.button_pressed(ButtonType.followDec)

      if CC.jvePilotState.carControl.autoFollow:
        follow_inc_button = CS.button_pressed(ButtonType.followInc, False)
        follow_dec_button = CS.button_pressed(ButtonType.followDec, False)
        if (follow_inc_button and follow_inc_button.pressedFrames < 50) or \
           (follow_dec_button and follow_dec_button.pressedFrames < 50):
          CC.jvePilotState.carControl.autoFollow = False
          CC.jvePilotState.notifyUi = True
      elif (follow_inc_button and follow_inc_button.pressedFrames >= 50) or \
           (follow_dec_button and follow_dec_button.pressedFrames >= 50):
        CC.jvePilotState.carControl.autoFollow = True
        CC.jvePilotState.notifyUi = True

      if enabled and not CS.out.brakePressed:
        button_counter_offset = [1, 1, 0, None][self.button_frame % 4]
        if button_counter_offset is not None:
          if not CS.out.cruiseState.enabled:
            if resume and self.auto_resume:  # I really want this to work!
              buttons_to_press = ["ACC_Resume"]
            elif CS.out.standstill:  # Stopped and waiting to resume
              buttons_to_press = [self.auto_resume_button(CS)]
          elif CS.out.cruiseState.enabled:  # Control ACC
            buttons_to_press = [self.auto_follow_button(CC, CS), self.hybrid_acc_button(CC, CS)]

    buttons_to_press = list(filter(None, buttons_to_press))
    if buttons_to_press is not None and len(buttons_to_press) > 0:
      new_msg = create_wheel_buttons_command(self.packer, button_counter + button_counter_offset, buttons_to_press)
      can_sends.append(new_msg)

  def auto_resume_button(self, CS):
    if self.auto_resume and CS.out.vEgo <= GAS_RESUME_SPEED:  # Keep trying while under gas_resume_speed
      return 'ACC_Resume'

  def hybrid_acc_button(self, CC, CS):
    target = CC.jvePilotState.carControl.vTargetFuture + 2 * CV.MPH_TO_MS  # add extra speed so ACC does the limiting

    # Move the adaptive curse control to the target speed
    eco_limit = None
    if CC.jvePilotState.carControl.accEco == 1:  # if eco mode
      eco_limit = self.cachedParams.get_float('jvePilot.settings.accEco.speedAheadLevel1', 1000)
    elif CC.jvePilotState.carControl.accEco == 2:  # if eco mode
      eco_limit = self.cachedParams.get_float('jvePilot.settings.accEco.speedAheadLevel2', 1000)

    if eco_limit:
      target = min(target, CS.out.vEgo + (eco_limit * CV.MPH_TO_MS))

    # ACC Braking
    diff = CS.out.vEgo - target
    if diff > ACC_BRAKE_THRESHOLD and abs(target - CC.jvePilotState.carControl.vMaxCruise) > ACC_BRAKE_THRESHOLD:  # ignore change in max cruise speed
      target -= diff

    # round to nearest unit
    target = round(min(CC.jvePilotState.carControl.vMaxCruise, target) * self.round_to_unit)
    current = round(CS.out.cruiseState.speed * self.round_to_unit)
    minSetting = round(self.minAccSetting * self.round_to_unit)

    if target < current and current > minSetting:
      return 'ACC_Decel'
    elif target > current:
      return 'ACC_Accel'

  def auto_follow_button(self, CC, CS):
    if CC.jvePilotState.carControl.autoFollow:
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

      if CC.jvePilotState.carState.accFollowDistance != target_follow and (self.autoFollowDistanceLock or target_follow) == target_follow:
        self.autoFollowDistanceLock = target_follow  # going from close to far, use upperbound

        if CC.jvePilotState.carState.accFollowDistance > target_follow:
          return 'ACC_Distance_Dec'
        else:
          return 'ACC_Distance_Inc'
