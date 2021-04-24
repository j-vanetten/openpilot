from common.params import Params
import time

CACHE = {}

class CachedParams:
  def __init__(self):
    self.params = Params()

  def get_float(self, key, ms):
    return float(self.get(key, ms))

  def get(self, key, ms):
    current_ms = round(time.time() * 1000)
    if key in CACHE:
      cached = CACHE[key]
      if current_ms < cached[0] + ms:
        return cached[1]

    gotten = self.params.get(key, encoding='utf8')
    CACHE[key] = [current_ms, gotten]

    return gotten
