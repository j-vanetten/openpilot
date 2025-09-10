from cereal import car
from openpilot.common.params import Params
from opendbc.car.car_helpers import button_pressed
from opendbc.car.chrysler.values import HYBRID_CARS

ButtonType = car.CarState.ButtonEvent.Type

class LongCarController:
  def __init__(self, CarController, CP, params, packer):
    self.CarController = CarController
    self.CP = CP
    self.params = params
    self.packer = packer
    self.last_das_3_counter = -1
    self.last_das_5_counter = -1
    self.hybrid = CP.carFingerprint in HYBRID_CARS

    self.settingsParams = Params()

  def button_control(self, CC, CS):
    if not CS.longControl:
      return False

    if CC.cruiseControl.cancel or button_pressed(CS.out, ButtonType.cancel) or CS.out.brakePressed:
      CS.longEnabled = False
    elif button_pressed(CS.out, ButtonType.accelCruise) or \
        button_pressed(CS.out, ButtonType.decelCruise) or \
        button_pressed(CS.out, ButtonType.resumeCruise):
        CS.longEnabled = CS.forward_gear

    accDiff = None
    if button_pressed(CS.out, ButtonType.followInc, False):
      if CS.out.jvePilotCarState.accEco < 2:
        accDiff = 1
    elif button_pressed(CS.out, ButtonType.followDec, False):
      if CS.out.jvePilotCarState.accEco > 0:
        accDiff = -1
    if accDiff is not None:
      newEco = CS.out.jvePilotCarState.accEco + accDiff
      self.settingsParams.put_nonblocking("jvePilot.settings.accEco", newEco)

    return True

  def acc(self, longitudinalPlan, frame, CC, CS, can_sends):
    return None
