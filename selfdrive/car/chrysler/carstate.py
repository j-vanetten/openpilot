from cereal import car
from opendbc.can.parser import CANParser
from opendbc.can.can_define import CANDefine
from selfdrive.config import Conversions as CV
from selfdrive.car.interfaces import CarStateBase
from selfdrive.car.chrysler.values import DBC, STEER_THRESHOLD
from common.cached_params import CachedParams

ButtonType = car.CarState.ButtonEvent.Type

LEAD_RADAR_CONFIG = ['jvePilot.settings.accFollow1RadarRatio',
                     'jvePilot.settings.accFollow2RadarRatio',
                     'jvePilot.settings.accFollow3RadarRatio',
                     'jvePilot.settings.accFollow4RadarRatio']
CHECK_BUTTONS = {ButtonType.cancel: 'ACC_CANCEL',
                 ButtonType.resumeCruise: 'ACC_RESUME',
                 ButtonType.accelCruise: 'ACC_SPEED_INC',
                 ButtonType.decelCruise: 'ACC_SPEED_DEC',
                 ButtonType.followInc: 'ACC_FOLLOW_INC',
                 ButtonType.followDec: 'ACC_FOLLOW_DEC'}

class CarState(CarStateBase):
  def __init__(self, CP):
    super().__init__(CP)
    self.cachedParams = CachedParams()
    can_define = CANDefine(DBC[CP.carFingerprint]['pt'])
    self.shifter_values = can_define.dv["GEAR"]['PRNDL']

  def update(self, cp, cp_cam):
    speed_adjust_ratio = self.cachedParams.get_float('jvePilot.settings.speedAdjustRatio', 5000)
    steer_zero_disabled = (self.cachedParams.get('jvePilot.settings.enableSteerToZero', 5000) != "1")
    inverse_speed_adjust_ratio = 2 - speed_adjust_ratio

    ret = car.CarState.new_message()

    self.frame = int(cp.vl["EPS_STATUS"]['COUNTER'])

    ret.doorOpen = any([cp.vl["DOORS"]['DOOR_OPEN_FL'],
                        cp.vl["DOORS"]['DOOR_OPEN_FR'],
                        cp.vl["DOORS"]['DOOR_OPEN_RL'],
                        cp.vl["DOORS"]['DOOR_OPEN_RR']])
    ret.seatbeltUnlatched = cp.vl["SEATBELT_STATUS"]['SEATBELT_DRIVER_UNLATCHED'] == 1

    ret.brakePressed = cp.vl["BRAKE_2"]['BRAKE_PRESSED_2'] == 5  # human-only
    ret.brake = 0
    ret.brakeLights = ret.brakePressed
    ret.gas = cp.vl["ACCEL_GAS_134"]['ACCEL_134']
    ret.gasPressed = ret.gas > 1e-5

    ret.espDisabled = (cp.vl["TRACTION_BUTTON"]['TRACTION_OFF'] == 1)

    ret.wheelSpeeds.fl = cp.vl['WHEEL_SPEEDS']['WHEEL_SPEED_FL']
    ret.wheelSpeeds.rr = cp.vl['WHEEL_SPEEDS']['WHEEL_SPEED_RR']
    ret.wheelSpeeds.rl = cp.vl['WHEEL_SPEEDS']['WHEEL_SPEED_RL']
    ret.wheelSpeeds.fr = cp.vl['WHEEL_SPEEDS']['WHEEL_SPEED_FR']
    ret.vEgoRaw = (cp.vl['SPEED_1']['SPEED_LEFT'] + cp.vl['SPEED_1']['SPEED_RIGHT']) / 2. * speed_adjust_ratio
    ret.vEgo, ret.aEgo = self.update_speed_kf(ret.vEgoRaw)
    ret.standstill = ret.vEgoRaw <= 0.1

    ret.leftBlindspot = cp.vl["BLIND_SPOT_WARNINGS"]['BLIND_SPOT_LEFT'] == 1
    ret.rightBlindspot = cp.vl["BLIND_SPOT_WARNINGS"]['BLIND_SPOT_RIGHT'] == 1
    ret.leftBlinker = cp.vl["STEERING_LEVERS"]['TURN_SIGNALS'] == 1
    ret.rightBlinker = cp.vl["STEERING_LEVERS"]['TURN_SIGNALS'] == 2
    ret.steeringAngleDeg = cp.vl["STEERING"]['STEER_ANGLE']
    ret.steeringRateDeg = cp.vl["STEERING"]['STEERING_RATE']
    ret.gearShifter = self.parse_gear_shifter(self.shifter_values.get(cp.vl['GEAR']['PRNDL'], None))

    ret.cruiseState.enabled = cp.vl["ACC_2"]['ACC_STATUS_2'] == 7  # ACC is green.
    ret.cruiseState.available = cp.vl["DASHBOARD"]['CRUISE_STATE'] in [3, 4]  # the comment below says 3 and 4 are ACC mode
    ret.cruiseState.speed = cp.vl["DASHBOARD"]['ACC_SPEED_CONFIG_KPH'] * CV.KPH_TO_MS
    # CRUISE_STATE is a three bit msg, 0 is off, 1 and 2 are Non-ACC mode, 3 and 4 are ACC mode, find if there are other states too
    ret.cruiseState.nonAdaptive = cp.vl["DASHBOARD"]['CRUISE_STATE'] in [1, 2]

    ret.steeringTorque = cp.vl["EPS_STATUS"]["TORQUE_DRIVER"]
    ret.steeringTorqueEps = cp.vl["EPS_STATUS"]["TORQUE_MOTOR"]
    ret.steeringPressed = abs(ret.steeringTorque) > STEER_THRESHOLD
    steer_state = cp.vl["EPS_STATUS"]["LKAS_STATE"]
    ret.steerError = steer_state == 4 or (steer_state == 0 and (ret.vEgo > self.CP.minSteerSpeed and steer_zero_disabled))

    ret.genericToggle = bool(cp.vl["STEERING_LEVERS"]['HIGH_BEAM_FLASH'])
    
    if self.CP.enableBsm:
      ret.leftBlindspot = cp.vl["BLIND_SPOT_WARNINGS"]['BLIND_SPOT_LEFT'] == 1
      ret.rightBlindspot = cp.vl["BLIND_SPOT_WARNINGS"]['BLIND_SPOT_RIGHT'] == 1

    self.lkas_counter = cp_cam.vl["LKAS_COMMAND"]['COUNTER']
    self.lkas_car_model = cp_cam.vl["LKAS_HUD"]['CAR_MODEL']
    self.lkas_status_ok = cp_cam.vl["LKAS_HEARTBIT"]['LKAS_STATUS_OK']

    ret.jvePilotCarState.accFollowDistance = int(min(3, max(0, cp.vl["DASHBOARD"]['ACC_DISTANCE_CONFIG_2'])))
    ret.jvePilotCarState.leadDistanceRadarRatio = self.cachedParams.get_float(LEAD_RADAR_CONFIG[ret.jvePilotCarState.accFollowDistance], 1000) * inverse_speed_adjust_ratio
    ret.jvePilotCarState.buttonCounter = int(cp.vl["WHEEL_BUTTONS"]['COUNTER'])

    button_events = []
    for buttonType in CHECK_BUTTONS:
      self.check_button(button_events, buttonType, bool(cp.vl["WHEEL_BUTTONS"][CHECK_BUTTONS[buttonType]]))
    ret.buttonEvents = button_events

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
      ("PRNDL", "GEAR", 0),
      ("DOOR_OPEN_FL", "DOORS", 0),
      ("DOOR_OPEN_FR", "DOORS", 0),
      ("DOOR_OPEN_RL", "DOORS", 0),
      ("DOOR_OPEN_RR", "DOORS", 0),
      ("BRAKE_PRESSED_2", "BRAKE_2", 0),
      ("ACCEL_134", "ACCEL_GAS_134", 0),
      ("SPEED_LEFT", "SPEED_1", 0),
      ("SPEED_RIGHT", "SPEED_1", 0),
      ("WHEEL_SPEED_FL", "WHEEL_SPEEDS", 0),
      ("WHEEL_SPEED_RR", "WHEEL_SPEEDS", 0),
      ("WHEEL_SPEED_RL", "WHEEL_SPEEDS", 0),
      ("WHEEL_SPEED_FR", "WHEEL_SPEEDS", 0),
      ("STEER_ANGLE", "STEERING", 0),
      ("STEERING_RATE", "STEERING", 0),
      ("TURN_SIGNALS", "STEERING_LEVERS", 0),
      ("ACC_STATUS_2", "ACC_2", 0),
      ("HIGH_BEAM_FLASH", "STEERING_LEVERS", 0),
      ("ACC_SPEED_CONFIG_KPH", "DASHBOARD", 0),
      ("CRUISE_STATE", "DASHBOARD", 0),
      ("TORQUE_DRIVER", "EPS_STATUS", 0),
      ("TORQUE_MOTOR", "EPS_STATUS", 0),
      ("LKAS_STATE", "EPS_STATUS", 1),
      ("COUNTER", "EPS_STATUS", -1),
      ("TRACTION_OFF", "TRACTION_BUTTON", 0),
      ("SEATBELT_DRIVER_UNLATCHED", "SEATBELT_STATUS", 0),
      ("COUNTER", "WHEEL_BUTTONS", -1),
      ("ACC_RESUME", "WHEEL_BUTTONS", 0),
      ("ACC_CANCEL", "WHEEL_BUTTONS", 0),
      ("ACC_SPEED_INC", "WHEEL_BUTTONS", 0),
      ("ACC_SPEED_DEC", "WHEEL_BUTTONS", 0),
      ("ACC_FOLLOW_INC", "WHEEL_BUTTONS", 0),
      ("ACC_FOLLOW_DEC", "WHEEL_BUTTONS", 0),
      ("ACC_DISTANCE_CONFIG_2", "DASHBOARD", 0),
      ("BLIND_SPOT_LEFT", "BLIND_SPOT_WARNINGS", 0),
      ("BLIND_SPOT_RIGHT", "BLIND_SPOT_WARNINGS", 0),
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
      ("WHEEL_BUTTONS", 50),
      ("ACCEL_GAS_134", 50),
      ("DASHBOARD", 15),
      ("STEERING_LEVERS", 10),
      ("SEATBELT_STATUS", 2),
      ("DOORS", 1),
      ("TRACTION_BUTTON", 1),
      ("BLIND_SPOT_WARNINGS", 2),
    ]

    if CP.enableBsm:
      signals += [
        ("BLIND_SPOT_RIGHT", "BLIND_SPOT_WARNINGS", 0),
        ("BLIND_SPOT_LEFT", "BLIND_SPOT_WARNINGS", 0),
      ]
      checks += [("BLIND_SPOT_WARNINGS", 2)]

    return CANParser(DBC[CP.carFingerprint]['pt'], signals, checks, 0)

  @staticmethod
  def get_cam_can_parser(CP):
    signals = [
      # sig_name, sig_address, default
      ("COUNTER", "LKAS_COMMAND", -1),
      ("CAR_MODEL", "LKAS_HUD", -1),
      ("LKAS_STATUS_OK", "LKAS_HEARTBIT", -1)
    ]
    checks = [
      ("LKAS_COMMAND", 100),
      ("LKAS_HEARTBIT", 10),
      ("LKAS_HUD", 4),
    ]

    return CANParser(DBC[CP.carFingerprint]['pt'], signals, checks, 2)
