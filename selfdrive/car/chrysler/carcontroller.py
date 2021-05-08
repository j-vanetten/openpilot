from selfdrive.car import apply_toyota_steer_torque_limits
from selfdrive.car.chrysler.chryslercan import create_lkas_hud, create_lkas_command, \
  create_wheel_buttons_command
from selfdrive.car.chrysler.values import CAR, CarControllerParams
from opendbc.can.packer import CANPacker
from selfdrive.config import Conversions as CV

from common.cached_params import CachedParams
from common.params import Params
from cereal import car
import cereal.messaging as messaging
ButtonType = car.CarState.ButtonEvent.Type

MIN_ACC_SPEED_MPH = 20
AUTO_FOLLOW_LOCK_MPH = 4 * CV.MPH_TO_MS

class CarController():
  def __init__(self, dbc_name, CP, VM):
    self.apply_steer_last = 0
    self.ccframe = 0
    self.prev_frame = -1
    self.hud_count = 0
    self.car_fingerprint = CP.carFingerprint
    self.gone_fast_yet = False
    self.steer_rate_limited = False
    self.last_button_counter = -1
    self.pause_control_until_frame = 0

    self.packer = CANPacker(dbc_name)

    self.params = Params()
    self.cachedParams = CachedParams()
    self.disable_auto_resume = self.params.get('jvePilot.settings.autoResume', encoding='utf8') == "0"
    self.autoFollowDistanceLock = None

  def update(self, enabled, CS, actuators, pcm_cancel_cmd, hud_alert, gas_resume_speed, jvepilot_state):
    can_sends = []
    self.ccframe += 1

    #*** control msgs ***
    button_counter = jvepilot_state.carState.buttonCounter
    if button_counter != self.last_button_counter:
      self.last_button_counter = button_counter

      follow_inc_button = CS.button_pressed(ButtonType.followInc)
      follow_dec_button = CS.button_pressed(ButtonType.followDec)
      if CS.button_pressed(ButtonType.cancel) or follow_inc_button or follow_dec_button:
        self.pause_control_until_frame = self.ccframe + 25  # Avoid pushing multiple buttons at the same time

      if jvepilot_state.carControl.autoFollow:
        follow_inc_button = CS.button_pressed(ButtonType.followInc, False)
        follow_dec_button = CS.button_pressed(ButtonType.followDec, False)
        if (follow_inc_button and follow_inc_button.pressedFrames < 50) or (follow_dec_button and follow_dec_button.pressedFrames < 50):
          jvepilot_state.carControl.autoFollow = False
          jvepilot_state.notifyUi = True
      elif (follow_inc_button and follow_inc_button.pressedFrames >= 50) or (follow_dec_button and follow_dec_button.pressedFrames >= 50):
        jvepilot_state.carControl.autoFollow = True
        jvepilot_state.notifyUi = True

      button_to_press = None
      if pcm_cancel_cmd:
        button_to_press = 'ACC_CANCEL'
      elif enabled and not CS.out.brakePressed:
        if self.ccframe >= self.pause_control_until_frame and self.ccframe % 8 < 4:  # press for 40ms, not for 40ms
          if (not CS.out.cruiseState.enabled) or CS.out.standstill:  # Stopped and waiting to resume
            button_to_press = self.auto_resume_button(CS, gas_resume_speed)
          elif CS.out.cruiseState.enabled:  # Control ACC
            button_to_press = self.auto_follow_button(CS, jvepilot_state) or self.hybrid_acc_button(CS, jvepilot_state)

      if button_to_press:
        new_msg = create_wheel_buttons_command(self, self.packer, button_counter + 1, button_to_press, True)
        can_sends.append(new_msg)

    frame = CS.lkas_counter
    if self.prev_frame != frame:
      self.prev_frame = frame
      self.last_frame_change = self.ccframe
    else:
      frame = (CS.lkas_counter + (self.ccframe - self.last_frame_change)) % 16  # guess the next frame

    # *** compute control surfaces ***
    # steer torque
    new_steer = int(round(actuators.steer * CarControllerParams.STEER_MAX))
    apply_steer = apply_toyota_steer_torque_limits(new_steer, self.apply_steer_last,
                                                   CS.out.steeringTorqueEps, CarControllerParams)
    self.steer_rate_limited = new_steer != apply_steer

    moving_fast = CS.out.vEgo > CS.CP.minSteerSpeed  # for status message
    if CS.out.vEgo > (CS.CP.minSteerSpeed - 0.5):  # for command high bit
      self.gone_fast_yet = True
    elif self.car_fingerprint in (CAR.PACIFICA_2019_HYBRID, CAR.PACIFICA_2020, CAR.JEEP_CHEROKEE_2019):
      if CS.out.vEgo < (CS.CP.minSteerSpeed - 3.0):
        self.gone_fast_yet = False  # < 14.5m/s stock turns off this bit, but fine down to 13.5
    lkas_active = moving_fast and enabled

    if not lkas_active:
      apply_steer = 0

    self.apply_steer_last = apply_steer

    # LKAS_HEARTBIT is forwarded by Panda so no need to send it here.
    # frame is 100Hz (0.01s period)
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
    if (not self.disable_auto_resume) and CS.out.vEgo <= gas_resume_speed:  # Keep trying while under gas_resume_speed
      return 'ACC_RESUME'

  def hybrid_acc_button(self, CS, jvepilot_state):
    # Move the adaptive curse control to the target speed
    acc_speed = CS.out.cruiseState.speed
    current = round(acc_speed * CV.MS_TO_MPH)
    target = round(jvepilot_state.carControl.vTargetFuture * CV.MS_TO_MPH)

    if jvepilot_state.carControl.accEco == 1:  # if eco mode
      current_speed = round(CS.out.vEgo * CV.MS_TO_MPH)
      target = min(target, int(current_speed + self.cachedParams.get_float('jvePilot.settings.accEco.speedAheadLevel1', 1000)))
    elif jvepilot_state.carControl.accEco == 2:  # if eco mode
      current_speed = round(CS.out.vEgo * CV.MS_TO_MPH)
      target = min(target, int(current_speed + self.cachedParams.get_float('jvePilot.settings.accEco.speedAheadLevel2', 1000)))

    if target < current and current > MIN_ACC_SPEED_MPH:
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

      if self.autoFollowDistanceLock is not None and abs(crossover[self.autoFollowDistanceLock] - CS.out.vEgo) > AUTO_FOLLOW_LOCK_MPH:
        self.autoFollowDistanceLock = None  # unlock

      if jvepilot_state.carState.accFollowDistance != target_follow and (self.autoFollowDistanceLock or target_follow) == target_follow:
        self.autoFollowDistanceLock = target_follow  # going from close to far, use upperbound

        if jvepilot_state.carState.accFollowDistance > target_follow:
          return 'ACC_FOLLOW_DEC'
        else:
          return 'ACC_FOLLOW_INC'