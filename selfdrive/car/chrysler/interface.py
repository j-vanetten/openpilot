#!/usr/bin/env python3
from cereal import car
from panda import Panda
from selfdrive.car.chrysler.values import CAR, CarControllerParams
from selfdrive.car import STD_CARGO_KG, scale_rot_inertia, scale_tire_stiffness, gen_empty_fingerprint, get_safety_config
from selfdrive.car.chrysler.values import CAR, DBC, RAM_CARS
from selfdrive.car.interfaces import CarInterfaceBase
from common.cached_params import CachedParams
from common.params import Params

ButtonType = car.CarState.ButtonEvent.Type
GAS_RESUME_SPEED = 1.
cachedParams = CachedParams()

class CarInterface(CarInterfaceBase):
  @staticmethod
  def get_pid_accel_limits(CS, CP, current_speed, cruise_speed):
    return CarControllerParams.ACCEL_MIN, CarInterface.accel_max(CS)

  @staticmethod
  def accel_max(CS):
    maxAccel = CarControllerParams.ACCEL_MAX
    if CS.longControl:
      eco = cachedParams.get_float('jvePilot.carState.accEco', 1000)
      if eco == 1:
        maxAccel = cachedParams.get_float('jvePilot.settings.longControl.eco1', 1000)
      elif eco == 2:
        maxAccel = cachedParams.get_float('jvePilot.settings.longControl.eco2', 1000)
      else:
        maxAccel = cachedParams.get_float('jvePilot.settings.longControl.eco0', 1000)

    return maxAccel

  @staticmethod
  def get_params(candidate, fingerprint=gen_empty_fingerprint(), car_fw=None, disable_radar=False):
    ret = CarInterfaceBase.get_std_params(candidate, fingerprint)
    ret.carName = "chrysler"

    ret.radarOffCan = DBC[candidate]['radar'] is None

    param = Panda.FLAG_CHRYSLER_RAM_DT if candidate in RAM_CARS else None
    ret.safetyConfigs = [get_safety_config(car.CarParams.SafetyModel.chrysler, param)]

    ret.steerActuatorDelay = 0.1
    ret.steerLimitTimer = 0.4

    ret.minSteerSpeed = 3.8  # m/s
    if candidate in (CAR.PACIFICA_2019_HYBRID, CAR.PACIFICA_2020, CAR.JEEP_CHEROKEE_2019):
      # TODO: allow 2019 cars to steer down to 13 m/s if already engaged.
      ret.minSteerSpeed = 17.5  # m/s 17 on the way up, 13 on the way down once engaged.

    # Chrysler
    if candidate in (CAR.PACIFICA_2017_HYBRID, CAR.PACIFICA_2018, CAR.PACIFICA_2018_HYBRID, CAR.PACIFICA_2019_HYBRID, CAR.PACIFICA_2020):
      ret.mass = 2242. + STD_CARGO_KG
      ret.wheelbase = 3.089
      ret.steerRatio = 16.2  # Pacifica Hybrid 2017
      ret.lateralTuning.pid.kpBP, ret.lateralTuning.pid.kiBP = [[9., 20.], [9., 20.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.15, 0.30], [0.03, 0.05]]
      ret.lateralTuning.pid.kf = 0.00006

    # Jeep
    elif candidate in (CAR.JEEP_CHEROKEE, CAR.JEEP_CHEROKEE_2019):
      ret.mass = 1778 + STD_CARGO_KG
      ret.wheelbase = 2.71
      ret.steerRatio = 16.7
      ret.steerActuatorDelay = 0.2
      ret.lateralTuning.pid.kpBP, ret.lateralTuning.pid.kiBP = [[9., 20.], [9., 20.]]
      ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.15, 0.30], [0.03, 0.05]]
      ret.lateralTuning.pid.kf = 0.00006

      ret.enableBsm = True

    # Ram
    elif candidate == CAR.RAM_1500:
      ret.steerActuatorDelay = 0.2

      ret.wheelbase = 3.88
      ret.steerRatio = 16.3
      ret.mass = 2493. + STD_CARGO_KG
      ret.maxLateralAccel = 2.4
      ret.minSteerSpeed = 14.5
      CarInterfaceBase.configure_torque_tune(candidate, ret.lateralTuning)


    else:
      raise ValueError(f"Unsupported car: {candidate}")

    if Params().get_bool("jvePilot.settings.steer.noMinimum"):
      ret.minSteerSpeed = -0.1

    ret.centerToFront = ret.wheelbase * 0.44

    # starting with reasonable value for civic and scaling by mass and wheelbase
    ret.rotationalInertia = scale_rot_inertia(ret.mass, ret.wheelbase)

    # TODO: start from empirically derived lateral slip stiffness for the civic and scale by
    # mass and CG position, so all cars will have approximately similar dyn behaviors
    ret.tireStiffnessFront, ret.tireStiffnessRear = scale_tire_stiffness(ret.mass, ret.wheelbase, ret.centerToFront)

    ret.openpilotLongitudinalControl = True  # kind of...
    ret.pcmCruiseSpeed = False  # Let jvePilot control the pcm cruise speed

    ret.enableBsm |= 720 in fingerprint[0]

    return ret

  def _update(self, c):
    ret = self.CS.update(self.cp, self.cp_cam)

    ret.steeringRateLimited = self.CC.steer_rate_limited if self.CC is not None else False

    # events
    events = self.create_common_events(ret, extra_gears=[car.CarState.GearShifter.low],
                                       gas_resume_speed=GAS_RESUME_SPEED, pcm_enable=False)

    if c.enabled and ret.brakePressed and ret.standstill and not self.disable_auto_resume:
      events.add(car.CarEvent.EventName.accBrakeHold)
    else:
      # Low speed steer alert hysteresis logic
      if self.CP.minSteerSpeed > 0. and ret.vEgo < (self.CP.minSteerSpeed + 0.5):
        self.low_speed_alert = True
      elif ret.vEgo > (self.CP.minSteerSpeed + 1.):
        self.low_speed_alert = False

      if self.low_speed_alert:
        events.add(car.CarEvent.EventName.belowSteerSpeed)

    # if self.CS.cruise_error:
    #   events.add(car.CarEvent.EventName.brakeUnavailable)

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

    return ret

  def apply(self, c):
    return self.CC.update(c, self.CS)
