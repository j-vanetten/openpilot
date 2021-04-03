from selfdrive.car import apply_toyota_steer_torque_limits
from selfdrive.car.chrysler.chryslercan import create_lkas_hud, create_lkas_command, \
                                               create_wheel_buttons_command
from selfdrive.car.chrysler.values import CAR, CarControllerParams
from opendbc.can.packer import CANPacker
from selfdrive.config import Conversions as CV

from common.op_params import opParams
from cereal import car
import cereal.messaging as messaging
ButtonType = car.CarState.ButtonEvent.Type

MIN_ACC_SPEED_MPH = 20

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

    self.pm = messaging.PubMaster(['autoFollow'])
    self.op_params = opParams()
    self.disable_auto_resume = self.op_params.get('disable_auto_resume')
    self.start_with_auto_follow_disabled = self.op_params.get('start_with_auto_follow_disabled')
    self.auto_follow_enabled = not self.start_with_auto_follow_disabled

  def update(self, enabled, CS, actuators, pcm_cancel_cmd, hud_alert, acc_speed, target_speed, gas_resume_speed):
    # this seems needed to avoid steering faults and to force the sync with the EPS counter
    frame = CS.lkas_counter
    if self.prev_frame == frame:
      return []

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


    can_sends = []

    #*** control msgs ***
    follow_inc_button = CS.button_pressed(ButtonType.followInc)
    follow_dec_button = CS.button_pressed(ButtonType.followDec)
    if CS.button_pressed(ButtonType.cancel) or follow_inc_button or follow_dec_button:
      self.pause_control_until_frame = self.ccframe + 25  # Avoid pushing multiple buttons at the same time

    # for 2 seconds at startup, let the UI know what state we are in
    if self.ccframe <= 200 and self.ccframe % 25 == 0:
      self.af_notify(self.auto_follow_enabled)

    if self.auto_follow_enabled:
      follow_inc_button = CS.button_pressed(ButtonType.followInc, False)
      follow_dec_button = CS.button_pressed(ButtonType.followDec, False)
      if (follow_inc_button and follow_inc_button.pressedFrames < 50) or (follow_dec_button and follow_dec_button.pressedFrames < 50):
        self.af_notify(False)  # override
    elif (follow_inc_button and follow_inc_button.pressedFrames >= 50) or (follow_dec_button and follow_dec_button.pressedFrames >= 50):
      self.af_notify(True)  # long pressed to re-enable

    button_counter_change = CS.buttonCounter != self.last_button_counter
    if button_counter_change:
      self.last_button_counter = CS.buttonCounter

    if pcm_cancel_cmd:
      new_msg = create_wheel_buttons_command(self, self.packer, CS.buttonCounter, 'ACC_CANCEL', True)
      can_sends.append(new_msg)

    elif enabled and button_counter_change and not CS.out.brakePressed:
      if self.ccframe >= self.pause_control_until_frame and self.ccframe % 10 <= 4:  # press for 50ms
        button_to_press = None
        if (not self.disable_auto_resume) and (not CS.out.cruiseState.enabled or CS.out.standstill):
          if CS.out.vEgo <= gas_resume_speed:  # Keep trying while under gas_resume_speed
            button_to_press = 'ACC_RESUME'
        elif CS.out.cruiseState.enabled:
          distance_config = self.target_follow(CS)
          if self.auto_follow_enabled and CS.accDistanceConfig != distance_config:
            if CS.accDistanceConfig > distance_config:
              button_to_press = 'ACC_FOLLOW_DEC'
            else:
              button_to_press = 'ACC_FOLLOW_INC'
          else:
            # Move the adaptive curse control to the target speed
            current = round(acc_speed * CV.MS_TO_MPH)
            target = round(target_speed * CV.MS_TO_MPH)

            if target < current and current > MIN_ACC_SPEED_MPH:
              button_to_press = 'ACC_SPEED_DEC'
            elif target > current:
              button_to_press = 'ACC_SPEED_INC'

        if button_to_press is not None:
          new_msg = create_wheel_buttons_command(self, self.packer, CS.buttonCounter + 1, button_to_press, True)
          can_sends.append(new_msg)

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

    self.ccframe += 1
    self.prev_frame = frame

    return can_sends

  def af_notify(self, enabled):
    self.auto_follow_enabled = enabled
    msg = messaging.new_message('autoFollow')
    msg.autoFollow.enabled = enabled
    self.pm.send('autoFollow', msg)

  def target_follow(self, CS):
    if CS.out.vEgo < self.op_params.get('auto_follow_2bars_speed') * CV.MPH_TO_MS:
      return 0
    elif CS.out.vEgo < self.op_params.get('auto_follow_3bars_speed') * CV.MPH_TO_MS:
      return 1
    elif CS.out.vEgo < self.op_params.get('auto_follow_4bars_speed') * CV.MPH_TO_MS:
      return 2
    else:
      return 3
