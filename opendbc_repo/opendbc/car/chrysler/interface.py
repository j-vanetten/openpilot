#!/usr/bin/env python3
from opendbc.car import Bus, get_safety_config, structs
from opendbc.car.chrysler.carcontroller import CarController
from opendbc.car.chrysler.carstate import CarState
from opendbc.car.chrysler.radar_interface import RadarInterface
from opendbc.car.chrysler.values import DBC, CAR, RAM_HD, RAM_DT, RAM_CARS, JEEPS, ChryslerFlags, ChryslerSafetyFlags
from opendbc.car.interfaces import CarInterfaceBase

from openpilot.common.params import Params
from openpilot.common.cached_params import CachedParams

params = Params()
cachedParams = CachedParams()
ButtonType = structs.CarState.ButtonEvent.Type

class CarInterface(CarInterfaceBase):
  CarState = CarState
  CarController = CarController
  RadarInterface = RadarInterface

  ACCEL_MAX = 2.  # m/s2, high to not limit stock ACC
  ACCEL_MIN = -3.5  # m/s2

  @staticmethod
  def get_pid_accel_limits(CS, CP, current_speed, cruise_speed):
    return CarInterface.ACCEL_MIN, CarInterface.accel_max(CS)

  @staticmethod
  def accel_max(CS):
    maxAccel = CarInterface.ACCEL_MAX
    if CS.longControl:
      eco = CS.out.jvePilotCarState.accEco
      if eco == 1:
        maxAccel = cachedParams.get_float('jvePilot.settings.accEco.longAccelLevel1', 1000)
      elif eco == 2:
        maxAccel = cachedParams.get_float('jvePilot.settings.accEco.longAccelLevel2', 1000)
      else:
        maxAccel = 2

    return maxAccel

  @staticmethod
  def _get_params(ret: structs.CarParams, candidate, fingerprint, car_fw, alpha_long, is_release, docs) -> structs.CarParams:
    ret.brand = "chrysler"
    ret.dashcamOnly = candidate in RAM_HD

    # radar parsing needs some work, see https://github.com/commaai/openpilot/issues/26842
    ret.radarUnavailable = Bus.radar not in DBC[candidate][Bus.radar]
    ret.steerActuatorDelay = 0.1
    ret.steerLimitTimer = 0.4

    # safety config
    ret.safetyConfigs = [get_safety_config(structs.CarParams.SafetyModel.chrysler)]
    if candidate in RAM_HD:
      ret.safetyConfigs[0].safetyParam |= ChryslerSafetyFlags.RAM_HD.value
    elif candidate in RAM_DT:
      ret.safetyConfigs[0].safetyParam |= ChryslerSafetyFlags.RAM_DT.value
    elif candidate in JEEPS:
      ret.safetyConfigs[0].safetyParam |= ChryslerSafetyFlags.JEEP.value

    CarInterfaceBase.configure_torque_tune(candidate, ret.lateralTuning)
    if candidate not in RAM_CARS:
      # Newer FW versions standard on the following platforms, or flashed by a dealer onto older platforms have a higher minimum steering speed.
      new_eps_platform = candidate in (CAR.CHRYSLER_PACIFICA_2019_HYBRID, CAR.CHRYSLER_PACIFICA_2020, CAR.JEEP_GRAND_CHEROKEE_2019, CAR.DODGE_DURANGO)
      new_eps_firmware = any(fw.ecu == 'eps' and fw.fwVersion[:4] >= b"6841" for fw in car_fw)
      if new_eps_platform or new_eps_firmware:
        ret.flags |= ChryslerFlags.HIGHER_MIN_STEERING_SPEED.value

    # Chrysler
    if candidate in (CAR.CHRYSLER_PACIFICA_2018, CAR.CHRYSLER_PACIFICA_2018_HYBRID, CAR.CHRYSLER_PACIFICA_2019_HYBRID,
                     CAR.CHRYSLER_PACIFICA_2020, CAR.DODGE_DURANGO):
      if params.get_bool("jvePilot.settings.steer.pid"):
        ret.lateralTuning.init('pid')
        ret.lateralTuning.pid.kpBP, ret.lateralTuning.pid.kiBP = [[9., 20.], [9., 20.]]
        ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.15, 0.30], [0.03, 0.05]]
        ret.lateralTuning.pid.kf = 0.00006

      ret.alphaLongitudinalAvailable = False # candidate not in HYBRID_CARS

    # Jeep
    elif candidate in (CAR.JEEP_GRAND_CHEROKEE, CAR.JEEP_GRAND_CHEROKEE_2019):
      ret.steerActuatorDelay = 0.2

      if params.get_bool("jvePilot.settings.steer.pid"):
        ret.lateralTuning.init('pid')
        ret.lateralTuning.pid.kpBP, ret.lateralTuning.pid.kiBP = [[9., 20.], [9., 20.]]
        ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.15, 0.30], [0.03, 0.05]]
        ret.lateralTuning.pid.kf = 0.00006

      ret.enableBsm = True
      ret.alphaLongitudinalAvailable = True

    # Ram
    elif candidate == CAR.RAM_1500_5TH_GEN:
      ret.steerActuatorDelay = 0.2
      ret.wheelbase = 3.88
      # Older EPS FW allow steer to zero
      if any(fw.ecu == 'eps' and b"68" < fw.fwVersion[:4] <= b"6831" for fw in car_fw):
        ret.minSteerSpeed = 0.

    elif candidate == CAR.RAM_HD_5TH_GEN:
      ret.steerActuatorDelay = 0.2

    else:
      raise ValueError(f"Unsupported car: {candidate}")

    if ret.flags & ChryslerFlags.HIGHER_MIN_STEERING_SPEED:
      # TODO: allow these cars to steer down to 13 m/s if already engaged.
      # TODO: Durango 2020 may be able to steer to zero once above 38 kph
      ret.minSteerSpeed = 17.5  # m/s 17 on the way up, 13 on the way down once engaged.

    ret.centerToFront = ret.wheelbase * 0.44
    ret.enableBsm |= 720 in fingerprint[0]

    ret.openpilotLongitudinalControl = True  # kind of...
    ret.pcmCruiseSpeed = False  # Let jvePilot control the pcm cruise speed

    # Autodetect WP
    if (0x4FF in fingerprint[0]) or params.get_bool("jvePilot.settings.steer.noMinimum"):
      params.put_bool_nonblocking("jvePilot.settings.steer.noMinimum", True)
      ret.minSteerSpeed = -0.1

    return ret
