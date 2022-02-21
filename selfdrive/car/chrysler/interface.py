#!/usr/bin/env python3
from cereal import car
from selfdrive.car.chrysler.values import CAR, CarControllerParams
from selfdrive.car import STD_CARGO_KG, scale_rot_inertia, scale_tire_stiffness, gen_empty_fingerprint, get_safety_config
from selfdrive.car.interfaces import CarInterfaceBase
from common.cached_params import CachedParams
from common.op_params import opParams

ButtonType = car.CarState.ButtonEvent.Type

GAS_RESUME_SPEED = 2.
cachedParams = CachedParams()
opParams = opParams()

class CarInterface(CarInterfaceBase):
  @staticmethod
  def get_pid_accel_limits(CP, current_speed, cruise_speed):
    return CarControllerParams.ACCEL_MIN, CarControllerParams.ACCEL_MAX * CarInterface.eco_multiplier()

  @staticmethod
  def eco_multiplier():
    eco_multiplier = 1
    eco = cachedParams.get_float('jvePilot.carState.accEco', 1000)
    if eco == 1:
      eco_multiplier = CarControllerParams.ECO_1
    elif eco == 2:
      eco_multiplier = CarControllerParams.ECO_2

    return eco_multiplier

  @staticmethod
  def get_params(candidate, fingerprint=gen_empty_fingerprint(), car_fw=None):
    min_steer_check = opParams.get('steer.checkMinimum')

    ret = CarInterfaceBase.get_std_params(candidate, fingerprint)
    ret.carName = "chrysler"
    ret.safetyConfigs = [get_safety_config(car.CarParams.SafetyModel.chrysler)]

    # Speed conversion:              20, 45 mph
    ret.wheelbase = 3.089  # in meters for Pacifica Hybrid 2017
    ret.steerRatio = 16.2  # Pacifica Hybrid 2017
    ret.mass = 2242. + STD_CARGO_KG  # kg curb weight Pacifica Hybrid 2017
    ret.lateralTuning.pid.kpBP, ret.lateralTuning.pid.kiBP = [[9., 20.], [9., 20.]]
    ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.15, 0.30], [0.03, 0.05]]
    ret.lateralTuning.pid.kf = 0.00006   # full torque for 10 deg at 80mph means 0.00007818594
    ret.steerActuatorDelay = 0.1
    ret.steerRateCost = 0.7
    ret.steerLimitTimer = 0.4

    if candidate in (CAR.JEEP_CHEROKEE, CAR.JEEP_CHEROKEE_2019):
      ret.wheelbase = 2.91  # in meters
      ret.steerRatio = 12.7
      ret.steerActuatorDelay = 0.2  # in seconds
      ret.enableBsm = True

    ret.centerToFront = ret.wheelbase * 0.44

    if candidate in (CAR.RAM_1500):
      ret.wheelbase = 3.88  # 2021 Ram 1500
      ret.steerRatio = 15.  # just a guess
      ret.mass = 2493. + STD_CARGO_KG  # kg curb weight 2021 Ram 1500
      ret.lateralTuning.pid.kpBP, ret.lateralTuning.pid.kiBP = [[0.], [0.,]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.10], [0.008,]]
      ret.steerActuatorDelay = 0.1
      ret.steerRateCost = 0.7  # may need tuning
      ret.centerToFront = ret.wheelbase * 0.4 # just a guess
      ret.minSteerSpeed = 14.5

    if candidate in (CAR.RAM_2500):
      ret.wheelbase = 3.785  # in meters
      ret.steerRatio = 23  # just a guess
      ret.mass = 3405. + STD_CARGO_KG  # kg curb weight 2021 Ram 2500
      ret.lateralTuning.pid.kpBP, ret.lateralTuning.pid.kiBP = [[0.], [0.,]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.15], [0.015,]]
      ret.steerActuatorDelay = 0.1
      ret.steerRateCost = 0.5  # may need tuning
      ret.centerToFront = ret.wheelbase * 0.38 # calculated from 100% - (front axle weight/total weight)
      ret.minSteerSpeed = 16

    if min_steer_check:
      ret.minSteerSpeed = 3.8  # m/s
      if candidate in (CAR.PACIFICA_2019_HYBRID, CAR.PACIFICA_2020, CAR.JEEP_CHEROKEE_2019):
        # TODO allow 2019 cars to steer down to 13 m/s if already engaged.
        ret.minSteerSpeed = 17.5  # m/s 17 on the way up, 13 on the way down once engaged.
      if candidate in (CAR.RAM_1500):
        ret.minSteerSpeed = 14.5
      if candidate in (CAR.RAM_2500):
        ret.minSteerSpeed = 16

    # starting with reasonable value for civic and scaling by mass and wheelbase
    ret.rotationalInertia = scale_rot_inertia(ret.mass, ret.wheelbase)

    # TODO: start from empirically derived lateral slip stiffness for the civic and scale by
    # mass and CG position, so all cars will have approximately similar dyn behaviors
    ret.tireStiffnessFront, ret.tireStiffnessRear = scale_tire_stiffness(ret.mass, ret.wheelbase, ret.centerToFront)

    ret.openpilotLongitudinalControl = True  # kind of...
    ret.pcmCruiseSpeed = False  # Let jvePilot control the pcm cruise speed

    ret.enableBsm |= 720 in fingerprint[0]

    return ret

  # returns a car.CarState
  def update(self, c, can_strings):
    # ******************* do can recv *******************
    self.cp.update_strings(can_strings)
    self.cp_cam.update_strings(can_strings)

    ret = self.CS.update(self.cp, self.cp_cam)

    ret.canValid = self.cp.can_valid and self.cp_cam.can_valid

    # speeds
    ret.steeringRateLimited = self.CC.steer_rate_limited if self.CC is not None else False

    # events
    events = self.create_common_events(ret, extra_gears=[car.CarState.GearShifter.low],
                                       gas_resume_speed=GAS_RESUME_SPEED, pcm_enable=False)

    if not self.CS.longControl and ret.brakePressed and ret.vEgo < GAS_RESUME_SPEED:
      events.add(car.CarEvent.EventName.accBrakeHold)
    elif not self.CC.moving_fast:
      events.add(car.CarEvent.EventName.belowSteerSpeed)

    if self.CS.cruise_error:
      events.add(car.CarEvent.EventName.brakeUnavailable)

    if self.CS.button_pressed(ButtonType.cancel):
      events.add(car.CarEvent.EventName.buttonCancel)  # cancel button pressed
    elif ret.cruiseState.enabled and not self.CS.out.cruiseState.enabled:
      events.add(car.CarEvent.EventName.pcmEnable)  # cruse is enabled
    elif (not ret.cruiseState.enabled) and (ret.vEgo > GAS_RESUME_SPEED or (self.CS.out.cruiseState.enabled and (not ret.standstill))):
      events.add(car.CarEvent.EventName.pcmDisable)  # give up, too fast to resume

    if self.CS.longControl:
      if ret.brakePressed and not self.CS.out.brakePressed:
        events.add(car.CarEvent.EventName.pedalPressed)

    ret.events = events.to_msg()

    # copy back carState packet to CS
    self.CS.out = ret.as_reader()

    return self.CS.out

  # pass in a car.CarControl
  # to be called @ 100hz
  def apply(self, c):

    if (self.CS.frame == -1):
      return []  # if we haven't seen a frame 220, then do not update.

    can_sends = self.CC.update(c.enabled, self.CS, c.actuators, c.cruiseControl.cancel, c.hudControl.visualAlert,
                               GAS_RESUME_SPEED, c)

    return can_sends
