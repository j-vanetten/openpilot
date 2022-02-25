#include <QMap>
#include <QSoundEffect>
#include <QString>

#include "selfdrive/hardware/hw.h"
#include "selfdrive/ui/ui.h"

const std::tuple<AudibleAlert, QString, int, float> sound_list[] = {
  // AudibleAlert, file name, loop count
  {AudibleAlert::ENGAGE, "engage.wav", 0, 1.0},
  {AudibleAlert::QUIET_ENGAGE, "engage.wav", 0, 0.5},
  {AudibleAlert::DISENGAGE, "disengage.wav", 0, 1.0},
  {AudibleAlert::QUIET_DISENGAGE, "disengage.wav", 0, 0.5},
  {AudibleAlert::REFUSE, "refuse.wav", 0, 1.0},

  {AudibleAlert::PROMPT, "prompt.wav", 0, 1.0},
  {AudibleAlert::PROMPT_REPEAT, "prompt.wav", QSoundEffect::Infinite, 1.0},
  {AudibleAlert::PROMPT_DISTRACTED, "prompt_distracted.wav", QSoundEffect::Infinite, 1.0},

  {AudibleAlert::WARNING_SOFT, "warning_soft.wav", QSoundEffect::Infinite, 1.0},
  {AudibleAlert::WARNING_IMMEDIATE, "warning_immediate.wav", QSoundEffect::Infinite, 1.0},
};

class Sound : public QObject {
public:
  explicit Sound(QObject *parent = 0);

protected:
  void update();
  void setAlert(const Alert &alert);

  Alert current_alert = {};
  QMap<AudibleAlert, QPair<QSoundEffect *, QPair<int, float>>> sounds;
  SubMaster sm;
  uint64_t started_frame;
};
