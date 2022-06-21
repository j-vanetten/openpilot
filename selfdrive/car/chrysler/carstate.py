from cereal import car
from common.conversions import Conversions as CV
from opendbc.can.parser import CANParser
from opendbc.can.can_define import CANDefine
from selfdrive.car.interfaces import CarStateBase
from selfdrive.car.chrysler.values import DBC, STEER_THRESHOLD, CarControllerParams
from common.cached_params import CachedParams
from common.op_params import opParams
from common.params import Params
import numpy as np

ButtonType = car.CarState.ButtonEvent.Type

CHECK_BUTTONS = {ButtonType.cancel: ["WHEEL_BUTTONS", 'ACC_CANCEL'],
                 ButtonType.resumeCruise: ["WHEEL_BUTTONS", 'ACC_RESUME'],
                 ButtonType.accelCruise: ["WHEEL_BUTTONS", 'ACC_SPEED_INC'],
                 ButtonType.decelCruise: ["WHEEL_BUTTONS", 'ACC_SPEED_DEC'],
                 ButtonType.followInc: ["WHEEL_BUTTONS", 'ACC_FOLLOW_INC'],
                 ButtonType.followDec: ["WHEEL_BUTTONS", 'ACC_FOLLOW_DEC'],
                 ButtonType.lkasToggle: ["TRACTION_BUTTON", 'TOGGLE_LKAS']}

PEDAL_GAS_PRESSED_XP = [0, 32, 255]
PEDAL_BRAKE_PRESSED_XP = [0, 24, 255]
PEDAL_PRESSED_YP = [0, 128, 255]

class CarState(CarStateBase):
  def __init__(self, CP):
    super().__init__(CP)
    can_define = CANDefine(DBC[CP.carFingerprint]["pt"])
    self.shifter_values = can_define.dv["GEAR"]["PRNDL"]
    self.cachedParams = CachedParams()
    self.opParams = opParams()
    self.lkasHeartbit = None
    self.dashboard = None
    self.speedRequested = 0
    self.params = Params()

  def update(self, cp, cp_cam):
    min_steer_check = self.opParams.get('steer.checkMinimum')

    ret = car.CarState.new_message()

    self.frame = int(cp.vl["EPS_STATUS"]["COUNTER"])

    ret.doorOpen = any([cp.vl["DOORS"]["DOOR_OPEN_FL"],
                        cp.vl["DOORS"]["DOOR_OPEN_FR"],
                        cp.vl["DOORS"]["DOOR_OPEN_RL"],
                        cp.vl["DOORS"]["DOOR_OPEN_RR"]])
    ret.seatbeltUnlatched = cp.vl["SEATBELT_STATUS"]["SEATBELT_DRIVER_UNLATCHED"] == 1

    ret.brakePressed = cp.vl["BRAKE_2"]["BRAKE_PRESSED_2"] == 5  # human-only
    ret.brake = 0
    ret.gas = cp.vl["ACCEL_GAS_134"]["ACCEL_134"]
    ret.gasPressed = ret.gas > 1e-5

    ret.espDisabled = (cp.vl["TRACTION_BUTTON"]["TRACTION_OFF"] == 1)

    ret.wheelSpeeds = self.get_wheel_speeds(
      cp.vl["WHEEL_SPEEDS"]["WHEEL_SPEED_FL"],
      cp.vl["WHEEL_SPEEDS"]["WHEEL_SPEED_FR"],
      cp.vl["WHEEL_SPEEDS"]["WHEEL_SPEED_RL"],
      cp.vl["WHEEL_SPEEDS"]["WHEEL_SPEED_RR"],
      unit=1,
    )
    ret.vEgoRaw = cp.vl["BRAKE_1"]["VEHICLE_SPEED_KPH"] * CV.KPH_TO_MS
    ret.vEgo, ret.aEgo = self.update_speed_kf(ret.vEgoRaw)
    ret.standstill = ret.vEgoRaw <= 0.1

    ret.leftBlinker = cp.vl["STEERING_LEVERS"]["TURN_SIGNALS"] == 1
    ret.rightBlinker = cp.vl["STEERING_LEVERS"]["TURN_SIGNALS"] == 2
    ret.steeringAngleDeg = cp.vl["STEERING"]["STEER_ANGLE"]
    ret.steeringRateDeg = cp.vl["STEERING"]["STEERING_RATE"]
    ret.gearShifter = self.parse_gear_shifter(self.shifter_values.get(cp.vl["GEAR"]["PRNDL"], None))

    ret.cruiseState.enabled = cp.vl["ACC_2"]["ACC_ENABLED"] == 1  # ACC is green.
    ret.cruiseState.available = cp.vl["DASHBOARD"]['CRUISE_STATE'] in [3, 4]  # the comment below says 3 and 4 are ACC mode
    ret.cruiseState.speed = cp.vl["DASHBOARD"]["ACC_SPEED_CONFIG_KPH"] * CV.KPH_TO_MS
    # CRUISE_STATE is a three bit msg, 0 is off, 1 and 2 are Non-ACC mode, 3 and 4 are ACC mode, find if there are other states too
    ret.cruiseState.nonAdaptive = cp.vl["DASHBOARD"]["CRUISE_STATE"] in (1, 2)
    ret.accFaulted = cp.vl["ACC_2"]["ACC_FAULTED"] != 0
    self.dashboard = cp.vl["DASHBOARD"]

    ret.steeringTorque = cp.vl["EPS_STATUS"]["TORQUE_DRIVER"]
    ret.steeringTorqueEps = cp.vl["EPS_STATUS"]["TORQUE_MOTOR"]
    ret.steeringPressed = abs(ret.steeringTorque) > STEER_THRESHOLD
    self.lkas_active = cp.vl["EPS_STATUS"]["LKAS_ACTIVE"] == 1
    ret.steerFaultPermanent = cp.vl["EPS_STATUS"]["LKAS_STEER_FAULT"] == 1 or (min_steer_check and not self.lkas_active and ret.vEgo > self.CP.minSteerSpeed)

    ret.genericToggle = bool(cp.vl["STEERING_LEVERS"]["HIGH_BEAM_FLASH"])

    if self.CP.enableBsm:
      ret.leftBlindspot = cp.vl["BLIND_SPOT_WARNINGS"]["BLIND_SPOT_LEFT"] == 1
      ret.rightBlindspot = cp.vl["BLIND_SPOT_WARNINGS"]["BLIND_SPOT_RIGHT"] == 1

    self.lkas_counter = cp_cam.vl["LKAS_COMMAND"]["COUNTER"]
    self.lkas_car_model = cp_cam.vl["LKAS_HUD"]["CAR_MODEL"]
    self.torq_status = cp.vl["EPS_STATUS"]["TORQ_STATUS"]

    brake = cp.vl["BRAKE_1"]["BRAKE_VAL_TOTAL"]
    gas = cp.vl["ACCEL_RELATED_120"]["ACCEL"]
    if gas > 0:
      ret.jvePilotCarState.pedalPressedAmount = float(np.interp(gas, PEDAL_GAS_PRESSED_XP, PEDAL_PRESSED_YP)) / 256
    elif brake > 0:
      ret.jvePilotCarState.pedalPressedAmount = float(np.interp(brake / 16, PEDAL_BRAKE_PRESSED_XP, PEDAL_PRESSED_YP)) / -256
    else:
      ret.jvePilotCarState.pedalPressedAmount = 0

    ret.jvePilotCarState.accFollowDistance = int(min(3, max(0, cp.vl["DASHBOARD"]['ACC_DISTANCE_CONFIG_2'])))
    ret.jvePilotCarState.buttonCounter = int(cp.vl["WHEEL_BUTTONS"]['COUNTER'])
    self.lkasHeartbit = cp_cam.vl["LKAS_HEARTBIT"]

    button_events = []
    for buttonType in CHECK_BUTTONS:
      self.check_button(button_events, buttonType, bool(cp.vl[CHECK_BUTTONS[buttonType][0]][CHECK_BUTTONS[buttonType][1]]))
    ret.buttonEvents = button_events

    if ret.cruiseState.available:
      if self.button_pressed(ButtonType.followInc, False):
        CarControllerParams.STEER_DELTA_UP += 1
        CarControllerParams.STEER_DELTA_DOWN += 1
        print(f"STEER_DELTA: {CarControllerParams.STEER_DELTA_UP}")
        self.params.put("jvePilot.setting.steerDelta", str(CarControllerParams.STEER_DELTA_DOWN))
      elif self.button_pressed(ButtonType.followDec, False):
        CarControllerParams.STEER_MAX += 1
        print(f"STEER_MAX: {CarControllerParams.STEER_MAX}")
        self.params.put("jvePilot.setting.steerMax", str(CarControllerParams.STEER_MAX))
    else:  # RESET
      if self.button_pressed(ButtonType.followInc, False):
        CarControllerParams.STEER_DELTA_UP = 3
        CarControllerParams.STEER_DELTA_DOWN = 3
        print(f"STEER_DELTA: {CarControllerParams.STEER_DELTA_UP}")
        self.params.put("jvePilot.setting.steerDelta", str(CarControllerParams.STEER_DELTA_DOWN))
      elif self.button_pressed(ButtonType.followDec, False):
        CarControllerParams.STEER_MAX = 261
        print(f"STEER_MAX: {CarControllerParams.STEER_MAX}")
        self.params.put("jvePilot.setting.steerMax", str(CarControllerParams.STEER_MAX))

    return ret

  def check_button(self, button_events, button_type, pressed):
    pressed_frames = 0
    pressed_changed = False
    for ob in self.out.buttonEvents:
      if ob.type == button_type:
        pressed_frames = ob.pressedFrames
        pressed_changed = ob.pressed != pressed
        break

    if pressed or pressed_changed:
      be = car.CarState.ButtonEvent.new_message()
      be.type = button_type
      be.pressed = pressed
      be.pressedFrames = pressed_frames

      if not pressed_changed:
        be.pressedFrames += 1

      button_events.append(be)

  def button_pressed(self, button_type, pressed=True):
    for b in self.out.buttonEvents:
      if b.type == button_type:
        if b.pressed == pressed:
          return b
        break

  @staticmethod
  def get_can_parser(CP):
    signals = [
      # sig_name, sig_address, default
      ("PRNDL", "GEAR"),
      ("DOOR_OPEN_FL", "DOORS"),
      ("DOOR_OPEN_FR", "DOORS"),
      ("DOOR_OPEN_RL", "DOORS"),
      ("DOOR_OPEN_RR", "DOORS"),
      ("BRAKE_PRESSED_2", "BRAKE_2"),
      ("ACCEL_134", "ACCEL_GAS_134"),
      ("WHEEL_SPEED_FL", "WHEEL_SPEEDS"),
      ("WHEEL_SPEED_RR", "WHEEL_SPEEDS"),
      ("WHEEL_SPEED_RL", "WHEEL_SPEEDS"),
      ("WHEEL_SPEED_FR", "WHEEL_SPEEDS"),
      ("STEER_ANGLE", "STEERING"),
      ("STEERING_RATE", "STEERING"),
      ("TURN_SIGNALS", "STEERING_LEVERS"),
      ("ACC_ENABLED", "ACC_2"),
      ("ACC_FAULTED", "ACC_2"),
      ("HIGH_BEAM_FLASH", "STEERING_LEVERS"),
      ("ACC_SPEED_CONFIG_KPH", "DASHBOARD"),
      ("CRUISE_STATE", "DASHBOARD"),
      ("TORQUE_DRIVER", "EPS_STATUS"),
      ("TORQUE_MOTOR", "EPS_STATUS"),
      ("LKAS_ACTIVE", "EPS_STATUS"),
      ("LKAS_STEER_FAULT", "EPS_STATUS"),
      ("TORQ_STATUS", "EPS_STATUS"),
      ("COUNTER", "EPS_STATUS"),
      ("TRACTION_OFF", "TRACTION_BUTTON"),
      ("SEATBELT_DRIVER_UNLATCHED", "SEATBELT_STATUS"),
      ("COUNTER", "WHEEL_BUTTONS"),
      ("ACC_RESUME", "WHEEL_BUTTONS"),
      ("ACC_CANCEL", "WHEEL_BUTTONS"),
      ("ACC_SPEED_INC", "WHEEL_BUTTONS"),
      ("ACC_SPEED_DEC", "WHEEL_BUTTONS"),
      ("ACC_FOLLOW_INC", "WHEEL_BUTTONS"),
      ("ACC_FOLLOW_DEC", "WHEEL_BUTTONS"),
      ("ACC_DISTANCE_CONFIG_2", "DASHBOARD"),
      ("TOGGLE_LKAS", "TRACTION_BUTTON"),
      ("VEHICLE_SPEED_KPH", "BRAKE_1"),
      ("BRAKE_VAL_TOTAL", "BRAKE_1"),
      ("ACCEL", "ACCEL_RELATED_120"),
    ]

    checks = [
      # sig_address, frequency
      ("BRAKE_2", 50),
      ("EPS_STATUS", 100),
      ("SPEED_1", 100),
      ("WHEEL_SPEEDS", 50),
      ("STEERING", 100),
      ("ACC_2", 50),
      ("GEAR", 50),
      ("ACCEL_GAS_134", 50),
      ("WHEEL_BUTTONS", 50),
      ("DASHBOARD", 15),
      ("STEERING_LEVERS", 10),
      ("SEATBELT_STATUS", 2),
      ("DOORS", 1),
      ("TRACTION_BUTTON", 1),
      ("BRAKE_1", 100),
      ("ACCEL_RELATED_120", 50)
    ]

    if CP.enableBsm:
      signals += [
        ("BLIND_SPOT_RIGHT", "BLIND_SPOT_WARNINGS"),
        ("BLIND_SPOT_LEFT", "BLIND_SPOT_WARNINGS"),
      ]
      checks.append(("BLIND_SPOT_WARNINGS", 2))

    return CANParser(DBC[CP.carFingerprint]["pt"], signals, checks, 0)

  @staticmethod
  def get_cam_can_parser(CP):
    # LKAS_HEARTBIT data needs to be forwarded!
    forward_lkas_heartbit_signals = [
      ("AUTO_HIGH_BEAM", "LKAS_HEARTBIT"),
      ("FORWARD_1", "LKAS_HEARTBIT"),
      ("FORWARD_2", "LKAS_HEARTBIT"),
      ("FORWARD_3", "LKAS_HEARTBIT"),
    ]

    signals = [
      # sig_name, sig_address
      ("COUNTER", "LKAS_COMMAND"),
      ("CAR_MODEL", "LKAS_HUD"),
      ("LKAS_LANE_LINES", "LKAS_HUD"),
    ] + forward_lkas_heartbit_signals
    checks = [
      ("LKAS_COMMAND", 100),
      ("LKAS_HUD", 4),
      ("LKAS_HEARTBIT", 10),
    ]

    return CANParser(DBC[CP.carFingerprint]["pt"], signals, checks, 2)