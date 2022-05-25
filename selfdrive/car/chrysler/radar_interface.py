#!/usr/bin/env python3
import math
from common.numpy_fast import clip
from opendbc.can.parser import CANParser
from cereal import car
from selfdrive.car.interfaces import RadarInterfaceBase
from selfdrive.car.chrysler.values import DBC, CAR

RADAR_MSGS_C = list(range(0x2c2, 0x2d4+2, 2))  # c_ messages 706,...,724
RADAR_MSGS_D = list(range(0x2a2, 0x2b4+2, 2))  # d_ messages
LAST_MSG = max(RADAR_MSGS_C + RADAR_MSGS_D)
NUMBER_MSGS = len(RADAR_MSGS_C) + len(RADAR_MSGS_D)

def _create_radar_can_parser(car_fingerprint):
  msg_n = len(RADAR_MSGS_C)
  # list of [(signal name, message name or number), (...)]
  # [('RADAR_STATE', 1024),
  #  ('LONG_DIST', 1072),
  #  ('LONG_DIST', 1073),
  #  ('LONG_DIST', 1074),
  #  ('LONG_DIST', 1075),

  signals = list(zip(['LONG_DIST'] * msg_n +
                ['LAT_ANGLE'] * msg_n +
                ['REL_SPEED'] * msg_n +
                ['PROBABILITY'] * msg_n +
                ['MEASURED'] * msg_n,
                RADAR_MSGS_C * 2 +  # LONG_DIST, LAT_DIST
                RADAR_MSGS_D * 3))  # REL_SPEED, PROBABILITY, MEASURED

  checks = list(zip(RADAR_MSGS_C +
                    RADAR_MSGS_D,
                    [20] * msg_n +  # 20Hz (0.05s)
                    [20] * msg_n))  # 20Hz (0.05s)

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
    self.rcp = _create_radar_can_parser(CP.carFingerprint)
    self.updated_messages = set()
    self.trigger_msg = LAST_MSG

    self.yRel_multiplier = -1 if CP.carFingerprint in (CAR.PACIFICA_2017_HYBRID, CAR.PACIFICA_2018_HYBRID, CAR.PACIFICA_2019_HYBRID) else 1

  def update(self, can_strings):
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

      if 'LONG_DIST' in cpt:  # c_* message
        azimuth = (cpt['LAT_ANGLE'])
        self.pts[trackId].dRel = math.cos(azimuth) * cpt['LONG_DIST']
        self.pts[trackId].yRel = math.sin(azimuth) * cpt['LONG_DIST'] * self.yRel_multiplier
      else:  # d_* message
        self.pts[trackId].vRel = cpt['REL_SPEED']
        self.pts[trackId].measured = bool(cpt['MEASURED'])

    # We want a list, not a dictionary. Filter out LONG_DIST==0 because that means it's not valid.
    ret.points = [x for x in self.pts.values() if x.measured and 250 > x.dRel > 0]

    self.updated_messages.clear()
    return ret
