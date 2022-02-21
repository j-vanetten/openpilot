from cereal import car
from opendbc.can.parser import CANParser
from opendbc.can.can_define import CANDefine
from selfdrive.config import Conversions as CV
from selfdrive.car.interfaces import CarStateBase
from selfdrive.car.chrysler.values import DBC, STEER_THRESHOLD, CAR
from common.cached_params import CachedParams
from common.params import Params
from common.op_params import opParams
import numpy as np

ButtonType = car.CarState.ButtonEvent.Type

CHECK_BUTTONS = {ButtonType.cancel: ["Cruise_Control_Buttons", 'ACC_Cancel'],
                 ButtonType.resumeCruise: ["Cruise_Control_Buttons", 'ACC_Resume'],
                 ButtonType.accelCruise: ["Cruise_Control_Buttons", 'ACC_Accel'],
                 ButtonType.decelCruise: ["Cruise_Control_Buttons", 'ACC_Decel'],
                 ButtonType.followInc: ["Cruise_Control_Buttons", 'ACC_Distance_Inc'],
                 ButtonType.followDec: ["Cruise_Control_Buttons", 'ACC_Distance_Dec'],
                 ButtonType.lkasToggle: ["Center_Stack_2", 'LKAS_Button']}

PEDAL_GAS_PRESSED_XP = [0, 32, 255]
PEDAL_BRAKE_PRESSED_XP = [0, 24, 255]
PEDAL_PRESSED_YP = [0, 128, 255]

class CarState(CarStateBase):
  def __init__(self, CP):
    super().__init__(CP)
    can_define = CANDefine(DBC[CP.carFingerprint]["pt"])
    self.shifter_values = can_define.dv["Transmission_Status"]["Gear_State"]
    self.cachedParams = CachedParams()
    self.opParams = opParams()
    #self.lkasHeartbit = None
    self.dashboard = None
    self.speedRequested = 0
    self.acc_2 = None
    self.gasRpm = None
    self.longEnabled = False
    self.longControl = False
    self.hybrid = CP.carFingerprint in (CAR.PACIFICA_2017_HYBRID, CAR.PACIFICA_2018_HYBRID, CAR.PACIFICA_2019_HYBRID)

  def update(self, cp, cp_cam):
    min_steer_check = self.opParams.get('steer.checkMinimum')

    ret = car.CarState.new_message()

    # lock info 
    ret.doorOpen = any([cp.vl["BCM_1"]["Driver_Door_Ajar"],
                        cp.vl["BCM_1"]["Passenger_Door_Ajar"],
                        cp.vl["BCM_1"]["Left_Rear_Door_Ajar"],
                        cp.vl["BCM_1"]["Right_Rear_Door_Ajar"]])
    ret.seatbeltUnlatched = cp.vl["ORC_1"]['Driver_Seatbelt_Status'] == 1 #1 is unbuckled

    # brake pedal
    ret.brakePressed = cp.vl["ESP_1"]['Brake_Pedal_State'] ==1  # Physical brake pedal switch
    ret.brake = 0

    # gas pedal
    ret.gas = cp.vl["ECM_5"]["Accelerator_Position"]
    ret.gasPressed = ret.gas > 45 # up from 5

    ret.espDisabled = (cp.vl["Center_Stack_1"]["Traction_Button"] == 1) #button is pressed. This doesn't mean ESP is diabled.

    # car speed
    ret.vEgoRaw = cp.vl["ESP_8"]["Vehicle_Speed"] * CV.KPH_TO_MS
    ret.vEgo, ret.aEgo = self.update_speed_kf(ret.vEgoRaw)
    ret.standstill = not ret.vEgoRaw > 0.001
    ret.wheelSpeeds = self.get_wheel_speeds(
    cp.vl["ESP_6"]["Wheel_RPM_Front_Left"],
    cp.vl["ESP_6"]["Wheel_RPM_Rear_Right"],
    cp.vl["ESP_6"]["Wheel_RPM_Rear_Left"],
    cp.vl["ESP_6"]["Wheel_RPM_Front_Right"],
    unit=1,
    )
    ret.standstill = ret.vEgoRaw <= 0.1

    # button presses
    ret.leftBlinker = (cp.vl["Steering_Column_Commands"]["Turn_Signal_Status"] == 1)
    ret.rightBlinker = (cp.vl["Steering_Column_Commands"]["Turn_Signal_Status"] == 2)
    ret.genericToggle = bool(cp.vl["Steering_Column_Commands"]["High_Beam_Lever_Status"])


    # steering wheel  
    ret.steeringAngleDeg = cp.vl["Steering_Column_Angle_Status"]["Steering_Wheel_Angle"]
    ret.steeringRateDeg = cp.vl["Steering_Column_Angle_Status"]["Steering_Rate"]
    ret.steeringTorque = cp.vl["EPS_2"]["Steering_Column_Torque"]
    ret.steeringTorqueEps = cp.vl["EPS_2"]["EPS_Motor_Torque"]
    ret.steeringPressed = abs(ret.steeringTorque) > STEER_THRESHOLD
    self.frame = int(cp.vl["EPS_2"]["COUNTER"])

    # gear
    ret.gearShifter = self.parse_gear_shifter(self.shifter_values.get(cp.vl["Transmission_Status"]["Gear_State"], None))

    self.longControl = cp_cam.vl["DAS_4"]['ACC_Activation_Status'] == 0 and self.cachedParams.get_bool('jvePilot.settings.longControl', 1000)
    if self.longControl:
      ret.cruiseState.enabled = self.longEnabled
      ret.cruiseState.available = True
      ret.cruiseState.nonAdaptive = False
      if self.hybrid:
        self.acc_1 = cp.vl["ACC_1"]
        self.torqMin = cp.vl["AXLE_TORQ"]["AXLE_TORQ_MIN"]
        self.torqMax = cp.vl["AXLE_TORQ"]["AXLE_TORQ_MAX"]
      else:
        self.torqMax = cp.vl["AXLE_TORQ_ICE"]["AXLE_TORQ_MAX"]
        if self.CP.carFingerprint in (CAR.PACIFICA_2017_HYBRID, CAR.PACIFICA_2018_HYBRID, CAR.PACIFICA_2019_HYBRID, CAR.PACIFICA_2018, CAR.PACIFICA_2020, CAR.JEEP_CHEROKEE_2019, CAR.JEEP_CHEROKEE):
          self.torqMin = cp.vl["DAS_3"]["ACC_TORQ"]
        if self.CP.carFingerprint in (CAR.RAM_1500, CAR.RAM_2500):
          self.torqMin = cp_cam.vl["DAS_3"]["ACC_TORQ"]
    else:
      if self.CP.carFingerprint in (CAR.PACIFICA_2017_HYBRID, CAR.PACIFICA_2018_HYBRID, CAR.PACIFICA_2019_HYBRID, CAR.PACIFICA_2018, CAR.PACIFICA_2020, CAR.JEEP_CHEROKEE_2019, CAR.JEEP_CHEROKEE):
        ret.cruiseState.enabled = cp.vl["DAS_3"]["ACC_Engaged"] == 1 # and self.lkasdisabled == 0 # ACC is green.
        ret.cruiseState.standstill = cp.vl["DAS_3"]["ACC_STOP"] == 1
        # ACC_Activation_Status is a three bit msg, 0 is off, 1 and 2 are Non-ACC mode, 3 and 4 are ACC mode
        ret.cruiseState.available = cp.vl["DAS_4"]['ACC_Activation_Status'] in [3, 4]  #3 ACCOn and 4 ACCSet
        ret.cruiseState.nonAdaptive = cp.vl["DAS_4"]["ACC_Activation_Status"] in (1, 2) #1 NormalCCOn and 2 NormalCCSet
        #ret.cruiseState.speedOffset = ret.cruiseState.speed - ret.vEgo        
      
      if self.CP.carFingerprint in (CAR.RAM_1500, CAR.RAM_2500):
        ret.cruiseState.enabled = cp_cam.vl["DAS_3"]["ACC_Engaged"] == 1 #  and self.lkasdisabled == 0 # ACC is green.
        ret.cruiseState.standstill = cp_cam.vl["DAS_3"]["ACC_STOP"] == 1
        # ACC_Activation_Status is a three bit msg, 0 is off, 1 and 2 are Non-ACC mode, 3 and 4 are ACC mode
        ret.cruiseState.available = cp_cam.vl["DAS_4"]['ACC_Activation_Status'] in [3, 4]  #3 ACCOn and 4 ACCSet
        ret.cruiseState.nonAdaptive = cp_cam.vl["DAS_4"]["ACC_Activation_Status"] in [1, 2] #1 NormalCCOn and 2 NormalCCSet
        #ret.cruiseState.speedOffset = ret.cruiseState.speed - ret.vEgo   
  
      self.longEnabled = False

    if self.CP.carFingerprint in (CAR.PACIFICA_2017_HYBRID, CAR.PACIFICA_2018_HYBRID, CAR.PACIFICA_2019_HYBRID, CAR.PACIFICA_2018, CAR.PACIFICA_2020, CAR.JEEP_CHEROKEE_2019, CAR.JEEP_CHEROKEE):
      self.cruise_error = cp.vl["DAS_3"]["Status"] != 0
      ret.cruiseState.speed = cp.vl["DAS_4"]["ACC_Set_Speed"] * CV.KPH_TO_MS
      self.dashboard = cp.vl["DAS_4"]
      self.steer_state = cp.vl["EPS_2"]["Torque_Overlay_Status"]
      ret.steerError = self.steer_state == 4 or (min_steer_check and not self.lkas_active and ret.vEgo > self.CP.minSteerSpeed)
      self.lkasbutton = (cp.vl["Center_Stack_1"]["LKAS_Button"] == 1)
      self.acc_2 = cp.vl['DAS_3']
      ret.jvePilotCarState.accFollowDistance = int(min(3, max(0, cp.vl["DAS_4"]['ACC_DISTANCE_CONFIG_2'])))
    
    if self.CP.carFingerprint in (CAR.RAM_1500, CAR.RAM_2500):
      self.cruise_error = cp_cam.vl["DAS_3"]["Status"] != 0
      ret.cruiseState.speed = cp_cam.vl["DAS_4"]["ACC_Set_Speed"] * CV.KPH_TO_MS
      self.dashboard = cp_cam.vl["DAS_4"]
      ret.steerError = False #cp_cam.vl["LKAS_COMMAND"]["LKAS_ERROR"]==1 # TODO: Find another bit to determine the steer error
      self.autoHighBeamBit = cp_cam.vl["DAS_6"]['Auto_High_Beam'] #Auto High Beam isn't Located in this message on chrysler or jeep currently located in 729 message
      self.lkasbutton = (cp.vl["Center_Stack_2"]["LKAS_Button"] == 1)
      self.acc_2 = cp_cam.vl['DAS_3']
      ret.jvePilotCarState.accFollowDistance = int(min(3, max(0, cp_cam.vl["DAS_4"]['ACC_DISTANCE_CONFIG_2'])))

    self.lkas_active = cp.vl["EPS_2"]["LKAS_ACTIVE"] == 1

    # blindspot sensors
    if self.CP.enableBsm:
      ret.leftBlindspot = cp.vl["BSM_1"]["Blind_Spot_Monitor_Left"] == 1
      ret.rightBlindspot = cp.vl["BSM_1"]["Blind_Spot_Monitor_Right"] == 1    


    self.lkas_counter = cp_cam.vl["DAS_3"]["COUNTER"]
    self.lanelines = cp_cam.vl["DAS_6"]["LKAS_LANE_LINES"]
    self.iconcolor = cp_cam.vl["DAS_6"]["LKAS_ICON_COLOR"]
    self.lkas_car_model = cp_cam.vl["DAS_6"]["CAR_MODEL"] 
    self.lkasalerts = cp_cam.vl["DAS_6"]["LKAS_ALERTS"]


    self.torq_status = cp.vl["EPS_2"]["Torque_Overlay_Status"]
    self.gasRpm = cp.vl["ECM_1"]["Engine_RPM"]
    

    brake = cp.vl["ESP_8"]["BRK_PRESSURE"]
    gas = ret.gas
    if gas > 0:
      ret.jvePilotCarState.pedalPressedAmount = float(np.interp(gas, PEDAL_GAS_PRESSED_XP, PEDAL_PRESSED_YP)) / 256
    elif brake > 0:
      ret.jvePilotCarState.pedalPressedAmount = float(np.interp(brake / 16, PEDAL_BRAKE_PRESSED_XP, PEDAL_PRESSED_YP)) / -256
    else:
      ret.jvePilotCarState.pedalPressedAmount = 0

    
    ret.jvePilotCarState.buttonCounter = int(cp.vl["Cruise_Control_Buttons"]["COUNTER"])
    #self.lkasHeartbit = cp_cam.vl["LKAS_HEARTBIT"]

    button_events = []
    for buttonType in CHECK_BUTTONS:
      self.check_button(button_events, buttonType, bool(cp.vl[CHECK_BUTTONS[buttonType][0]][CHECK_BUTTONS[buttonType][1]]))
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
    hybrid = CP.carFingerprint in (CAR.PACIFICA_2017_HYBRID, CAR.PACIFICA_2018_HYBRID, CAR.PACIFICA_2019_HYBRID)

    signals = [
      # sig_name, sig_address, default
      ("Gear_State", "Transmission_Status",0), #Gear Position
      ("Vehicle_Speed", "ESP_8",0),#Vehicle Speed
      ("BRK_PRESSURE", "ESP_8",0),#Brake Pressure
      ("Acceleration", "ESP_4",0),#Acceleration Rate
      ("Yaw_Rate", "ESP_4",0),#Yaw Rate
      ("Wheel_RPM_Front_Left", "ESP_6",0),#FL Wheel Speed
      ("Wheel_RPM_Front_Right", "ESP_6",0),#FR Wheel Speed
      ("Wheel_RPM_Rear_Left", "ESP_6",0),#RL Wheel Speed
      ("Wheel_RPM_Rear_Right", "ESP_6",0),#RR Wheel Speed
      ("Accelerator_Position", "ECM_5",0), #Accelerator Position
      ("Brake_Pedal_State", "ESP_1",0),#Brake Pedal Pressed
      ("Steering_Wheel_Angle", "Steering_Column_Angle_Status",0),#Steering Angle
      ("Steering_Rate", "Steering_Column_Angle_Status",0),#Steering rate
      ("Steering_Column_Torque", "EPS_2",0),#EPS Driver applied torque
      ("EPS_Motor_Torque", "EPS_2",0),#EPS Motor Torque output
      ("Torque_Overlay_Status", "EPS_2",0),
      ("LKAS_ACTIVE", "EPS_2",0),
      ("Traction_Button", "Center_Stack_1",0),#Traction Control Button
      ("Turn_Signal_Status", "Steering_Column_Commands",0),#Blinker 
      ("High_Beam_Lever_Status", "Steering_Column_Commands",0),#High Beam Lever
      ("ACC_Accel", "Cruise_Control_Buttons",0),#ACC Accel Button
      ("ACC_Decel", "Cruise_Control_Buttons",0),#ACC Decel Button
      ("ACC_Cancel", "Cruise_Control_Buttons",0),#ACC Cancel Button
      ("ACC_Distance_Dec", "Cruise_Control_Buttons",0),#ACC Distance Decrement Button
      ("ACC_Distance_Inc", "Cruise_Control_Buttons",0),#ACC Distance Increment Button
      ("ACC_Resume", "Cruise_Control_Buttons",0),#ACC Resume Button
      ("Cruise_OnOff", "Cruise_Control_Buttons",0),#Cruise On Off Button
      ("ACC_OnOff", "Cruise_Control_Buttons",0),#ACC On Off Button
      ("COUNTER", "Cruise_Control_Buttons",0),#ACC Counter Button
      ("ACC_Distance_Inc", "Cruise_Control_Buttons",0),#ACC Distance Increase Button
      ("Driver_Door_Ajar", "BCM_1",0),#driver Door
      ("Passenger_Door_Ajar", "BCM_1",0),#Passenger Door
      ("Left_Rear_Door_Ajar", "BCM_1",0),#Driver Rear Door
      ("Right_Rear_Door_Ajar", "BCM_1",0),#Passenger Rear Door
      ("Driver_Seatbelt_Status", "ORC_1",0), #Driver Sear Belt
      ("COUNTER", "EPS_2",0),#EPS Counter  
      ("Engine_RPM", "ECM_1", 0),
    ]

    if hybrid:
      signals += [
        ("AXLE_TORQ_MIN", "AXLE_TORQ", 0),
        ("AXLE_TORQ_MAX", "AXLE_TORQ", 0),

        ("COUNTER", "ACC_1", 0),
        ("ACC_TORQ_REQ", "ACC_1", 0),
        ("ACC_TORQ", "ACC_1", 0),
        ("FORWARD_1", "ACC_1", 0),
        ("FORWARD_2", "ACC_1", 0),
        ("FORWARD_3", "ACC_1", 0),
      ]
    else:
      signals += [
        ("AXLE_TORQ_MIN", "AXLE_TORQ_ICE", 0),
        ("AXLE_TORQ_MAX", "AXLE_TORQ_ICE", 0),
      ]

    checks = [
      # sig_address, frequency
      ("Transmission_Status", 50),
      ("ESP_1", 50),
      ("ESP_4", 50),
      ("ESP_6", 50),
      ("ESP_8", 50),
      ("ECM_5", 50),
      ("Steering_Column_Angle_Status", 100),
      ("EPS_2", 100),
      ("Center_Stack_1", 1),
      ("Steering_Column_Commands", 10),
      ("Cruise_Control_Buttons", 50),
      ("BCM_1", 1),
      ("ORC_1", 1),
      ("ECM_1", 50),
    ]

    if hybrid:
      checks += [
        ("AXLE_TORQ", 50),
        ("ACC_1", 50),
      ]
    else:
      checks += [
        ("AXLE_TORQ_ICE", 50),
      ]

    if CP.enableBsm:
      signals += [
        ("Blind_Spot_Monitor_Left", "BSM_1",0),
        ("Blind_Spot_Monitor_Right", "BSM_1",0),
      ]
      checks += [("BSM_1", 2)]

    if CP.carFingerprint in (CAR.PACIFICA_2017_HYBRID, CAR.PACIFICA_2018_HYBRID, CAR.PACIFICA_2019_HYBRID, CAR.PACIFICA_2018, CAR.PACIFICA_2020, CAR.JEEP_CHEROKEE_2019, CAR.JEEP_CHEROKEE):
      signals += [
        ("ACC_Engaged", "DAS_3",0),#ACC Engaged
        ("ACC_STOP", "DAS_3",0),#ACC Engaged
        ("Status", "DAS_3",0),
        ("ACC_TORQ", "DAS_3",0),
        ("ACC_Set_Speed", "DAS_4",0),
        ("ACC_Activation_Status", "DAS_4",0),
        ("ACC_DISTANCE_CONFIG_2", "DAS_4",0),
        ("LKAS_Button", "Center_Stack_1",0),#LKAS Button
      ]
      checks += [
        ("DAS_3", 50),
        ("DAS_4", 50),
        ]

    if CP.carFingerprint in (CAR.RAM_1500, CAR.RAM_2500):
      signals += [
        ("LKAS_Button", "Center_Stack_2",0),#LKAS Button
      ]

      checks += [
        ("Center_Stack_2", 1),
        ]

    return CANParser(DBC[CP.carFingerprint]["pt"], signals, checks, 0)

  @staticmethod
  def get_cam_can_parser(CP):
    # LKAS_HEARTBIT data needs to be forwarded!
    #forward_lkas_heartbit_signals = [
    #    ("AUTO_HIGH_BEAM", "LKAS_HEARTBIT", 0),
    #    ("FORWARD_1", "LKAS_HEARTBIT", 0),
    #    ("FORWARD_2", "LKAS_HEARTBIT", 0),
    #    ("FORWARD_3", "LKAS_HEARTBIT", 0),
    #]

    signals = [
      # sig_name, sig_address, default
      ("LKAS_LANE_LINES", "DAS_6",0),
      ("LKAS_ICON_COLOR", "DAS_6",0),
      ("LKAS_Disabled", "DAS_6",0),
      ("CAR_MODEL", "DAS_6",0),
      ("LKAS_ALERTS", "DAS_6",0),
    ]# + forward_lkas_heartbit_signals

    checks = [
      ("DAS_6", 15),
      #("LKAS_HEARTBIT", 10),
    ]

    if CP.carFingerprint in (CAR.RAM_1500, CAR.RAM_2500):
      signals += [
        ("ACC_Engaged", "DAS_3",0),#ACC Engaged
        ("ACC_STOP", "DAS_3",0),#ACC Engaged
        ("Status", "DAS_3",0),
        ("COUNTER", "DAS_3",0),
        ("ACC_TORQ", "DAS_3",0),
        ("ACC_Set_Speed", "DAS_4",0),
        ("ACC_Activation_Status", "DAS_4",0),
        ("ACC_DISTANCE_CONFIG_2", "DAS_4",0),
        ("Auto_High_Beam", "DAS_6",0),
      ]
      checks += [
        ("DAS_3", 50),
        ("DAS_4", 50),
        ]

    return CANParser(DBC[CP.carFingerprint]["pt"], signals, checks, 2)
