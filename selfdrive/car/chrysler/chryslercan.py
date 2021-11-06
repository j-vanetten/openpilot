from cereal import car
from selfdrive.car import make_can_msg


GearShifter = car.CarState.GearShifter
VisualAlert = car.CarControl.HUDControl.VisualAlert

def create_lkas_hud(packer, gear, lkas_active, hud_alert, hud_count, lkas_car_model):
  # LKAS_HUD 0x2a6 (678) Controls what lane-keeping icon is displayed.

  if hud_alert in [VisualAlert.steerRequired, VisualAlert.ldw]:
    msg = b'\x00\x00\x00\x03\x00\x00\x00\x00'
    return make_can_msg(0x2a6, msg, 0)

  color = 1  # default values are for park or neutral in 2017 are 0 0, but trying 1 1 for 2019
  lines = 1
  alerts = 0

  if hud_count < (1 * 4):  # first 3 seconds, 4Hz
    alerts = 1
  # CAR.PACIFICA_2018_HYBRID and CAR.PACIFICA_2019_HYBRID
  # had color = 1 and lines = 1 but trying 2017 hybrid style for now.
  if gear in (GearShifter.drive, GearShifter.reverse, GearShifter.low):
    if lkas_active:
      color = 2  # control active, display green.
      lines = 6
    else:
      color = 1  # control off, display white.
      lines = 1

  values = {
    "LKAS_ICON_COLOR": color,  # byte 0, last 2 bits
    "CAR_MODEL": lkas_car_model,  # byte 1
    "LKAS_LANE_LINES": lines,  # byte 2, last 4 bits
    "LKAS_ALERTS": alerts,  # byte 3, last 4 bits
  }

  return packer.make_can_msg("LKAS_HUD", 0, values)  # 0x2a6


def create_lkas_command(packer, apply_steer, moving_fast, frame):
  # LKAS_COMMAND 0x292 (658) Lane-keeping signal to turn the wheel.
  values = {
    "LKAS_STEERING_TORQUE": apply_steer,
    "LKAS_HIGH_TORQUE": int(moving_fast),
    "COUNTER": frame % 0x10,
  }
  return packer.make_can_msg("LKAS_COMMAND", 0, values)

def create_lkas_heartbit(packer, value, lkasHeartbit):
  # LKAS_HEARTBIT (697) LKAS heartbeat
  values = lkasHeartbit.copy()  # forward what we parsed
  values["LKAS_DISABLED"] = value
  return packer.make_can_msg("LKAS_HEARTBIT", 0, values)

def create_wheel_buttons_command(packer, counter, buttons):
  # WHEEL_BUTTONS (571) Message sent
  values = {
    "COUNTER": counter % 0x10,
  }

  for b in buttons:
    if b is not None:
      values[b] = 1

  return packer.make_can_msg("WHEEL_BUTTONS", 0, values)

def acc_log(packer, aTarget, vTarget, long_starting, long_stopping):
  values = {
    'OP_A_TARGET': aTarget,
    'OP_V_TARGET': vTarget,
    'LONG_STARTING': long_starting,
    'LONG_STOPPING': long_stopping,
  }
  return packer.make_can_msg("ACC_LOG", 0, values)

def acc_command(packer, counter, go, gas, stop, brake, acc_2):
  values = acc_2.copy()  # forward what we parsed
  values['COUNTER'] = counter % 0x10
  values['ACC_GO'] = go
  values['ACC_STOP'] = stop

  if brake != 4:
    values['ACC_DECEL_REQ'] = 1
    values['ACC_DECEL'] = brake
  else:
    values['ACC_DECEL_REQ'] = 0
    values['ACC_DECEL'] = 4

  if brake == 4 and gas != 0:
    values['ACC_TORQ_REQ'] = 1
    values['ACC_TORQ'] = gas
  else:
    values['ACC_TORQ_REQ'] = 0
    values['ACC_TORQ'] = 0

  return packer.make_can_msg("ACC_2", 0, values)

def acc_command_v2(packer, counter, gas, acc_1):
  values = acc_1.copy()  # forward what we parsed
  values['COUNTER'] = counter % 0x10

  if gas != 0:
    values['ACC_TORQ_REQ'] = 1
    values['ACC_TORQ'] = gas
  else:
    values['ACC_TORQ_REQ'] = 0
    values['ACC_TORQ'] = 0

  return packer.make_can_msg("ACC_1", 0, values)
