#!/usr/bin/env python3
import math

from cereal import car
from opendbc.can.parser import CANParser
from selfdrive.car.interfaces import RadarInterfaceBase
from selfdrive.car.chrysler.values import DBC, PRE_2019
from common.params import Params

RADAR_MSGS_C = list(range(0x2c2, 0x2d4 + 2, 2))  # c_ messages 706,...,724
RADAR_MSGS_D = list(range(0x2a2, 0x2b4 + 2, 2))  # d_ messages
LAST_MSG = max(RADAR_MSGS_C + RADAR_MSGS_D)


def _create_radar_can_parser(car_fingerprint):
  if Params().get_bool("jvePilot.settings.visionOnly"):
    return None
  
  dbc = DBC[car_fingerprint]['radar']
  if dbc is None:
    return None

  msg_c_n = len(RADAR_MSGS_C)
  msg_d_n = len(RADAR_MSGS_D)
  # list of [(signal name, message name or number), (...)]
  # [('RADAR_STATE', 1024),
  #  ('LONG_DIST', 1072),
  #  ('LONG_DIST', 1073),
  #  ('LONG_DIST', 1074),
  #  ('LONG_DIST', 1075),

  signals = list(zip(['LONG_DIST'] * msg_c_n +
                     ['LAT_ANGLE'] * msg_c_n +
                     ['REL_SPEED'] * msg_d_n +
                     ['MEASURED'] * msg_d_n +
                     ['PROBABILITY'] * msg_d_n,
                     RADAR_MSGS_C * 2 +  # LONG_DIST, LAT_DIST
                     RADAR_MSGS_D * 3))  # REL_SPEED, MEASURED

  checks = list(zip(RADAR_MSGS_C +
                    RADAR_MSGS_D,
                    [20] * msg_c_n +  # 20Hz (0.05s)
                    [20] * msg_d_n))  # 20Hz (0.05s)

  return CANParser(DBC[car_fingerprint]['radar'], signals, checks, 1)

def _address_to_track(address):
  if address in RADAR_MSGS_C:
    return (address - RADAR_MSGS_C[0]) // 2
  if address in RADAR_MSGS_D:
    return (address - RADAR_MSGS_D[0]) // 2
  raise ValueError("radar received unexpected address %d" % address)

class RadarInterface(RadarInterfaceBase):
  def __init__(self, CP):
    super().__init__(CP)
    self.CP = CP
    self.rcp = _create_radar_can_parser(CP.carFingerprint)
    self.updated_messages = set()
    self.trigger_msg = LAST_MSG

    self.yRel_multiplier = 1 if CP.carFingerprint in PRE_2019 else -1

  def update(self, can_strings):
    if self.rcp is None or self.CP.radarUnavailable:
      return super().update(None)

    vls = self.rcp.update_strings(can_strings)
    self.updated_messages.update(vls)

    if self.trigger_msg not in self.updated_messages:
      return None

    ret = car.RadarData.new_message()
    errors = []
    if not self.rcp.can_valid:
      errors.append("canError")
    ret.errors = errors

    for ii in self.updated_messages:  # ii should be the message ID as a number
      cpt = self.rcp.vl[ii]
      trackId = _address_to_track(ii)

      if trackId not in self.pts:
        self.pts[trackId] = car.RadarData.RadarPoint.new_message()
        self.pts[trackId].trackId = trackId
        self.pts[trackId].aRel = float('nan')
        self.pts[trackId].yvRel = float('nan')

        # self.pts[trackId].yRel = float('nan')

      if 'LONG_DIST' in cpt:  # c_* message
        azimuth = (cpt['LAT_ANGLE'])
        # self.pts[trackId].dRel = math.cos(azimuth) * cpt['LONG_DIST']
        # self.pts[trackId].yRel = math.sin(azimuth) * cpt['LONG_DIST']
        self.pts[trackId].dRel = cpt['LONG_DIST']
        self.pts[trackId].yRel = math.tan(azimuth) * cpt['LONG_DIST'] * self.yRel_multiplier
      else:  # d_* message
        self.pts[trackId].vRel = cpt['REL_SPEED']
        self.pts[trackId].measured = bool(cpt['MEASURED']) and (cpt['PROBABILITY'] > 250)

    # We want a list, not a dictionary. Filter out LONG_DIST==0 because that means it's not valid.
    ret.points = [x for x in self.pts.values() if x.measured and (255 > x.dRel > 0)]

    self.updated_messages.clear()
    return ret