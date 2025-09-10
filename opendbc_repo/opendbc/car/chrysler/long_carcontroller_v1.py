import math

from cereal import car
from opendbc.car.common.conversions import Conversions as CV
from openpilot.common.numpy_fast import clip
from opendbc.car.chrysler import chryslercan
from opendbc.car.chrysler.long_carcontroller import LongCarController

LongCtrlState = car.CarControl.Actuators.LongControlState

# LONG PARAMS
LOW_WINDOW = CV.MPH_TO_MS * 5
SLOW_WINDOW = CV.MPH_TO_MS * 20
COAST_WINDOW = CV.MPH_TO_MS * 2

# accelerator
TORQ_RELEASE_CHANGE = 0.35
TORQ_ADJUST_THRESHOLD = 0.3
START_ADJUST_ACCEL_FRAMES = 100
CAN_DOWNSHIFT_ACCEL_FRAMES = 200
ADJUST_ACCEL_COOLDOWN_MAX = 1
TORQ_BRAKE_MAX = -0.1

# braking
BRAKE_CHANGE = 0.06

## COMMA
TIRE_SIZE = [275, 55, 20] # 275/55R20
# https://x-engineer.org/calculate-wheel-radius/
WHEEL_RADIUS = 0.95 * ((TIRE_SIZE[2] * 25.4 / 2) + (TIRE_SIZE[0] * TIRE_SIZE[1] / 100)) / 1000
WHEEL_CIRCUMFERENCE = math.tau * WHEEL_RADIUS
# https://web.archive.org/web/20180116135154/https://www.ramtrucks.com/2019/ram-1500.html
CdA = 13.0 / 10.764 # CdA = frontal drag coefficient x area (ft^2 converted to m^2)
# https://www.epa.gov/compliance-and-fuel-economy-data/data-cars-used-testing-fuel-economy
ROLLING_RESISTANCE_COEFF = 46.31 / 5500 # Target Coef A (lbf) / Equivalent Test Weight (lbs.)
GRAVITY = 9.81 # m/s^2
AIR_DENSITY = 1.225 # kg/m3 (sea level air density of dry air @ 15° C)

class LongCarControllerV1(LongCarController):
  def __init__(self, CarController, CP, params, packer):
    super().__init__(CarController, CP, params, packer)

    # long
    self.accel_steady = 0
    self.last_brake = None
    self.last_torque = 0.
    self.torq_adjust = 0.
    self.under_accel_frame_count = 0
    self.vehicleMass = CP.mass
    self.max_gear = None

    self.finalDriveRatios = [x * CP.axleRatio for x in CP.gearRatios]

  def torqRange(self, CS):
    return CS.wheelTorqMin if self.hybrid else CS.torqMin, CS.wheelTorqMax if self.hybrid else CS.torqMax

  # T = (mass x accel x velocity x 1000)/(.105 x Engine rpm)
  def acc(self, longitudinalPlan, frame, CC, CS, can_sends):
    if not CC.enabled or not CS.longControl or len(longitudinalPlan.speeds) == 0:
      self.torq_adjust = 0
      self.last_brake = None
      self.last_torque = None
      self.max_gear = None
      return None

    vTarget = longitudinalPlan.speeds[0]
    aTarget = CC.actuators.accel

    boost = 0
    if CS.out.vEgo < SLOW_WINDOW and aTarget > 0:
      # improve slow speed acceleration?
      speed_limiter = (SLOW_WINDOW - CS.out.vEgo) / SLOW_WINDOW
      accel_limiter = max(0, (aTarget - CS.out.aEgo) / TORQ_ADJUST_THRESHOLD)
      boost = self.params.ACCEL_MAX * min(speed_limiter, accel_limiter)

    v2aTarget = longitudinalPlan.speeds[-1] - longitudinalPlan.speeds[0]
    if aTarget > v2aTarget > 0:
      # use speed to calc acceleration instead of model
      aTarget = v2aTarget

    aTarget = clip(aTarget, self.params.ACCEL_MIN, self.CarController.accel_max(CS) + boost)

    torqMin, torqMax = self.torqRange(CS)
    long_stopping = CC.actuators.longControlState == LongCtrlState.stopping

    under_accel_frame_count = 0
    override_request = CS.out.gasPressed or CS.out.brakePressed
    if not override_request:
      stop_req = long_stopping or \
        (CS.out.standstill and (longitudinalPlan.shouldStop or not longitudinalPlan.allowThrottle))

      go_req = not stop_req and CS.out.standstill

      if go_req:
        under_accel_frame_count = self.under_accel_frame_count = START_ADJUST_ACCEL_FRAMES  # ready to add torq
        self.last_brake = None

      currently_braking = self.last_brake is not None
      speed_to_far_off = abs(CS.out.vEgo - vTarget) > COAST_WINDOW
      allow_smart_slowing = not speed_to_far_off and CS.out.vEgo > LOW_WINDOW
      engine_brake = allow_smart_slowing and TORQ_BRAKE_MAX < aTarget < 0 \
                     and self.torque(CC, CS, aTarget, vTarget) + self.torq_adjust > torqMin

      if go_req or ((aTarget >= 0 or engine_brake) and not currently_braking):  # gas
        self.acc_gas(CC, CS, frame, aTarget, vTarget)

      elif aTarget < 0:  # brake
        self.acc_brake(CS, aTarget, vTarget, speed_to_far_off)

      elif self.last_brake is not None:  # let up on the brake
        self.last_brake += BRAKE_CHANGE
        if self.last_brake >= 0:
          self.last_brake = None

      elif self.last_torque is not None:  # let up on gas
        self.last_torque -= TORQ_RELEASE_CHANGE
        if self.last_torque <= max(0, torqMin):
          self.last_torque = None

      if stop_req:
        brake = self.last_brake = aTarget if not CS.out.standstill else min(-2, aTarget)
        fidget_stopped_brake_frame = frame % 100 < 50
        brake += 0.01 if fidget_stopped_brake_frame else 0.0
        torque = self.last_torque = None
      elif go_req:
        brake = self.last_brake = None
        torque = math.floor(self.last_torque * 100) / 100
      elif self.last_brake:
        brake = math.floor(self.last_brake * 100) / 100
        torque = self.last_torque = None
      elif self.last_torque:
        brake = self.last_brake = None
        torque = math.floor(self.last_torque * 100) / 100
      else:  # coasting
        brake = self.last_brake = None
        torque = self.last_torque = None
    else:
      self.last_torque = None
      self.last_brake = None
      self.max_gear = None
      stop_req = None
      brake = None
      go_req = None
      torque = None

    # hills/towing
    will_be_slowing = aTarget > 0 > longitudinalPlan.accels[-1] if len(longitudinalPlan.accels) else 0
    if will_be_slowing:  # going to not need it
      self.torq_adjust = max(0, self.torq_adjust - longitudinalPlan.accels[-1] * -10)
    elif aTarget < 0:  # not needed
      self.torq_adjust = max(0, self.torq_adjust - max(aTarget * -10, ADJUST_ACCEL_COOLDOWN_MAX))
    elif CS.out.aEgo > aTarget:  # Too much
      over_accel = CS.out.aEgo - aTarget
      self.torq_adjust = max(0, self.torq_adjust - over_accel)
    elif torque is not None:
      under_accel = aTarget - CS.out.aEgo
      if under_accel > TORQ_ADJUST_THRESHOLD:  # if not close enough
        self.torq_adjust += under_accel * (self.CarController.accel_max(CS) / self.CarController.ACCEL_MAX)
        under_accel_frame_count = self.under_accel_frame_count + 1  # inc under accelerating frame count
        self.torq_adjust = max(0, min(torqMax, self.torq_adjust))

    # Donw shift
    if under_accel_frame_count == 0:
      self.max_gear = None
    elif under_accel_frame_count > CAN_DOWNSHIFT_ACCEL_FRAMES:
      if CS.out.vEgo < vTarget - COAST_WINDOW / self.CarController.accel_max(CS) \
          and CS.out.aEgo < self.CarController.accel_max(CS) / 5 \
          and torque > torqMax * 0.98:  # Time to downshift?
        if CS.transmission_gear > 3 and CS.gasRpm < 4500:
          self.max_gear = CS.transmission_gear - 1
          under_accel_frame_count = 0

    self.under_accel_frame_count = under_accel_frame_count

    if frame % 4 == 0:
      can_sends.append(chryslercan.acc_log(self.packer, int(self.torq_adjust), aTarget, vTarget, CS.out.aEgo))

    brake_prep = brake is not None and len(longitudinalPlan.accels) and longitudinalPlan.accels[0] - longitudinalPlan.accels[-1] > 1.0

    counter_das_3_changed = CS.das_3['COUNTER'] != self.last_das_3_counter
    self.last_das_3_counter = CS.das_3['COUNTER']

    if not self.hybrid or brake is not None or brake_prep:
      can_sends.append(chryslercan.das_3_command(self.packer,
                                                 2 if counter_das_3_changed else 3,
                                                 go_req,
                                                 False if self.hybrid else torque is not None,
                                                 1546.75 if self.hybrid else torque,
                                                 self.max_gear,
                                                 stop_req,
                                                 brake,
                                                 brake_prep,
                                                 CS.das_3))

    if self.hybrid:
      counter_das_5_changed = CS.das_5['COUNTER'] != self.last_das_5_counter
      self.last_das_5_counter = CS.das_5['COUNTER']

      if torque is not None:
        can_sends.append(chryslercan.das_5_command(self.packer,
                                                   2 if counter_das_5_changed else 3,
                                                   torque,
                                                   CS.das_5))

  def calc_drag_force(self, engine_torque, transmission_gear, road_pitch, aEgo, vEgo, wind=0):
    force_drag = 0.5 * CdA * AIR_DENSITY * ((vEgo - wind) ** 2)

    if vEgo < LOW_WINDOW:
      # https://x-engineer.org/rolling-resistance/
      force_rolling = ROLLING_RESISTANCE_COEFF * self.vehicleMass * GRAVITY
      # https://x-engineer.org/aerodynamic-drag/
      return force_rolling + force_drag

    return force_drag

  def torque(self, CC, CS, aTarget, vTarget):
    pitch = CC.orientationNED[1] if len(CC.orientationNED) > 1 else 0
    drag_force = self.calc_drag_force(CS.engine_torque, CS.transmission_gear, pitch, CS.out.aEgo, CS.out.vEgo)
    force = (self.vehicleMass * aTarget) + drag_force
    if self.hybrid:
      return force * WHEEL_RADIUS
    else:
      axle_rpm = CS.gasRpm / self.finalDriveRatios[int(CS.transmission_gear) - 1]
      return (force * vTarget) / axle_rpm

  def acc_gas(self, CC, CS, frame, aTarget, vTarget):
    torqMin, torqMax = self.torqRange(CS)
    accelerating = aTarget > 0 and vTarget > CS.out.vEgo + SLOW_WINDOW
    if accelerating:
      vSmoothTarget = vTarget
      aSmoothTarget = (aTarget + CS.out.aEgo) / 2
    else:
      vSmoothTarget = (vTarget + CS.out.vEgo) / 2
      aSmoothTarget = aTarget

    cruise = self.torque(CC, CS, aSmoothTarget, vSmoothTarget)
    self.last_torque = max(torqMin + 1, min(torqMax, cruise + self.torq_adjust))

  def acc_brake(self, CS, aTarget, vTarget, speed_to_far_off):
    brake_target = max(self.CarController.ACCEL_MIN, round(aTarget, 2))
    if self.last_brake is None:
      self.last_brake = min(0., brake_target / 2)
    elif self.last_brake < -.2 and CS.out.aEgo < brake_target:  # are we slowing too much?
      self.last_brake += (BRAKE_CHANGE / 10)
    else:
      tBrake = brake_target
      if not speed_to_far_off and 0 >= tBrake >= -1:  # let up on brake as we approach
        tBrake = (tBrake * 1.1) + .1

      lBrake = self.last_brake
      if tBrake < lBrake:
        diff = min(BRAKE_CHANGE, (lBrake - tBrake) / 2)
        self.last_brake = max(lBrake - diff, tBrake)
      elif tBrake - lBrake > 0.01:  # don't let up unless it's a big enough jump
        diff = min(BRAKE_CHANGE, (tBrake - lBrake) / 2)
        self.last_brake = min(lBrake + diff, tBrake)
