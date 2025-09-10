#include "selfdrive/ui/qt/onroad/buttons.h"

#include <QPainter>

#include "selfdrive/ui/qt/util.h"

void drawIcon(QPainter &p, const QPoint &center, const QPixmap &img, const QBrush &bg, float opacity, int bg_btn_size) {
  p.setRenderHint(QPainter::Antialiasing);
  p.setOpacity(1.0);  // bg dictates opacity of ellipse
  p.setPen(Qt::NoPen);
  p.setBrush(bg);
  p.drawEllipse(center, bg_btn_size / 2, bg_btn_size / 2);
  p.setOpacity(opacity);
  p.drawPixmap(center - QPoint(img.width() / 2, img.height() / 2), img);
  p.setOpacity(1.0);
}

void drawImage(QPainter &p, const QPoint &center, const QPixmap &img, float opacity) {
  p.setRenderHint(QPainter::Antialiasing);
  p.setOpacity(opacity);
  p.drawPixmap(center - QPoint(img.width() / 2, img.height() / 2), img);
  p.setOpacity(1.0);
}

// ExperimentalButton
ExperimentalButton::ExperimentalButton(QWidget *parent) : experimental_mode(false), engageable(false), QPushButton(parent) {
  setFixedSize(btn_size, btn_size);

  engage_img = loadPixmap("../assets/icons/chffr_wheel.png", {img_size, img_size});
  experimental_img = loadPixmap("../assets/icons/experimental.svg", {img_size, img_size});
  QObject::connect(this, &QPushButton::clicked, this, &ExperimentalButton::changeMode);
}

void ExperimentalButton::changeMode() {
  const auto cp = (*uiState()->sm)["carParams"].getCarParams();
  bool can_change = hasLongitudinalControl(cp) && params.getBool("ExperimentalModeConfirmed");
  if (can_change) {
    params.putBool("ExperimentalMode", !experimental_mode);
  }
}

void ExperimentalButton::updateState(const UIState &s) {
  const auto cs = (*s.sm)["selfdriveState"].getSelfdriveState();
  bool eng = cs.getEngageable() || cs.getEnabled();
  if ((cs.getExperimentalMode() != experimental_mode) || (eng != engageable)) {
    engageable = eng;
    experimental_mode = cs.getExperimentalMode();
    update();
  }
}

void ExperimentalButton::paintEvent(QPaintEvent *event) {
  QPainter p(this);
  QPixmap img = experimental_mode ? experimental_img : engage_img;
  drawIcon(p, QPoint(btn_size / 2, btn_size / 2), img, QColor(0, 0, 0, 166), (isDown() || !engageable) ? 0.6 : 1.0, btn_size);
}

// EcoButton
EcoButton::EcoButton(QWidget *parent) : eco(0), QPushButton(parent) {
  setFixedSize(btn_size_lg, btn_size_lg);

  eco_imgs[0] = loadPixmap("../assets/jvepilot/img_acc_eco_off.png", {img_size_lg, img_size_lg});
  eco_imgs[1] = loadPixmap("../assets/jvepilot/img_acc_eco_1.png", {img_size_lg, img_size_lg});
  eco_imgs[2] = loadPixmap("../assets/jvepilot/img_acc_eco_2.png", {img_size_lg, img_size_lg});

  QObject::connect(this, &QPushButton::clicked, this, &EcoButton::changeMode);
}

void EcoButton::changeMode() {
  params.put("jvePilot.settings.accEco", std::to_string((eco == 2 ? 0 : eco + 1)));
}

void EcoButton::updateState(const UIState &s) {
  const auto cs = (*s.sm)["carState"].getCarState().getJvePilotCarState();
  int accEco = cs.getAccEco();
  if (accEco != eco) {
    eco = accEco;
    update();
  }
}

void EcoButton::paintEvent(QPaintEvent *event) {
  QPainter p(this);
  QPixmap img = eco_imgs[eco];
  drawIcon(p, QPoint(btn_size_lg / 2, btn_size_lg / 2), img, QColor(0, 0, 0, 166), isDown() ? 0.6 : 1.0, btn_size_lg);
}

// AutoFollowButton
AutoFollowButton::AutoFollowButton(QWidget *parent) : auto_follow(false), long_control(false), cruise_enabled(false), QPushButton(parent) {
  setFixedSize(btn_size, btn_size);

  imgs[0] = loadPixmap("../assets/jvepilot/auto_follow_off.png", {img_size, img_size});
  imgs[1] = loadPixmap("../assets/jvepilot/auto_follow_on.png", {img_size, img_size});

  long_control_imgs[0] = loadPixmap("../assets/jvepilot/driving_brain_off.png", {img_size, img_size});
  long_control_imgs[1] = loadPixmap("../assets/jvepilot/driving_brain_on.png", {img_size, img_size});
}

void AutoFollowButton::updateState(const UIState &s) {
  const auto cs = (*s.sm)["carState"].getCarState();
  const auto jveState = cs.getJvePilotCarState();
  const auto cruiseState = cs.getCruiseState();

  int autoFollow = jveState.getAutoFollow();
  bool longControl = jveState.getLongControl();
  bool cruiseEnabled = cruiseState.getEnabled();
  if (autoFollow != auto_follow || longControl != long_control || cruiseEnabled != cruise_enabled) {
    auto_follow = autoFollow;
    long_control = longControl;
    cruise_enabled = cruiseEnabled;
    update();
  }
}

void AutoFollowButton::paintEvent(QPaintEvent *event) {
  QPainter p(this);
  QPixmap img = long_control ? long_control_imgs[cruise_enabled ? 1 : 0] : imgs[auto_follow ? 1 : 0];

  drawImage(p, QPoint(btn_size / 2, btn_size / 2), img, 1.0);
}
