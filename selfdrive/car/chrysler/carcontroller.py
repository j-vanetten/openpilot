from selfdrive.car import apply_toyota_steer_torque_limits
from selfdrive.car.chrysler.chryslercan import create_lkas_hud, create_lkas_command, \
                                               create_wheel_buttons_command, create_lkas_heartbit
from selfdrive.car.chrysler.values import CAR, CarControllerParams
from opendbc.can.packer import CANPacker
from selfdrive.config import Conversions as CV

from selfdrive.controls.lib.drive_helpers import V_CRUISE_MIN, V_CRUISE_MIN_IMPERIAL
from common.cached_params import CachedParams
from common.params import Params
from cereal import car
import cereal.messaging as messaging
ButtonType = car.CarState.ButtonEvent.Type

V_CRUISE_MIN_IMPERIAL_MS = V_CRUISE_MIN_IMPERIAL * CV.KPH_TO_MS
V_CRUISE_MIN_MS = V_CRUISE_MIN * CV.KPH_TO_MS
AUTO_FOLLOW_LOCK_MS = 3 * CV.MPH_TO_MS

ACC_BRAKE_THRESHOLD = 2 * CV.MPH_TO_MS

class CarController():
  def __init__(self, dbc_name, CP, VM):
    self.apply_steer_last = 0
    self.ccframe = 0
    self.prev_frame = -1
    self.hud_count = 0
    self.car_fingerprint = CP.carFingerprint
    self.gone_fast_yet = False
    self.steer_rate_limited = False
    self.last_button_counter = 0
    self.last_frame_change = -1

    self.packer = CANPacker(dbc_name)

    self.params = Params()
    self.auto_resume = self.params.get_bool('jvePilot.settings.autoResume')
    self.minAccSetting = V_CRUISE_MIN_MS if self.params.get_bool("IsMetric") else V_CRUISE_MIN_IMPERIAL_MS
    self.round_to_unit = CV.MS_TO_KPH if self.params.get_bool("IsMetric") else CV.MS_TO_MPH

    self.cachedParams = CachedParams()
    self.autoFollowDistanceLock = None
    self.moving_fast = False
    self.sent_buttons = False

  def update(self, enabled, CS, actuators, pcm_cancel_cmd, hud_alert, gas_resume_speed, c):
    jvepilot_state = c.jvePilotState
    can_sends = []
    self.ccframe += 1

    if CS.button_pressed(ButtonType.altButton1, False):
      jvepilot_state.carControl.useLaneLines = not jvepilot_state.carControl.useLaneLines
      self.params.put("EndToEndToggle", "0" if jvepilot_state.carControl.useLaneLines else "1")
      jvepilot_state.notifyUi = True

    #*** control msgs ***
    button_counter = jvepilot_state.carState.buttonCounter
    if button_counter != self.last_button_counter:
      self.last_button_counter = button_counter

      buttons_to_press = []
      if pcm_cancel_cmd or CS.button_pressed(ButtonType.cancel):
        buttons_to_press = ['ACC_CANCEL']
      elif CS.button_pressed(ButtonType.setCruise):
        buttons_to_press = ['ACC_ENABLE']
      else:
        if CS.button_pressed(ButtonType.altButton2, False):
          jvepilot_state.carControl.accEco = (jvepilot_state.carControl.accEco + 1) % 3
          jvepilot_state.notifyUi = True

        buttons_to_press.append(self.follow_buttons(CS, jvepilot_state))

        if not enabled:
          if CS.button_pressed(ButtonType.resumeCruise):
            buttons_to_press.append('ACC_RESUME')
          elif CS.button_pressed(ButtonType.accelCruise):
            buttons_to_press.append('ACC_SPEED_INC')
          elif CS.button_pressed(ButtonType.decelCruise):
            buttons_to_press.append('ACC_SPEED_DEC')
        elif not CS.out.brakePressed:
          if CS.out.cruiseState.enabled:  # Control ACC
            if button_counter % 6 < 1:
              buttons_to_press.append(self.auto_follow_button(CS, jvepilot_state))
            if button_counter % 2 < 1:
              buttons_to_press.append(self.hybrid_acc_button(CS, jvepilot_state))
          elif CS.out.standstill:  # Stopped and waiting to resume
            if button_counter % 10 < 8:
              buttons_to_press.append(self.auto_resume_button(CS, gas_resume_speed))

      buttons = list(filter(lambda button: button is not None, buttons_to_press))
      has_buttons = len(buttons) > 0
      if has_buttons or self.sent_buttons or len(CS.out.buttonEvents) > 0:
        self.sent_buttons = has_buttons
        send_wheel_message = create_wheel_buttons_command(self.packer, button_counter + 1, buttons, CS.wheelButtons)
        can_sends.append(send_wheel_message)

    frame = CS.lkas_counter
    if self.prev_frame != frame:
      self.prev_frame = frame
      self.last_frame_change = self.ccframe
    else:
      frame = (CS.lkas_counter + (self.ccframe - self.last_frame_change)) % 16  # Predict the next frame

    # *** compute control surfaces ***
    # steer torque
    new_steer = int(round(actuators.steer * CarControllerParams.STEER_MAX))
    apply_steer = apply_toyota_steer_torque_limits(new_steer, self.apply_steer_last,
                                                   CS.out.steeringTorqueEps, CarControllerParams)
    self.steer_rate_limited = new_steer != apply_steer

    if self.car_fingerprint in (CAR.JEEP_CHEROKEE, CAR.PACIFICA_2017_HYBRID, CAR.PACIFICA_2018, CAR.PACIFICA_2018_HYBRID):
      self.gone_fast_yet = self.gone_fast_yet or CS.torq_status > 1
      self.moving_fast = not CS.out.steerError and CS.lkas_active
    else:
      self.moving_fast = CS.out.vEgo > CS.CP.minSteerSpeed  # for status message
      if CS.out.vEgo > (CS.CP.minSteerSpeed - 0.5):  # for command high bit
        self.gone_fast_yet = True
      elif CS.out.vEgo < (CS.CP.minSteerSpeed - 3.0):
        self.gone_fast_yet = False  # < 14.5m/s stock turns off this bit, but fine down to 13.5

    lkas_active = self.moving_fast and enabled
    if not lkas_active:
      apply_steer = 0

    self.apply_steer_last = apply_steer

    if self.ccframe % 10 == 0:  # 0.1s period
      new_msg = create_lkas_heartbit(self.packer, 0 if jvepilot_state.carControl.useLaneLines else 1, CS.lkasHeartbit)
      can_sends.append(new_msg)

    if (self.ccframe % 25 == 0):  # 0.25s period
      if (CS.lkas_car_model != -1):
        new_msg = create_lkas_hud(
          self.packer, CS.out.gearShifter, lkas_active, hud_alert,
          self.hud_count, CS.lkas_car_model)
        can_sends.append(new_msg)
        self.hud_count += 1

    new_msg = create_lkas_command(self.packer, int(apply_steer), self.gone_fast_yet, frame)
    can_sends.append(new_msg)

    return can_sends

  def auto_resume_button(self, CS, gas_resume_speed):
    if self.auto_resume and CS.out.vEgo <= gas_resume_speed:  # Keep trying while under gas_resume_speed
      return 'ACC_RESUME'

  def follow_buttons(self, CS, jvepilot_state):
    button_to_press = None

    enable_auto_follow = None
    if follow_inc_button := CS.button_pressed(ButtonType.followInc):
      if follow_inc_button.pressedFrames >= 50:
        enable_auto_follow = True
    elif follow_inc_button := CS.button_pressed(ButtonType.followInc, False):
      if follow_inc_button.pressedFrames < 50:
        enable_auto_follow = False
        button_to_press = 'ACC_FOLLOW_INC'
    elif follow_dec_button := CS.button_pressed(ButtonType.followDec):
      if follow_dec_button.pressedFrames >= 50:
        enable_auto_follow = True
    elif follow_dec_button := CS.button_pressed(ButtonType.followDec, False):
      if follow_dec_button.pressedFrames < 50:
        enable_auto_follow = False
        button_to_press = 'ACC_FOLLOW_DEC'

    if enable_auto_follow is not None:
      jvepilot_state.notifyUi = jvepilot_state.carControl.autoFollow != enable_auto_follow
      jvepilot_state.carControl.autoFollow = enable_auto_follow

    return button_to_press

  def hybrid_acc_button(self, CS, jvepilot_state):
    target = jvepilot_state.carControl.vTargetFuture

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
    if diff > ACC_BRAKE_THRESHOLD and abs(target - jvepilot_state.carControl.vMaxCruise) > ACC_BRAKE_THRESHOLD:  # ignore change in max cruise speed
      target -= diff

    # round to nearest unit
    target = round(target * self.round_to_unit)
    current = round(CS.out.cruiseState.speed * self.round_to_unit)

    if target < current and current > self.minAccSetting:
      CS.dashboard["ACC_SPEED_CONFIG_KPH"] -= (1. / self.round_to_unit) * CV.MS_TO_KPH
      return 'ACC_SPEED_DEC'
    elif target > current:
      CS.dashboard["ACC_SPEED_CONFIG_KPH"] += (1. / self.round_to_unit) * CV.MS_TO_KPH
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