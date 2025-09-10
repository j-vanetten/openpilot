#include <cassert>
#include <cmath>
#include <string>
#include <tuple>
#include <vector>

#include <QDebug>

#include "common/watchdog.h"
#include "common/util.h"
#include "selfdrive/ui/qt/network/networking.h"
#include "selfdrive/ui/qt/offroad/settings.h"
#include "selfdrive/ui/qt/qt_window.h"
#include "selfdrive/ui/qt/widgets/prime.h"
#include "selfdrive/ui/qt/widgets/scrollview.h"
#include "selfdrive/ui/qt/offroad/developer_panel.h"
#include "selfdrive/ui/qt/offroad/firehose.h"

#include "common/params.h"

JvePilotTogglesPanel::JvePilotTogglesPanel(QWidget *parent) : ListWidget(parent) {
  QList<AbstractControl*> toggles;

  // slowInCurves
  QList<struct ConfigButton> slowInCurvesConfigs = {
    { "jvePilot.settings.slowInCurves.speedRatio",
      0.1, 2,
      "Speed Ratio",
      "Default: 1.0, Min: 0.1, Max: 2.0\n"
        "Use this to tune the speed in curves to your liking."
        "\nFor example, 1.2 to go 20% faster and .8 to go 20% slower across all curvatures."
    }
    ,{ "jvePilot.settings.slowInCurves.speedDropOff",
      1, 3,
      "Speed Drop Off",
      "Default: 2.0\n"
        "Experimental. Lower this value to decrease how quickly speed drops as the curve increases."
        "\nTo go faster in turns at higher speeds, decrease this value.  To compensate for this change, you may need to increase the Speed Ratio."
    }
  };
  addItem(new ParamControl("jvePilot.settings.slowInCurves",
                                  "Slow in Curves",
                                  "jvePilot will slow in curves so that you don't have to.",
                                  "../assets/jvepilot/settings/icon_slow_in_curves.png",
                                  this,
                                  &slowInCurvesConfigs));
  // autoFollow
  QList<struct ConfigButton> autoFollowConfigs = {
    { "jvePilot.settings.autoFollow.speed1-2Bars",
      0, 300,
      "1-2 Bar Change Over (MPH)",
      "Default: 15 mph, Min: 0, Max: 300\n"
        "Use this to change the speed at which Auto Follow will switch between one to two bars."
    },
    { "jvePilot.settings.autoFollow.speed2-3Bars",
      0, 300,
      "2-3 Bar Change Over (MPH)",
      "Default: 30 mph, Min: 0, Max: 300\n"
        "Use this to change the speed at which Auto Follow will switch between two to three bars."
    },
    { "jvePilot.settings.autoFollow.speed3-4Bars",
      0, 300,
      "3-4 Bar Change Over (MPH)",
      "Default: 65 mph, Min: 0, Max: 300\n"
        "Use this to change the speed at which Auto Follow will switch between three to four bars."
    },
    { "jvePilot.settings.autoFollow.relaxed",
      1, 2,
      "Relaxed Profile Follow Time (seconds)",
      "Default: 1.80, Min: 1, Max: 2\n"
        "How much time the model stays behind the lead car in seconds in relaxed mode."
    },
    { "jvePilot.settings.autoFollow.standard",
      1, 2,
      "Standard Profile Follow Time (seconds)",
      "Default: 1.40, Min: 1, Max: 2\n"
        "How much time the model stays behind the lead car in seconds in standard mode."
    },
    { "jvePilot.settings.autoFollow.aggressive",
      1, 2,
      "Aggressive Profile Follow Time (seconds)",
      "Default: 1.00, Min: 1, Max: 2\n"
        "How much time the model stays behind the lead car in seconds in aggressive mode."
    }
  };
  addItem(new ParamControl("jvePilot.settings.autoFollow",
                           "Start with Auto Follow Enabled",
                           "When enabled, jvePilot will enable Auto Follow on the start of every drive.",
                           "../assets/jvepilot/settings/icon_auto_follow.png",
                           this,
                           &autoFollowConfigs));

  // Always One Lateral Control
  addItem(new ParamControl("jvePilot.settings.steer.aolc",
                           "Always On Lateral Control",
                           "When enabled and ACC is ready, jvePilot will steer even if ACC isn't active",
                           "../assets/img_chffr_wheel.png",
                           this));

  // Blindspot Lane Highlight Toggle
  addItem(new ParamControl("jvePilot.settings.blindspotHighlight",
                           "Blindspot Lane Highlight",
                           "When a vehicle is detected in your blindspot, the adjacent lane line will turn bold red.",
                           "../assets/offroad/img_circled_check.png",
                           this));

  // Auto enable ACC on start
  addItem(new ParamControl("jvePilot.settings.autoEnableAcc",
                           "ACC Ready on Start",
                           "When enabled, ACC will be made ready on start without having to press the ACC On/Off button",
                           "../assets/img_circled_check.png",
                           this));

  // reverseAccSpeedChange
  addItem(new ParamControl("jvePilot.settings.reverseAccSpeedChange",
                           "Reverse ACC +/- Speeds",
                           "When enabled, quick pressing the ACC +/- buttons changes the speed in 5 increments."
                           " Hold a little longer to change by 1."
                           " Disable to keep stock setting.",
                           "../assets/jvepilot/settings/icon_acc_speed_change.png",
                           this));

  // audioAlertOnSteeringLoss
  addItem(new ParamControl("jvePilot.settings.audioAlertOnSteeringLoss",
                           "Audio Alert on Steering Loss",
                           "When enabled, jvePilot will play an alert when speed it too low to steer.",
                           "../assets/jvepilot/settings/alert_steer_loss.png",
                           this));

  // accEco
  QList<struct ConfigButton> ecoConfigs = {
    { "jvePilot.settings.accEco.speedAheadLevel1",
      1, 100,
      "Keep ahead at Eco 1 (MPH)",
      "Default: 7 mph, Min: 1, Max: 100\n"
        "The higher the number the more acceleration that occurs."
    },
    { "jvePilot.settings.accEco.speedAheadLevel2",
      1, 100,
      "Keep ahead at Eco 2 (MPH)",
      "Default: 5 mph, Min: 1, Max: 100\n"
        "The higher the number the more acceleration that occurs."
    },
    { "jvePilot.settings.accEco.reductionRate",
      0, 2,
      "Eco speed reduction rate",
      "Default: 0, Min: 0, Max: 1\n"
        "For each MPH above 20, this amount is removed from the Eco keep ahead speed."
    },
    { "jvePilot.settings.accEco.longAccelLevel1",
      0, 2,
      "Max acceleration at Eco 1 (m/s²)",
      "Default: 1 m/s², Min: 0, Max: 2\n"
        "LONG CONTROL ONLY\n"
        "The higher the number the more acceleration that occurs."
    },
    { "jvePilot.settings.accEco.longAccelLevel2",
      0, 2,
      "Max acceleration at Eco 2 (m/s²)",
      "Default: 1.5 m/s² mph, Min: 0, Max: 2\n"
        "LONG CONTROL ONLY\n"
        "The higher the number the more acceleration that occurs."
    }
  };
  addItem(new LabelControl("ACC Eco",
                           "",
                           "Use these settings to tune how much acceleration occurs by limiting how much ACC is set above your current speed.",
                           this,
                           "../assets/jvepilot/settings/icon_acc_eco.png",
                           &ecoConfigs));

  // Brake Hold
  addItem(new ParamControl("jvePilot.settings.brakeHold",
                           "Brake Hold (Jeeps Only)",
                           "Say stopped when ACC stops behind a lead car then resume when lead car resumes.",
                           "../assets/jvepilot/settings/icon_brake_hold.svg",
                           this));


  // misc
  QList<struct ConfigButton> miscConfigs = {
    { "jvePilot.settings.deviceOffset",
      -2, 2,
      "Device Offset",
      "Default: 0.00 meters, Min: -2.00, Max: 2.00\n"
        "Compensate for mounting your device off-center in the windshield."
        "\nFor example, 0.04 if your device is 4cm left of center."
        "\nNOTE: This is not how far the CAMERA is off-center, but how far the MOUNT/DEVICE is off-center."
    }
  };
  addItem(new LabelControl("jvePilot Control Settings",
                                  "",
                                  "Use these settings to tune some of jvePilot's control settings.",
                                  this,
                                  "../assets/jvepilot/settings/icon_misc.png",
                                  &miscConfigs));

  // Minimum Steer Check
  addItem(new ParamControl("jvePilot.settings.steer.noMinimum",
                           "ADVANCED: Speed Spoofing Mod",
                           "If you have a mod that allows OP to steering down to a stop, enable this.",
                           "../assets/jvepilot/settings/icon_wp_mod.png",
                           this));
  // PID Controller
  addItem(new ParamControl("jvePilot.settings.steer.pid",
                           "ADVANCED: PID Controller",
                           "Use the PID controller instead of torque for steering.",
                           "../assets/img_chffr_wheel.png",
                           this));
  // Vision Only
  addItem(new ParamControl("jvePilot.settings.visionOnly",
                           "ADVANCED: Vision only",
                           "Enable this setting if you are seeing the lead car yellow triangle acting erratically.",
                           "../assets/jvepilot/settings/icon_eye.png",
                           this));

  // Reverse Radar
  addItem(new ParamControl("jvePilot.settings.reverseRadar",
                           "ADVANCED: Reverse Radar X Axis",
                           "Enable this setting if the lead car yellow triangle is reversed on the X axis",
                           "../assets/offroad/icon_calibration.png",
                           this));

  // Make/Model/Year
  targetCarBtn = new ButtonControl(tr("Target Car"), tr("SELECT"));
  connect(targetCarBtn, &ButtonControl::clicked, [=]() {
    QStringList cars = {
        "Auto detect",
        "Grand Cherokee 2018",
        "Grand Cherokee 2019",
        "Pacifica Hybrid 2017",
        "Pacifica Hybrid 2018",
        "Pacifica Hybrid 2019",
        "Pacifica 2018",
        "Pacifica 2020",
        "Durango",
    };

    QString cur = QString::fromStdString(params.get("jvePilot.settings.selectedCar"));
    QString selection = MultiOptionDialog::getSelection(tr("Select a car"), cars, cur, this);
    if (!selection.isEmpty()) {
      params.put("jvePilot.settings.selectedCar", selection.toStdString());
      targetCarBtn->setValue(QString::fromStdString(params.get("jvePilot.settings.selectedCar")));
    }
  });
  addItem(targetCarBtn);
}

TogglesPanel::TogglesPanel(SettingsWindow *parent) : ListWidget(parent) {
  // param, title, desc, icon, restart needed
  std::vector<std::tuple<QString, QString, QString, QString, bool>> toggle_defs{
    {
      "OpenpilotEnabledToggle",
      tr("Enable openpilot"),
      tr("Use the openpilot system for adaptive cruise control and lane keep driver assistance. Your attention is required at all times to use this feature."),
      "../assets/icons/chffr_wheel.png",
      true,
    },
    {
      "ExperimentalMode",
      tr("Experimental Mode"),
      tr(" "),
      "../assets/icons/experimental_white.svg",
      false,
    },
    {
      "DisengageOnAccelerator",
      tr("Disengage on Accelerator Pedal"),
      tr("When enabled, pressing the accelerator pedal will disengage openpilot."),
      "../assets/icons/disengage_on_accelerator.svg",
      false,
    },
    {
      "IsLdwEnabled",
      tr("Enable Lane Departure Warnings"),
      tr("Receive alerts to steer back into the lane when your vehicle drifts over a detected lane line without a turn signal activated while driving over 31 mph (50 km/h)."),
      "../assets/icons/warning.png",
      false,
    },
    {
      "AlwaysOnDM",
      tr("Always-On Driver Monitoring"),
      tr("Enable driver monitoring even when openpilot is not engaged."),
      "../assets/icons/monitoring.png",
      false,
    },
    {
      "RecordFront",
      tr("Record and Upload Driver Camera"),
      tr("Upload data from the driver facing camera and help improve the driver monitoring algorithm."),
      "../assets/icons/monitoring.png",
      true,
    },
    {
      "RecordAudio",
      tr("Record and Upload Microphone Audio"),
      tr("Record and store microphone audio while driving. The audio will be included in the dashcam video in comma connect."),
      "../assets/icons/microphone.png",
      true,
    },
    {
      "IsMetric",
      tr("Use Metric System"),
      tr("Display speed in km/h instead of mph."),
      "../assets/icons/metric.png",
      false,
    },
  };


  std::vector<QString> longi_button_texts{tr("Aggressive"), tr("Standard"), tr("Relaxed")};
  long_personality_setting = new ButtonParamControl("LongitudinalPersonality", tr("Driving Personality"),
                                          tr("Standard is recommended. In aggressive mode, openpilot will follow lead cars closer and be more aggressive with the gas and brake. "
                                             "In relaxed mode openpilot will stay further away from lead cars. On supported cars, you can cycle through these personalities with "
                                             "your steering wheel distance button."),
                                          "../assets/icons/speed_limit.png",
                                          longi_button_texts);

  // set up uiState update for personality setting
  QObject::connect(uiState(), &UIState::uiUpdate, this, &TogglesPanel::updateState);

  for (auto &[param, title, desc, icon, needs_restart] : toggle_defs) {
    auto toggle = new ParamControl(param, title, desc, icon, this);

    bool locked = params.getBool((param + "Lock").toStdString());
    toggle->setEnabled(!locked);

    if (needs_restart && !locked) {
      toggle->setDescription(toggle->getDescription() + tr(" Changing this setting will restart openpilot if the car is powered on."));

      QObject::connect(uiState(), &UIState::engagedChanged, [toggle](bool engaged) {
        toggle->setEnabled(!engaged);
      });

      QObject::connect(toggle, &ParamControl::toggleFlipped, [=](bool state) {
        params.putBool("OnroadCycleRequested", true);
      });
    }

    addItem(toggle);
    toggles[param.toStdString()] = toggle;

    // insert longitudinal personality after NDOG toggle
    if (param == "DisengageOnAccelerator") {
      addItem(long_personality_setting);
    }
  }

  // Toggles with confirmation dialogs
  toggles["ExperimentalMode"]->setActiveIcon("../assets/icons/experimental.svg");
  toggles["ExperimentalMode"]->setConfirmation(true, true);
}

void TogglesPanel::updateState(const UIState &s) {
  const SubMaster &sm = *(s.sm);

  if (sm.updated("selfdriveState")) {
    auto personality = sm["selfdriveState"].getSelfdriveState().getPersonality();
    if (personality != s.scene.personality && s.scene.started && isVisible()) {
      long_personality_setting->setCheckedButton(static_cast<int>(personality));
    }
    uiState()->scene.personality = personality;
  }
}

void TogglesPanel::expandToggleDescription(const QString &param) {
  toggles[param.toStdString()]->showDescription();
}

void TogglesPanel::scrollToToggle(const QString &param) {
  if (auto it = toggles.find(param.toStdString()); it != toggles.end()) {
    auto scroll_area = qobject_cast<QScrollArea*>(parent()->parent());
    if (scroll_area) {
      scroll_area->ensureWidgetVisible(it->second);
    }
  }
}

void TogglesPanel::showEvent(QShowEvent *event) {
  updateToggles();
}

void TogglesPanel::updateToggles() {
  auto experimental_mode_toggle = toggles["ExperimentalMode"];
  const QString e2e_description = QString("%1<br>"
                                          "<h4>%2</h4><br>"
                                          "%3<br>"
                                          "<h4>%4</h4><br>"
                                          "%5<br>")
                                  .arg(tr("openpilot defaults to driving in <b>chill mode</b>. Experimental mode enables <b>alpha-level features</b> that aren't ready for chill mode. Experimental features are listed below:"))
                                  .arg(tr("End-to-End Longitudinal Control"))
                                  .arg(tr("Let the driving model control the gas and brakes. openpilot will drive as it thinks a human would, including stopping for red lights and stop signs. "
                                          "Since the driving model decides the speed to drive, the set speed will only act as an upper bound. This is an alpha quality feature; "
                                          "mistakes should be expected."))
                                  .arg(tr("New Driving Visualization"))
                                  .arg(tr("The driving visualization will transition to the road-facing wide-angle camera at low speeds to better show some turns. The Experimental mode logo will also be shown in the top right corner."));

  //const bool is_release = paramms.getBool("IsReleaseBranch");
  auto cp_bytes = params.get("CarParamsPersistent");
  if (!cp_bytes.empty()) {
    AlignedBuffer aligned_buf;
    capnp::FlatArrayMessageReader cmsg(aligned_buf.align(cp_bytes.data(), cp_bytes.size()));
    cereal::CarParams::Reader CP = cmsg.getRoot<cereal::CarParams>();

    if (hasLongitudinalControl(CP)) {
      // normal description and toggle
      experimental_mode_toggle->setEnabled(true);
      experimental_mode_toggle->setDescription(e2e_description);
      long_personality_setting->setEnabled(true);
    } else {
      // no long for now
      experimental_mode_toggle->setEnabled(false);
      long_personality_setting->setEnabled(false);
      params.remove("ExperimentalMode");

      const QString unavailable = tr("Experimental mode is currently unavailable on this car since the car's stock ACC is used for longitudinal control.");

      QString long_desc = unavailable + " " + \
                          tr("openpilot longitudinal control may come in a future update.");
      if (true) {
        if (false) {
          long_desc = unavailable + " " + tr("An alpha version of openpilot longitudinal control can be tested, along with Experimental mode, on non-release branches.");
        } else {
          long_desc = tr("Enable the openpilot longitudinal control (alpha) toggle to allow Experimental mode.");
        }
      }
      experimental_mode_toggle->setDescription("<b>" + long_desc + "</b><br><br>" + e2e_description);
    }

    experimental_mode_toggle->refresh();
  } else {
    experimental_mode_toggle->setDescription(e2e_description);
  }
}

DevicePanel::DevicePanel(SettingsWindow *parent) : ListWidget(parent) {
  setSpacing(50);
  addItem(new LabelControl(tr("Dongle ID"), getDongleId().value_or(tr("N/A"))));
  addItem(new LabelControl(tr("Serial"), params.get("HardwareSerial").c_str()));

  pair_device = new ButtonControl(tr("Pair Device"), tr("PAIR"),
                                  tr("Pair your device with comma connect (connect.comma.ai) and claim your comma prime offer."));
  connect(pair_device, &ButtonControl::clicked, [=]() {
    PairingPopup popup(this);
    popup.exec();
  });
  addItem(pair_device);

  // offroad-only buttons

  auto dcamBtn = new ButtonControl(tr("Driver Camera"), tr("PREVIEW"),
                                   tr("Preview the driver facing camera to ensure that driver monitoring has good visibility. (vehicle must be off)"));
  connect(dcamBtn, &ButtonControl::clicked, [=]() { emit showDriverView(); });
  addItem(dcamBtn);

  resetCalibBtn = new ButtonControl(tr("Reset Calibration"), tr("RESET"), "");
  connect(resetCalibBtn, &ButtonControl::showDescriptionEvent, this, &DevicePanel::updateCalibDescription);
  connect(resetCalibBtn, &ButtonControl::clicked, [&]() {
    if (!uiState()->engaged()) {
      if (ConfirmationDialog::confirm(tr("Are you sure you want to reset calibration?"), tr("Reset"), this)) {
        // Check engaged again in case it changed while the dialog was open
        if (!uiState()->engaged()) {
          params.remove("CalibrationParams");
          params.remove("LiveTorqueParameters");
          params.remove("LiveParameters");
          params.remove("LiveParametersV2");
          params.remove("LiveDelay");
          params.putBool("OnroadCycleRequested", true);
          updateCalibDescription();
        }
      }
    } else {
      ConfirmationDialog::alert(tr("Disengage to Reset Calibration"), this);
    }
  });
  addItem(resetCalibBtn);

  auto retrainingBtn = new ButtonControl(tr("Review Training Guide"), tr("REVIEW"), tr("Review the rules, features, and limitations of openpilot"));
  connect(retrainingBtn, &ButtonControl::clicked, [=]() {
    if (ConfirmationDialog::confirm(tr("Are you sure you want to review the training guide?"), tr("Review"), this)) {
      emit reviewTrainingGuide();
    }
  });
  addItem(retrainingBtn);

  if (Hardware::TICI()) {
    auto regulatoryBtn = new ButtonControl(tr("Regulatory"), tr("VIEW"), "");
    connect(regulatoryBtn, &ButtonControl::clicked, [=]() {
      const std::string txt = util::read_file("../assets/offroad/fcc.html");
      ConfirmationDialog::rich(QString::fromStdString(txt), this);
    });
    addItem(regulatoryBtn);
  }

  auto translateBtn = new ButtonControl(tr("Change Language"), tr("CHANGE"), "");
  connect(translateBtn, &ButtonControl::clicked, [=]() {
    QMap<QString, QString> langs = getSupportedLanguages();
    QString selection = MultiOptionDialog::getSelection(tr("Select a language"), langs.keys(), langs.key(uiState()->language), this);
    if (!selection.isEmpty()) {
      // put language setting, exit Qt UI, and trigger fast restart
      params.put("LanguageSetting", langs[selection].toStdString());
      qApp->exit(18);
      watchdog_kick(0);
    }
  });
  addItem(translateBtn);

  QObject::connect(uiState()->prime_state, &PrimeState::changed, [this] (PrimeState::Type type) {
    pair_device->setVisible(type == PrimeState::PRIME_TYPE_UNPAIRED);
  });
  QObject::connect(uiState(), &UIState::offroadTransition, [=](bool offroad) {
    for (auto btn : findChildren<ButtonControl *>()) {
      if (btn != pair_device && btn != resetCalibBtn) {
        btn->setEnabled(offroad);
      }
    }
  });

  // power buttons
  QHBoxLayout *power_layout = new QHBoxLayout();
  power_layout->setSpacing(30);

  QPushButton *reboot_btn = new QPushButton(tr("Reboot"));
  reboot_btn->setObjectName("reboot_btn");
  power_layout->addWidget(reboot_btn);
  QObject::connect(reboot_btn, &QPushButton::clicked, this, &DevicePanel::reboot);

  QPushButton *poweroff_btn = new QPushButton(tr("Power Off"));
  poweroff_btn->setObjectName("poweroff_btn");
  power_layout->addWidget(poweroff_btn);
  QObject::connect(poweroff_btn, &QPushButton::clicked, this, &DevicePanel::poweroff);

  if (!Hardware::PC()) {
    connect(uiState(), &UIState::offroadTransition, poweroff_btn, &QPushButton::setVisible);
  }

  setStyleSheet(R"(
    #reboot_btn { height: 120px; border-radius: 15px; background-color: #393939; }
    #reboot_btn:pressed { background-color: #4a4a4a; }
    #poweroff_btn { height: 120px; border-radius: 15px; background-color: #E22C2C; }
    #poweroff_btn:pressed { background-color: #FF2424; }
  )");
  addItem(power_layout);
}

void DevicePanel::updateCalibDescription() {
  QString desc = tr("openpilot requires the device to be mounted within 4° left or right and within 5° up or 9° down.");
  std::string calib_bytes = params.get("CalibrationParams");
  if (!calib_bytes.empty()) {
    try {
      AlignedBuffer aligned_buf;
      capnp::FlatArrayMessageReader cmsg(aligned_buf.align(calib_bytes.data(), calib_bytes.size()));
      auto calib = cmsg.getRoot<cereal::Event>().getLiveCalibration();
      if (calib.getCalStatus() != cereal::LiveCalibrationData::Status::UNCALIBRATED) {
        double pitch = calib.getRpyCalib()[1] * (180 / M_PI);
        double yaw = calib.getRpyCalib()[2] * (180 / M_PI);
        desc += tr(" Your device is pointed %1° %2 and %3° %4.")
                    .arg(QString::number(std::abs(pitch), 'g', 1), pitch > 0 ? tr("down") : tr("up"),
                         QString::number(std::abs(yaw), 'g', 1), yaw > 0 ? tr("left") : tr("right"));
      }
    } catch (kj::Exception) {
      qInfo() << "invalid CalibrationParams";
    }
  }

  int lag_perc = 0;
  std::string lag_bytes = params.get("LiveDelay");
  if (!lag_bytes.empty()) {
    try {
      AlignedBuffer aligned_buf;
      capnp::FlatArrayMessageReader cmsg(aligned_buf.align(lag_bytes.data(), lag_bytes.size()));
      lag_perc = cmsg.getRoot<cereal::Event>().getLiveDelay().getCalPerc();
    } catch (kj::Exception) {
      qInfo() << "invalid LiveDelay";
    }
  }
  if (lag_perc < 100) {
    desc += tr("\n\nSteering lag calibration is %1% complete.").arg(lag_perc);
  } else {
    desc += tr("\n\nSteering lag calibration is complete.");
  }

  std::string torque_bytes = params.get("LiveTorqueParameters");
  if (!torque_bytes.empty()) {
    try {
      AlignedBuffer aligned_buf;
      capnp::FlatArrayMessageReader cmsg(aligned_buf.align(torque_bytes.data(), torque_bytes.size()));
      auto torque = cmsg.getRoot<cereal::Event>().getLiveTorqueParameters();
      // don't add for non-torque cars
      if (torque.getUseParams()) {
        int torque_perc = torque.getCalPerc();
        if (torque_perc < 100) {
          desc += tr(" Steering torque response calibration is %1% complete.").arg(torque_perc);
        } else {
          desc += tr(" Steering torque response calibration is complete.");
        }
      }
    } catch (kj::Exception) {
      qInfo() << "invalid LiveTorqueParameters";
    }
  }

  desc += "\n\n";
  desc += tr("openpilot is continuously calibrating, resetting is rarely required. "
             "Resetting calibration will restart openpilot if the car is powered on.");
  resetCalibBtn->setDescription(desc);
}

void DevicePanel::reboot() {
  if (!uiState()->engaged()) {
    if (ConfirmationDialog::confirm(tr("Are you sure you want to reboot?"), tr("Reboot"), this)) {
      // Check engaged again in case it changed while the dialog was open
      if (!uiState()->engaged()) {
        params.putBool("DoReboot", true);
      }
    }
  } else {
    ConfirmationDialog::alert(tr("Disengage to Reboot"), this);
  }
}

void DevicePanel::poweroff() {
  if (!uiState()->engaged()) {
    if (ConfirmationDialog::confirm(tr("Are you sure you want to power off?"), tr("Power Off"), this)) {
      // Check engaged again in case it changed while the dialog was open
      if (!uiState()->engaged()) {
        params.putBool("DoShutdown", true);
      }
    }
  } else {
    ConfirmationDialog::alert(tr("Disengage to Power Off"), this);
  }
}

void SettingsWindow::showEvent(QShowEvent *event) {
  setCurrentPanel(0);
}

void SettingsWindow::setCurrentPanel(int index, const QString &param) {
  if (!param.isEmpty()) {
    // Check if param ends with "Panel" to determine if it's a panel name
    if (param.endsWith("Panel")) {
      QString panelName = param;
      panelName.chop(5); // Remove "Panel" suffix

      // Find the panel by name
      for (int i = 0; i < nav_btns->buttons().size(); i++) {
        if (nav_btns->buttons()[i]->text() == tr(panelName.toStdString().c_str())) {
          index = i;
          break;
        }
      }
    } else {
      emit expandToggleDescription(param);
      emit scrollToToggle(param);
    }
  }

  panel_widget->setCurrentIndex(index);
  nav_btns->buttons()[index]->setChecked(true);
}

SettingsWindow::SettingsWindow(QWidget *parent) : QFrame(parent) {

  // setup two main layouts
  sidebar_widget = new QWidget;
  QVBoxLayout *sidebar_layout = new QVBoxLayout(sidebar_widget);
  panel_widget = new QStackedWidget();

  // close button
  QPushButton *close_btn = new QPushButton(tr("×"));
  close_btn->setStyleSheet(R"(
    QPushButton {
      font-size: 140px;
      padding-bottom: 20px;
      border-radius: 85px;
      background-color: #292929;
      font-weight: 400;
    }
    QPushButton:pressed {
      background-color: #3B3B3B;
    }
  )");
  close_btn->setFixedSize(170, 170);
  sidebar_layout->addSpacing(45);
  sidebar_layout->addWidget(close_btn, 0, Qt::AlignCenter);
  QObject::connect(close_btn, &QPushButton::clicked, this, &SettingsWindow::closeSettings);

  // setup panels
  DevicePanel *device = new DevicePanel(this);
  QObject::connect(device, &DevicePanel::reviewTrainingGuide, this, &SettingsWindow::reviewTrainingGuide);
  QObject::connect(device, &DevicePanel::showDriverView, this, &SettingsWindow::showDriverView);

  TogglesPanel *toggles = new TogglesPanel(this);
  QObject::connect(this, &SettingsWindow::expandToggleDescription, toggles, &TogglesPanel::expandToggleDescription);
  QObject::connect(this, &SettingsWindow::scrollToToggle, toggles, &TogglesPanel::scrollToToggle);

  auto networking = new Networking(this);
  QObject::connect(uiState()->prime_state, &PrimeState::changed, networking, &Networking::setPrimeType);

  QList<QPair<QString, QWidget *>> panels = {
    {tr("Device"), device},
    {tr("Network"), networking},
    {tr("Toggles"), toggles},
    {tr("jvePilot"), new JvePilotTogglesPanel(this)},
    {tr("Software"), new SoftwarePanel(this)},
    {tr("Firehose"), new FirehosePanel(this)},
    {tr("Developer"), new DeveloperPanel(this)},
  };

  nav_btns = new QButtonGroup(this);
  for (auto &[name, panel] : panels) {
    QPushButton *btn = new QPushButton(name);
    btn->setCheckable(true);
    btn->setChecked(nav_btns->buttons().size() == 0);
    btn->setStyleSheet(R"(
      QPushButton {
        color: grey;
        border: none;
        background: none;
        font-size: 60px;
        font-weight: 500;
      }
      QPushButton:checked {
        color: white;
      }
      QPushButton:pressed {
        color: #ADADAD;
      }
    )");
    btn->setSizePolicy(QSizePolicy::Preferred, QSizePolicy::Expanding);
    nav_btns->addButton(btn);
    sidebar_layout->addWidget(btn, 0, Qt::AlignRight);

    const int lr_margin = name != tr("Network") ? 50 : 0;  // Network panel handles its own margins
    panel->setContentsMargins(lr_margin, 25, lr_margin, 25);

    ScrollView *panel_frame = new ScrollView(panel, this);
    panel_widget->addWidget(panel_frame);

    QObject::connect(btn, &QPushButton::clicked, [=, w = panel_frame]() {
      btn->setChecked(true);
      panel_widget->setCurrentWidget(w);
    });
  }
  sidebar_layout->setContentsMargins(50, 50, 100, 50);

  // main settings layout, sidebar + main panel
  QHBoxLayout *main_layout = new QHBoxLayout(this);

  sidebar_widget->setFixedWidth(500);
  main_layout->addWidget(sidebar_widget);
  main_layout->addWidget(panel_widget);

  setStyleSheet(R"(
    * {
      color: white;
      font-size: 50px;
    }
    SettingsWindow {
      background-color: black;
    }
    QStackedWidget, ScrollView {
      background-color: #292929;
      border-radius: 30px;
    }
  )");
}
