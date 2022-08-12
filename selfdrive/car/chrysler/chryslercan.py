from cereal import car
from selfdrive.car.chrysler.values import RAM_CARS

GearShifter = car.CarState.GearShifter
VisualAlert = car.CarControl.HUDControl.VisualAlert

def create_lkas_hud(packer, CP, lkas_active, hud_alert, hud_count, car_model, auto_high_beam):
  # LKAS_HUD - Controls what lane-keeping icon is displayed

  # == Color ==
  # 0 hidden?
  # 1 white
  # 2 green
  # 3 ldw

  # == Lines ==
  # 03 white Lines
  # 04 grey lines
  # 09 left lane close
  # 0A right lane close
  # 0B left Lane very close
  # 0C right Lane very close
  # 0D left cross cross
  # 0E right lane cross

  # == Alerts ==
  # 7 Normal
  # 6 lane departure place hands on wheel

  color = 2 if lkas_active else 1
  lines = 3 if lkas_active else 0
  alerts = 7 if lkas_active else 0

  if hud_count < (1 * 4):  # first 3 seconds, 4Hz
    alerts = 1

  if hud_alert in (VisualAlert.ldw, VisualAlert.steerRequired):
    color = 4
    lines = 0
    alerts = 6

  values = {
    "LKAS_ICON_COLOR": color,
    "CAR_MODEL": car_model,
    "LKAS_LANE_LINES": lines,
    "LKAS_ALERTS": alerts,
  }

  if CP.carFingerprint in RAM_CARS:
    values['AUTO_HIGH_BEAM_ON'] = auto_high_beam

  return packer.make_can_msg("DAS_6", 0, values)


def create_lkas_command(packer, CP, apply_steer, lkas_control_bit, frame):
  # LKAS_COMMAND Lane-keeping signal to turn the wheel
  enabled_val = 2 if CP.carFingerprint in RAM_CARS else 1
  values = {
    "STEERING_TORQUE": apply_steer,
    "LKAS_CONTROL_BIT": enabled_val if lkas_control_bit else 0,
  }
  return packer.make_can_msg("LKAS_COMMAND", 0, values, frame % 0x10)

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

  return packer.make_can_msg("CRUISE_BUTTONS", 0, values)


def acc_log(packer, adjustment, aTarget, vTarget, stopping, standstill):
  values = {
    'OP_A_TARGET': aTarget,
    'OP_V_TARGET': vTarget,
    'ADJUSTMENT': adjustment,
    'STOPPING': stopping,
    'STANDSTILL': standstill,
  }
  return packer.make_can_msg("ACC_LOG", 0, values)


def acc_command(packer, counter, enabled, go, gas, max_gear, stop, brake, das_3):
  values = das_3.copy()  # forward what we parsed
  values['ACC_AVAILABLE'] = 1
  values['ACC_ACTIVE'] = enabled
  values['COUNTER'] = counter % 0x10

  if go is not None:
    values['ACC_GO'] = go

  if stop is not None:
    values['ACC_STANDSTILL'] = stop

  if brake is not None:
    values['ACC_DECEL_REQ'] = enabled
    values['ACC_DECEL'] = brake

  if gas is not None:
    values['ACC_TORQ_REQ'] = enabled
    values['ACC_TORQ'] = gas

  if max_gear is not None:
    values['GR_MAX_REQ'] = max_gear

  return packer.make_can_msg("DAS_3", 0, values)
