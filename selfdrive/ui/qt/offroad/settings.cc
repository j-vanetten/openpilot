#include <string>
#include <iostream>
#include <sstream>
#include <cassert>

#ifndef QCOM
#include "networking.hpp"
#endif
#include "settings.hpp"
#include "widgets/input.hpp"
#include "widgets/toggle.hpp"
#include "widgets/offroad_alerts.hpp"
#include "widgets/controls.hpp"
#include "widgets/ssh_keys.hpp"
#include "common/params.h"
#include "common/util.h"
#include "selfdrive/hardware/hw.h"

QWidget * jvePilot_panel() {
  QVBoxLayout *toggles_list = new QVBoxLayout();

  // slowInCurves
  QList<struct ConfigButton> slowInCurvesConfigs = { 
    { "jvePilot.settings.slowInCurves.speedRatio", 
      "1.0", 0.1, 2, 
      "Speed Ratio",
      "Default: 1.0\n"
        "Use this to tune the speed in curves to you liking."
    },
    { "jvePilot.settings.slowInCurves.speedDropoffAngle",
      "0.0", -360, 360, 
      "Speed Dropoff",
      "Default: 0\n"
        "Use this to tune the speed as the curve gets tighter."
    }
  };
  toggles_list->addWidget(new ParamControl("jvePilot.settings.slowInCurves",
                                            "Slow in Curves",
                                            "When in a curve, jvePilot will slow down for you.",
                                            "../assets/jvepilot/settings/icon_slow_in_curves.png",
                                            &slowInCurvesConfigs
                                          ));
  // autoFollow
  QList<struct ConfigButton> autoFollowConfigs = { 
    { "jvePilot.settings.autoFollow.speed1-2Bars",
      "15", 0, 300, 
      "1-2 Bar Change Over",
      "Default: 15 mph\n"
        "Use this to change the speed at which Auto Follow will switch between one to two bars."
    },
    { "jvePilot.settings.autoFollow.speed2-3Bars",
      "30", 0, 300, 
      "2-3 Bar Change Over",
      "Default: 30 mph\n"
        "Use this to change the speed at which Auto Follow will switch between two to three bars."
    },
    { "jvePilot.settings.autoFollow.speed3-4Bars",
      "65", 0, 300, 
      "3-4 Bar Change Over",
      "Default: 65 mph\n"
        "Use this to change the speed at which Auto Follow will switch between three to four bars."
    }
  };
  toggles_list->addWidget(horizontal_line());
  toggles_list->addWidget(new ParamControl("jvePilot.settings.autoFollow",
                                            "Start with Auto Follow Enabled",
                                            "When enabled, jvePilot will enable Auto Follow on the start of every drive.",
                                            "../assets/jvepilot/settings/icon_auto_follow.png",
                                            &autoFollowConfigs
                                          ));

  // reverseAccSpeedChange
  toggles_list->addWidget(horizontal_line());
  toggles_list->addWidget(new ParamControl("jvePilot.settings.reverseAccSpeedChange",
                                            "Reverse ACC +/- Speeds",
                                            "When enabled, quick pressing the ACC +/- buttons changes the speed in 5 mph increments."
                                            " Hold a little longer to change by 1 mph."
                                            " Disable to keep stock setting.",
                                            "../assets/jvepilot/settings/icon_acc_speed_change.png"
                                          ));

  // autoResume
  toggles_list->addWidget(horizontal_line());
  toggles_list->addWidget(new ParamControl("jvePilot.settings.autoResume",
                                            "Auto Resume",
                                            "When enabled, jvePilot will resume after ACC comes to a stop behind another vehicle.",
                                            "../assets/jvepilot/settings/icon_auto_resume.png"
                                          ));

  // disableOnGas
  toggles_list->addWidget(horizontal_line());
  toggles_list->addWidget(new ParamControl("jvePilot.settings.disableOnGas",
                                            "Disable on Gas",
                                            "When enabled, jvePilot will disengage jvePilot when the gas pedal is pressed.",
                                            "../assets/jvepilot/settings/icon_gas_pedal.png"
                                          ));

  // misc
  QList<struct ConfigButton> miscConfigs = { 
    { "jvePilot.settings.deviceOffset",
      "0.00", -2, 2, 
      "Device Offset",
      "Default: 0.00 meters\n"
        "Compensate for mounting your device off center in the windshield."
        "NOTE: This is not how far the CAMERA is off center, but how far the MOUNT is off center."
    },
    { "jvePilot.settings.speedAdjustRatio",
      "1.0", 0.9, 1.1, 
      "Speed Adjust Ratio",
      "Default: 1.0\n"
        "jvePilot can report an incorrect speed compared to your vehicle or the real world."
        " Apps like Waze report you current speed using GPS which is more accurate than jvePilot or your speedometer may report."
        " Use this setting to get the speed reported by jvePilot just right."
    }
  };
  toggles_list->addWidget(horizontal_line());
  toggles_list->addWidget(new LabelControl( "jvePilot Device Settings",
                                            "", 
                                            "Use these settings tune some of jvePilot's operational settings.",
                                            &miscConfigs));

  // accEco
  QList<struct ConfigButton> ecoConfigs = {
    { "jvePilot.settings.accEco.speedAheadLevel1",
      "7", 1, 200,
      "Keep ahead at ACC Eco level 1",
      "Default: 7 mph\n"
        "The higher the number the more acceleration that occurs."
    },
    { "jvePilot.settings.accEco.speedAheadLevel2",
      "5", 1, 200,
      "Keep ahead at ACC Eco level 2",
      "Default: 5 mph\n"
        "The higher the number the more acceleration that occurs."
    }
  };
  toggles_list->addWidget(horizontal_line());
  toggles_list->addWidget(new LabelControl( "ACC Eco",
                                            "",
                                            "Use these settings to tune how much acceleration occurs by limiting how much ACC is set above your current speed.",
                                            &ecoConfigs));

  // acc follow distance
  QList<struct ConfigButton> accFollowDistanceConfigs = { 
    { "jvePilot.settings.accFollow1RadarRatio",
      "2.6", 0.5, 4, 
      "Ratio at Follow Level 1",
      "Default: 2.6\n"
        "At follow level 1, apply this ratio to the radar distance."
    },
    { "jvePilot.settings.accFollow2RadarRatio",
      "2.1", 0.5, 4,
      "Ratio at Follow Level 2",
      "Default: 2.1\n"
        "At follow level 2, apply this ratio to the radar distance."
    },
    { "jvePilot.settings.accFollow3RadarRatio",
      "1.5", 0.5, 4, 
      "Ratio at Follow Level 3",
      "Default: 2.6\n"
        "At follow level 3, apply this ratio to the radar distance."
    },
    { "jvePilot.settings.accFollow4RadarRatio",
      "1.1", 0.5, 4, 
      "Ratio at Follow Level 4",
      "Default: 2.6\n"
        "At follow level 4, apply this ratio to the radar distance."
    }
  };
  toggles_list->addWidget(horizontal_line());
  toggles_list->addWidget(new LabelControl( "ACC Follow Distance", 
                                            "", 
                                            "jvePilot and ACC's follow distance setting are at odds with one another."
                                            " To solve this, we adjust what jvePilot thinks the distance to vehicle in front of you is."
                                            " A higher number means jvePilot thinks the distance to a leading vehicle it actually further away."
                                            " This causes jvePilot to move up closer than it normally would.", 
                                            &accFollowDistanceConfigs));

  QWidget *widget = new QWidget;
  widget->setLayout(toggles_list);
  return widget;
}

QWidget * toggles_panel() {
  QVBoxLayout *toggles_list = new QVBoxLayout();

  toggles_list->addWidget(new ParamControl("OpenpilotEnabledToggle",
                                            "Enable openpilot",
                                            "Use the openpilot system for adaptive cruise control and lane keep driver assistance. Your attention is required at all times to use this feature. Changing this setting takes effect when the car is powered off.",
                                            "../assets/offroad/icon_openpilot.png"
                                              ));
  toggles_list->addWidget(horizontal_line());
  toggles_list->addWidget(new ParamControl("IsLdwEnabled",
                                            "Enable Lane Departure Warnings",
                                            "Receive alerts to steer back into the lane when your vehicle drifts over a detected lane line without a turn signal activated while driving over 31mph (50kph).",
                                            "../assets/offroad/icon_warning.png"
                                              ));
  toggles_list->addWidget(horizontal_line());
  toggles_list->addWidget(new ParamControl("IsRHD",
                                            "Enable Right-Hand Drive",
                                            "Allow openpilot to obey left-hand traffic conventions and perform driver monitoring on right driver seat.",
                                            "../assets/offroad/icon_openpilot_mirrored.png"
                                            ));
  toggles_list->addWidget(horizontal_line());
  toggles_list->addWidget(new ParamControl("IsMetric",
                                            "Use Metric System",
                                            "Display speed in km/h instead of mp/h.",
                                            "../assets/offroad/icon_metric.png"
                                            ));
  toggles_list->addWidget(horizontal_line());
  toggles_list->addWidget(new ParamControl("CommunityFeaturesToggle",
                                            "Enable Community Features",
                                            "Use features from the open source community that are not maintained or supported by comma.ai and have not been confirmed to meet the standard safety model. These features include community supported cars and community supported hardware. Be extra cautious when using these features",
                                            "../assets/offroad/icon_shell.png"
                                            ));
  toggles_list->addWidget(horizontal_line());
  ParamControl *record_toggle = new ParamControl("RecordFront",
                                            "Record and Upload Driver Camera",
                                            "Upload data from the driver facing camera and help improve the driver monitoring algorithm.",
                                            "../assets/offroad/icon_network.png");
  toggles_list->addWidget(record_toggle);
  toggles_list->addWidget(horizontal_line());
  toggles_list->addWidget(new ParamControl("EndToEndToggle",
                                           "\U0001f96c Disable use of lanelines (Alpha) \U0001f96c",
                                           "In this mode openpilot will ignore lanelines and just drive how it thinks a human would.",
                                           "../assets/offroad/icon_road.png"));

  bool record_lock = Params().read_db_bool("RecordFrontLock");
  record_toggle->setEnabled(!record_lock);

  QWidget *widget = new QWidget;
  widget->setLayout(toggles_list);
  return widget;
}

DevicePanel::DevicePanel(QWidget* parent) : QWidget(parent) {
  QVBoxLayout *device_layout = new QVBoxLayout;

  Params params = Params();

  QString dongle = QString::fromStdString(params.get("DongleId", false));
  device_layout->addWidget(new LabelControl("Dongle ID", dongle));
  device_layout->addWidget(horizontal_line());

  QString serial = QString::fromStdString(params.get("HardwareSerial", false));
  device_layout->addWidget(new LabelControl("Serial", serial));

  // offroad-only buttons
  QList<ButtonControl*> offroad_btns;

  offroad_btns.append(new ButtonControl("Driver Camera", "PREVIEW",
                                   "Preview the driver facing camera to help optimize device mounting position for best driver monitoring experience. (vehicle must be off)",
                                   [=]() { Params().write_db_value("IsDriverViewEnabled", "1", 1); }));

  offroad_btns.append(new ButtonControl("Reset Calibration", "RESET",
                                   "openpilot requires the device to be mounted within 4° left or right and within 5° up or down. openpilot is continuously calibrating, resetting is rarely required.", [=]() {
    if (ConfirmationDialog::confirm("Are you sure you want to reset calibration?")) {
      Params().delete_db_value("CalibrationParams");
    }
  }));

  offroad_btns.append(new ButtonControl("Review Training Guide", "REVIEW",
                                        "Review the rules, features, and limitations of openpilot", [=]() {
    if (ConfirmationDialog::confirm("Are you sure you want to review the training guide?")) {
      Params().delete_db_value("CompletedTrainingVersion");
      emit reviewTrainingGuide();
    }
  }));

  QString brand = params.read_db_bool("Passive") ? "dashcam" : "openpilot";
  offroad_btns.append(new ButtonControl("Uninstall " + brand, "UNINSTALL", "", [=]() {
    if (ConfirmationDialog::confirm("Are you sure you want to uninstall?")) {
      Params().write_db_value("DoUninstall", "1");
    }
  }));

  for(auto &btn : offroad_btns){
    device_layout->addWidget(horizontal_line());
    QObject::connect(parent, SIGNAL(offroadTransition(bool)), btn, SLOT(setEnabled(bool)));
    device_layout->addWidget(btn);
  }

  // power buttons
  QHBoxLayout *power_layout = new QHBoxLayout();
  power_layout->setSpacing(30);

  QPushButton *reboot_btn = new QPushButton("Reboot");
  power_layout->addWidget(reboot_btn);
  QObject::connect(reboot_btn, &QPushButton::released, [=]() {
    if (ConfirmationDialog::confirm("Are you sure you want to reboot?")) {
      Hardware::reboot();
    }
  });

  QPushButton *poweroff_btn = new QPushButton("Power Off");
  poweroff_btn->setStyleSheet("background-color: #E22C2C;");
  power_layout->addWidget(poweroff_btn);
  QObject::connect(poweroff_btn, &QPushButton::released, [=]() {
    if (ConfirmationDialog::confirm("Are you sure you want to power off?")) {
      Hardware::poweroff();
    }
  });

  device_layout->addLayout(power_layout);

  setLayout(device_layout);
  setStyleSheet(R"(
    QPushButton {
      padding: 0;
      height: 120px;
      border-radius: 15px;
      background-color: #393939;
    }
  )");
}

DeveloperPanel::DeveloperPanel(QWidget* parent) : QFrame(parent) {
  QVBoxLayout *main_layout = new QVBoxLayout(this);
  setLayout(main_layout);
  setStyleSheet(R"(QLabel {font-size: 50px;})");
}

void DeveloperPanel::showEvent(QShowEvent *event) {
  Params params = Params();
  std::string brand = params.read_db_bool("Passive") ? "dashcam" : "openpilot";
  QList<QPair<QString, std::string>> dev_params = {
    {"Version", brand + " v" + params.get("Version", false).substr(0, 14)},
    {"Git Branch", params.get("GitBranch", false)},
    {"Git Commit", params.get("GitCommit", false).substr(0, 10)},
    {"Panda Firmware", params.get("PandaFirmwareHex", false)},
    {"OS Version", Hardware::get_os_version()},
  };

  for (int i = 0; i < dev_params.size(); i++) {
    const auto &[name, value] = dev_params[i];
    QString val = QString::fromStdString(value).trimmed();
    if (labels.size() > i) {
      labels[i]->setText(val);
    } else {
      labels.push_back(new LabelControl(name, val));
      layout()->addWidget(labels[i]);
      if (i < (dev_params.size() - 1)) {
        layout()->addWidget(horizontal_line());
      }
    }
  }
}

QWidget * network_panel(QWidget * parent) {
#ifdef QCOM
  QVBoxLayout *layout = new QVBoxLayout;
  layout->setSpacing(30);

  // wifi + tethering buttons
  layout->addWidget(new ButtonControl("WiFi Settings", "OPEN", "",
                                      [=]() { HardwareEon::launch_wifi(); }));
  layout->addWidget(horizontal_line());

  layout->addWidget(new ButtonControl("Tethering Settings", "OPEN", "",
                                      [=]() { HardwareEon::launch_tethering(); }));
  layout->addWidget(horizontal_line());

  // SSH key management
  layout->addWidget(new SshToggle());
  layout->addWidget(horizontal_line());
  layout->addWidget(new SshControl());

  layout->addStretch(1);

  QWidget *w = new QWidget;
  w->setLayout(layout);
#else
  Networking *w = new Networking(parent);
#endif
  return w;
}

SettingsWindow::SettingsWindow(QWidget *parent) : QFrame(parent) {
  // setup two main layouts
  QVBoxLayout *sidebar_layout = new QVBoxLayout();
  sidebar_layout->setMargin(0);
  panel_widget = new QStackedWidget();
  panel_widget->setStyleSheet(R"(
    border-radius: 30px;
    background-color: #292929;
  )");

  // close button
  QPushButton *close_btn = new QPushButton("X");
  close_btn->setStyleSheet(R"(
    font-size: 90px;
    font-weight: bold;
    border 1px grey solid;
    border-radius: 85px;
    background-color: #292929;
  )");
  close_btn->setFixedSize(170, 170);
  sidebar_layout->addSpacing(45);
  sidebar_layout->addWidget(close_btn, 0, Qt::AlignCenter);
  QObject::connect(close_btn, SIGNAL(released()), this, SIGNAL(closeSettings()));

  // setup panels
  DevicePanel *device = new DevicePanel(this);
  QObject::connect(device, SIGNAL(reviewTrainingGuide()), this, SIGNAL(reviewTrainingGuide()));

  QPair<QString, QWidget *> panels[] = {
    {"Device", device},
    {"Network", network_panel(this)},
    {"Toggles", toggles_panel()},
    {"jvePilot", jvePilot_panel()},
    {"Developer", new DeveloperPanel()},
  };

  sidebar_layout->addSpacing(45);
  nav_btns = new QButtonGroup();
  for (auto &[name, panel] : panels) {
    QPushButton *btn = new QPushButton(name);
    btn->setCheckable(true);
    btn->setStyleSheet(R"(
      QPushButton {
        color: grey;
        border: none;
        background: none;
        font-size: 60px;
        font-weight: 500;
        padding-top: 25px;
        padding-bottom: 25px;
      }
      QPushButton:checked {
        color: white;
      }
    )");

    nav_btns->addButton(btn);
    sidebar_layout->addWidget(btn, 0, Qt::AlignRight);

    panel->setContentsMargins(50, 25, 50, 25);
    QScrollArea *panel_frame = new QScrollArea;
    panel_frame->setWidget(panel);
    panel_frame->setWidgetResizable(true);
    panel_frame->setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    panel_frame->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    panel_frame->setStyleSheet("background-color:transparent;");

    QScroller *scroller = QScroller::scroller(panel_frame->viewport());
    auto sp = scroller->scrollerProperties();

    sp.setScrollMetric(QScrollerProperties::VerticalOvershootPolicy, QVariant::fromValue<QScrollerProperties::OvershootPolicy>(QScrollerProperties::OvershootAlwaysOff));

    scroller->grabGesture(panel_frame->viewport(), QScroller::LeftMouseButtonGesture);
    scroller->setScrollerProperties(sp);

    panel_widget->addWidget(panel_frame);

    QObject::connect(btn, &QPushButton::released, [=, w = panel_frame]() {
      panel_widget->setCurrentWidget(w);
    });
  }
  qobject_cast<QPushButton *>(nav_btns->buttons()[0])->setChecked(true);
  sidebar_layout->setContentsMargins(50, 50, 100, 50);

  // main settings layout, sidebar + main panel
  QHBoxLayout *settings_layout = new QHBoxLayout();

  sidebar_widget = new QWidget;
  sidebar_widget->setLayout(sidebar_layout);
  sidebar_widget->setFixedWidth(500);
  settings_layout->addWidget(sidebar_widget);
  settings_layout->addWidget(panel_widget);

  setLayout(settings_layout);
  setStyleSheet(R"(
    * {
      color: white;
      font-size: 50px;
    }
    SettingsWindow {
      background-color: black;
    }
  )");
}