from opendbc.can import CANDefine, CANParser
from cereal import car
from opendbc.car import Bus, create_button_events, structs
from opendbc.car.chrysler.values import DBC, STEER_THRESHOLD, HYBRID_CARS, RAM_CARS
from opendbc.car.common.conversions import Conversions as CV
from opendbc.car.interfaces import CarStateBase

import numpy as np
from openpilot.common.params import Params
from openpilot.common.cached_params import CachedParams
from opendbc.car.interfaces import FORWARD_GEARS

ButtonType = structs.CarState.ButtonEvent.Type

CHECK_BUTTONS = {ButtonType.cancel: ["CRUISE_BUTTONS", 'ACC_Cancel'],
                 ButtonType.resumeCruise: ["CRUISE_BUTTONS", 'ACC_Resume'],
                 ButtonType.accelCruise: ["CRUISE_BUTTONS", 'ACC_Accel'],
                 ButtonType.decelCruise: ["CRUISE_BUTTONS", 'ACC_Decel'],
                 ButtonType.followInc: ["CRUISE_BUTTONS", 'ACC_Distance_Inc'],
                 ButtonType.followDec: ["CRUISE_BUTTONS", 'ACC_Distance_Dec'],
                 ButtonType.lkasToggle: ["TRACTION_BUTTON", 'TOGGLE_LKAS']}

PEDAL_GAS_PRESSED_XP = [0, 32, 255]
PEDAL_BRAKE_PRESSED_XP = [0, 24, 255]
PEDAL_PRESSED_YP = [0, 128, 255]

class CarState(CarStateBase):
  def __init__(self, CP):
    super().__init__(CP)
    self.CP = CP
    can_define = CANDefine(DBC[CP.carFingerprint][Bus.pt])

    self.auto_high_beam = 0
    self.button_counter = 0
    self.lkas_car_model = -1

    if CP.carFingerprint in RAM_CARS:
      self.shifter_values = can_define.dv["Transmission_Status"]["Gear_State"]
    else:
      self.shifter_values = can_define.dv["GEAR"]["PRNDL"]

    #self.distance_button = 0

    self.settingsParams = Params()
    self.lkasHeartbit = None
    self.lkas_disabled = self.settingsParams.get_bool("jvePilot.carstate.lkasDisabled")
    self.auto_follow = self.settingsParams.get_bool("jvePilot.settings.autoFollow")

    # long control
    self.longControl = False
    self.cachedParams = CachedParams()
    self.das_3 = None
    self.das_5 = None
    self.longEnabled = False
    self.longControl = False
    self.gasRpm = None
    self.allowLong = True # CP.carFingerprint in (CAR.JEEP_CHEROKEE, CAR.JEEP_CHEROKEE_2019)
    self.torqMin = None
    self.torqMax = None
    self.wheelTorqMin = None
    self.wheelTorqMax = None
    self.transmission_gear = None
    self.engine_torque = None
    self.cruise_enabled = False
    self.brake_hold = False
    self.acc_accelerating = False
    self.acc_decelerating = False
    self.cruise_active_actual = False
    self.forward_gear = False

  def update(self, can_parsers) -> structs.CarState:
    cp = can_parsers[Bus.pt]
    cp_cam = can_parsers[Bus.cam]

    ret = structs.CarState()

    # prev_distance_button = self.distance_butto
    # self.distance_button = cp.vl["CRUISE_BUTTONS"]["ACC_Distance_Dec"]

    button_events = []
    for buttonType in CHECK_BUTTONS:
      self.check_button(button_events, buttonType, bool(cp.vl[CHECK_BUTTONS[buttonType][0]][CHECK_BUTTONS[buttonType][1]]))
    ret.buttonEvents = button_events

    # lock info
    ret.doorOpen = any([cp.vl["BCM_1"]["DOOR_OPEN_FL"],
                        cp.vl["BCM_1"]["DOOR_OPEN_FR"],
                        cp.vl["BCM_1"]["DOOR_OPEN_RL"],
                        cp.vl["BCM_1"]["DOOR_OPEN_RR"]])
    ret.seatbeltUnlatched = cp.vl["ORC_1"]["SEATBELT_DRIVER_UNLATCHED"] == 1

    # brake pedal
    ret.brake = 0
    ret.brakePressed = cp.vl["ESP_1"]['Brake_Pedal_State'] == 1  # Physical brake pedal switch

    # gas pedal
    ret.gasPressed = cp.vl["ECM_5"]["Accelerator_Position"] > 1e-5

    # car speed
    if self.CP.carFingerprint in RAM_CARS:
      ret.vEgoRaw = cp.vl["ESP_8"]["Vehicle_Speed"] * CV.KPH_TO_MS
      ret.gearShifter = self.parse_gear_shifter(self.shifter_values.get(cp.vl["Transmission_Status"]["Gear_State"], None))
    else:
      ret.vEgoRaw = cp.vl["ESP_8"]["Vehicle_Speed"] * CV.KPH_TO_MS
      ret.gearShifter = self.parse_gear_shifter(self.shifter_values.get(cp.vl["GEAR"]["PRNDL"], None))
    self.forward_gear = ret.gearShifter in FORWARD_GEARS

    ret.vEgoRaw = cp.vl["ESP_8"]["Vehicle_Speed"] * CV.KPH_TO_MS
    ret.vEgo, ret.aEgo = self.update_speed_kf(ret.vEgoRaw)
    ret.standstill = not ret.vEgoRaw > 0.001

    # button presses
    ret.leftBlinker, ret.rightBlinker = self.update_blinker_from_stalk(200, cp.vl["STEERING_LEVERS"]["TURN_SIGNALS"] == 1,
                                                                       cp.vl["STEERING_LEVERS"]["TURN_SIGNALS"] == 2)
    ret.genericToggle = cp.vl["STEERING_LEVERS"]["HIGH_BEAM_PRESSED"] == 1

    # steering wheel
    ret.steeringAngleDeg = cp.vl["STEERING"]["STEERING_ANGLE"] + cp.vl["STEERING"]["STEERING_ANGLE_HP"]
    ret.steeringRateDeg = cp.vl["STEERING"]["STEERING_RATE"]
    ret.steeringTorque = cp.vl["EPS_2"]["COLUMN_TORQUE"]
    ret.steeringTorqueEps = cp.vl["EPS_2"]["EPS_TORQUE_MOTOR"]
    ret.steeringPressed = abs(ret.steeringTorque) > STEER_THRESHOLD

    # cruise state
    cp_cruise = cp_cam if self.CP.carFingerprint in RAM_CARS else cp

    self.longControl = (self.CP.alphaLongitudinalAvailable and cp.vl["DAS_4"]["ACC_STATE"] == 0
                        and self.cachedParams.get_bool('AlphaLongitudinalEnabled', 1000))
    if self.longControl:
      ret.jvePilotCarState.longControl = True
      ret.cruiseState.enabled = self.longEnabled
      ret.cruiseState.available = True
      ret.cruiseState.nonAdaptive = False
      ret.cruiseState.standstill = False
      ret.accFaulted = False
      self.torqMin = cp_cruise.vl["DAS_3"]["ENGINE_TORQUE_REQUEST"]
      self.torqMax = cp_cruise.vl["ECM_TRQ"]["ENGINE_TORQ_MAX"]
      self.transmission_gear = int(cp_cruise.vl['TCM_A7']["CurrentGear"])
      self.gasRpm = cp_cruise.vl["ECM_1"]["ENGINE_RPM"]
      self.engine_torque = cp_cruise.vl["ECM_1"]["ENGINE_TORQUE"]
      if self.CP.carFingerprint in HYBRID_CARS:
        self.wheelTorqMin = cp_cruise.vl["AXLE_TORQ"]["AXLE_TORQ_MIN"]
        self.wheelTorqMax = cp_cruise.vl["AXLE_TORQ"]["AXLE_TORQ_MAX"]
    else:
      self.longEnabled = False
      ret.jvePilotCarState.longControl = False
      ret.cruiseState.available = cp_cruise.vl["DAS_3"]["ACC_AVAILABLE"] == 1
      ret.cruiseState.enabled = cp_cruise.vl["DAS_3"]["ACC_ACTIVE"] == 1
      ret.cruiseState.speed = cp_cruise.vl["DAS_4"]["ACC_SET_SPEED_KPH"] * CV.KPH_TO_MS
      ret.cruiseState.nonAdaptive = cp_cruise.vl["DAS_4"]["ACC_STATE"] in (1, 2)  # 1 NormalCCOn and 2 NormalCCSet
      ret.cruiseState.standstill = cp_cruise.vl["DAS_3"]["ACC_STANDSTILL"] == 1
      ret.accFaulted = cp_cruise.vl["DAS_3"]["ACC_FAULTED"] != 0
      if not ret.cruiseState.enabled and ret.standstill and self.forward_gear and self.brake_hold:
        ret.cruiseState.enabled = ret.cruiseState.available # stay enabled
        ret.cruiseState.standstill = True # we want to resume

    self.das_3 = cp_cruise.vl['DAS_3']
    self.acc_accelerating = self.das_3["ENGINE_TORQUE_REQUEST_MAX"] == 1
    self.acc_decelerating = self.das_3["ACC_DECEL_REQ"] == 1
    self.cruise_active_actual = self.das_3["ACC_ACTIVE"] == 1

    self.das_5 = cp.vl['DAS_5']
    self.lkasHeartbit = cp_cam.vl["LKAS_HEARTBIT"]
    self.cruise_enabled = ret.cruiseState.enabled

    if self.CP.carFingerprint in RAM_CARS:
      # Auto High Beam isn't Located in this message on chrysler or jeep currently located in 729 message
      self.auto_high_beam = cp_cam.vl["DAS_6"]['AUTO_HIGH_BEAM_ON']
      ret.steerFaultTemporary = cp.vl["EPS_3"]["DASM_FAULT"] == 1
    else:
      if abs(ret.steeringAngleDeg) > 200:
        self.above_steer_angle_alert = (self.CP.minSteerSpeed < 0.)
      elif abs(ret.steeringAngleDeg) < 180:
        self.above_steer_angle_alert = False

      backward = cp.vl["ESP_6"]["MOVING_FORWARD"] == 0 and ret.vEgoRaw > 0
      ret.steerFaultTemporary = cp.vl["EPS_2"]["LKAS_TEMPORARY_FAULT"] == 1 or cp.vl["EPS_2"]["LKAS_STATE"] == 12 or self.above_steer_angle_alert or backward
      ret.steerFaultPermanent = cp.vl["EPS_2"]["LKAS_STATE"] == 4

    # blindspot sensors
    if self.CP.enableBsm:
      ret.leftBlindspot = cp.vl["BSM_1"]["LEFT_STATUS"] == 1
      ret.rightBlindspot = cp.vl["BSM_1"]["RIGHT_STATUS"] == 1

    self.lkas_car_model = cp_cam.vl["DAS_6"]["CAR_MODEL"]
    self.button_counter = cp.vl["CRUISE_BUTTONS"]["COUNTER"]

    # ret.buttonEvents = create_button_events(self.distance_button, prev_distance_button, {1: ButtonType.gapAdjustCruise})

    brake = cp.vl["ESP_8"]["BRK_PRESSURE"]
    gas = cp.vl["ECM_2"]["ACCEL"]
    if brake > 0:
      ret.jvePilotCarState.pedalPressedAmount = float(np.interp(brake / 16, PEDAL_BRAKE_PRESSED_XP, PEDAL_PRESSED_YP)) / -256
    elif gas > 0:
      ret.jvePilotCarState.pedalPressedAmount = float(np.interp(gas, PEDAL_GAS_PRESSED_XP, PEDAL_PRESSED_YP)) / 256
    else:
      ret.jvePilotCarState.pedalPressedAmount = 0

    ret.jvePilotCarState.accFollowDistance = int(min(3, max(0, cp.vl["DAS_4"]['ACC_DISTANCE_CONFIG_2'])))
    ret.jvePilotCarState.autoFollow = self.auto_follow
    ret.jvePilotCarState.lkasDisabled = self.lkas_disabled
    ret.jvePilotCarState.aolcReady = self.cachedParams.get_bool('jvePilot.settings.steer.aolc',1000) \
                                     and ret.cruiseState.available and self.forward_gear

    return ret

  def check_button(self, button_events, button_type, pressed):
    pressed_frames = 0
    pressed_changed = False
    cruise_enabled_when_pressed = self.cruise_enabled
    for ob in self.out.buttonEvents:
      if ob.type == button_type:
        pressed_frames = ob.pressedFrames
        pressed_changed = ob.pressed != pressed
        cruise_enabled_when_pressed = ob.cruiseEnabledWhenPressed
        break

    if pressed or pressed_changed:
      if not pressed_changed:
        pressed_frames += 1
      button_events.append(car.CarState.ButtonEvent(pressed=pressed, type=button_type, pressedFrames=pressed_frames, cruiseEnabledWhenPressed=cruise_enabled_when_pressed))

  @staticmethod
  def get_can_parsers(CP):
    return {
      Bus.pt: CANParser(DBC[CP.carFingerprint][Bus.pt], [], 0),
      Bus.cam: CANParser(DBC[CP.carFingerprint][Bus.pt], [], 2),
    }
