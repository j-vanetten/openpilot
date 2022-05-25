"""Utilities for reading real time clocks and keeping soft real time constraints."""
import gc
import os
import time
import multiprocessing
from typing import Optional

from common.clock import sec_since_boot  # pylint: disable=no-name-in-module, import-error
from selfdrive.hardware import PC, TICI


# time step for each process
DT_CTRL = 0.01  # controlsd
DT_MDL = 0.05  # model
DT_TRML = 0.5  # thermald and manager

# driver monitoring
if TICI:
  DT_DMON = 0.05
else:
  DT_DMON = 0.1


class Priority:
  # CORE 2
  # - modeld = 55
  # - camerad = 54
  CTRL_LOW = 51 # plannerd & radard

  # CORE 3
  # - boardd = 55
  CTRL_HIGH = 53


def set_realtime_priority(level: int) -> None:
  if not PC:
    os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(level))  # type: ignore[attr-defined]


def set_core_affinity(core: int) -> None:
  if not PC:
    os.sched_setaffinity(0, [core,])   # type: ignore[attr-defined]


def config_realtime_process(core: int, priority: int) -> None:
  gc.disable()
  set_realtime_priority(priority)
  set_core_affinity(core)


class Ratekeeper:
  def __init__(self, rate: int, print_delay_threshold: Optional[float] = 0.0) -> None:
    """Rate in Hz for ratekeeping. print_delay_threshold must be nonnegative."""
    self._interval = 1. / rate
    self._next_frame_time = sec_since_boot() + self._interval
    self._print_delay_threshold = print_delay_threshold
    self._frame = 0
    self._remaining = 0.0
    self._process_name = multiprocessing.current_process().name

  @property
  def frame(self) -> int:
    return self._frame

  @property
  def remaining(self) -> float:
    return self._remaining

  # Maintain loop rate by calling this at the end of each loop
  def keep_time(self) -> bool:
    lagged = self.monitor_time()
    if self._remaining > 0:
      time.sleep(self._remaining)
    return lagged

  # this only monitor the cumulative lag, but does not enforce a rate
  def monitor_time(self) -> bool:
    lagged = False
    remaining = self._next_frame_time - sec_since_boot()
    self._next_frame_time += self._interval
    if self._print_delay_threshold is not None and remaining < -self._print_delay_threshold:
      print(f"{self._process_name} lagging by {-remaining * 1000:.2f} ms")
      lagged = True
    self._frame += 1
    self._remaining = remaining
    return lagged
