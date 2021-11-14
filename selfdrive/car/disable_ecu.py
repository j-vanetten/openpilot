from selfdrive.car.isotp_parallel_query import IsoTpParallelQuery
from selfdrive.swaglog import cloudlog

COM_CONT_RESPONSE = b''

def disable_ecu(logcan, sendcan, bus=0, addr=0x7d0, com_cont_req=b'\x28\x83\x01', timeout=0.1, retry=10, debug=False,
                diag_request=b'\x10\x03', diag_response=b'\x50\x03'):
  """Silence an ECU by disabling sending and receiving messages using UDS 0x28.
  The ECU will stay silent as long as openpilot keeps sending Tester Present.

  This is used to disable the radar in some cars. Openpilot will emulate the radar.
  WARNING: THIS DISABLES AEB!"""
  cloudlog.warning(f"ecu disable {hex(addr)} ...")

  for i in range(retry):
    try:
      query = IsoTpParallelQuery(sendcan, logcan, bus, [addr], [diag_request], [diag_response], debug=debug)
      print(f"ecu disable part 1")

      for a, b in query.get_data(timeout).items():
        print(f"ecu disable part 1 results a={a} b={b}")
        cloudlog.warning("communication control disable tx/rx ...")

        query = IsoTpParallelQuery(sendcan, logcan, bus, [addr], [com_cont_req], [COM_CONT_RESPONSE], debug=debug)
        print(f"ecu disable part 2")

        query.get_data(0)

        cloudlog.warning("ecu disabled")
        return True
    except Exception:
      print(f"ecu disable exception")
      cloudlog.exception("ecu disable exception")

    print(f"ecu disable retry ({i+1}) ...")
  cloudlog.warning("ecu disable failed")

  query = IsoTpParallelQuery(sendcan, logcan, bus, [addr], [com_cont_req], [COM_CONT_RESPONSE], debug=debug)
  query.get_data(0)
  print(f"ecu disable requested anyway")

  return False
