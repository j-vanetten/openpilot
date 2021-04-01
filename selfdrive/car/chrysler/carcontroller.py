from selfdrive.car import apply_toyota_steer_torque_limits
from selfdrive.car.chrysler.chryslercan import create_lkas_hud, create_lkas_command, \
                                               create_wheel_buttons_command
from selfdrive.car.chrysler.values import CAR, CarControllerParams
from opendbc.can.packer import CANPacker
from selfdrive.config import Conversions as CV
from common.op_params import opParams

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

    op_params = opParams()
    self.disable_auto_resume = op_params.get('disable_auto_resume')

  def update(self, enabled, CS, actuators, pcm_cancel_cmd, hud_alert, acc_speed, target_speed, gas_resume_speed):
    # this seems needed to avoid steering faults and to force the sync with the EPS counter
    frame = CS.lkas_counter
    if self.prev_frame == frame:
      return []

    # *** compute control surfaces ***
    # steer torque
    new_steer = actuators.steer * CarControllerParams.STEER_MAX
    apply_steer = apply_toyota_steer_torque_limits(new_steer, self.apply_steer_last,
                                                   CS.out.steeringTorqueEps, CarControllerParams)
    self.steer_rate_limited = new_steer != apply_steer

    moving_fast = CS.out.vEgo > CS.CP.minSteerSpeed  # for status message
    if CS.out.vEgo > (CS.CP.minSteerSpeed - 0.5):  # for command high bit
      self.gone_fast_yet = True
    elif self.car_fingerprint in (CAR.PACIFICA_2019_HYBRID, CAR.JEEP_CHEROKEE_2019):
      if CS.out.vEgo < (CS.CP.minSteerSpeed - 3.0):
        self.gone_fast_yet = False  # < 14.5m/s stock turns off this bit, but fine down to 13.5
    lkas_active = moving_fast and enabled

    if not lkas_active:
      apply_steer = 0

    self.apply_steer_last = apply_steer

    can_sends = []

    #*** control msgs ***

    if CS.accCancelButton or CS.accFollowDecButton or CS.accFollowIncButton:
      self.pause_control_until_frame = self.ccframe + 100  # Avoid pushing multiple buttons at the same time

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
