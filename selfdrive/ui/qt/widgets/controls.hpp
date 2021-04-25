#pragma once

#include <QFrame>
#include <QHBoxLayout>
#include <QLabel>
#include <QPushButton>
#include <QVBoxLayout>

#include "common/params.h"
#include "toggle.hpp"

QFrame *horizontal_line(QWidget *parent = nullptr);

// config for a widget
struct ConfigButton {
  public:
  std::string param;
  std::string default_value;
  float min;
  float max;
  QString title;
  QString text; 
};

class AbstractControl : public QFrame {
  Q_OBJECT

protected:
  AbstractControl(const QString &title, const QString &desc = "", const QString &icon = "", QList<struct ConfigButton> *btns = {}, QWidget *parent = nullptr);

  QSize minimumSizeHint() const override {
    QSize size = QFrame::minimumSizeHint();
    size.setHeight(120);
    return size;
  };

  QHBoxLayout *hlayout;
  QPushButton *title_label;
  QLabel *description = nullptr;
};

// widget to display a value
class LabelControl : public AbstractControl {
  Q_OBJECT

public:
  LabelControl(const QString &title, const QString &text, const QString &desc = "", QList<struct ConfigButton> *btns = {}, const QString &icon = "", QWidget *parent = nullptr) : AbstractControl(title, desc, icon, btns, parent) {
    label.setText(text);
    label.setAlignment(Qt::AlignRight | Qt::AlignVCenter);
    hlayout->addWidget(&label);
  }
  void setText(const QString &text) { label.setText(text); }

private:
  QLabel label;
};

// widget for a button with a label
class ButtonControl : public AbstractControl {
  Q_OBJECT

public:
  template <typename Functor>
  ButtonControl(const QString &title, const QString &text, const QString &desc, Functor functor, const QString &icon = "", QList<struct ConfigButton> *btns = {}, QWidget *parent = nullptr) : AbstractControl(title, desc, icon, btns, parent) {
    btn.setText(text);
    btn.setStyleSheet(R"(
      QPushButton {
        padding: 0;
        border-radius: 50px;
        font-size: 35px;
        font-weight: 500;
        color: #E4E4E4;
        background-color: #393939;
      }
      QPushButton:disabled {
        color: #33E4E4E4;
      }
    )");
    btn.setFixedSize(250, 100);
    QObject::connect(&btn, &QPushButton::released, functor);
    hlayout->addWidget(&btn);
  }
  void setLabel(const QString &text) { title_label->setText(text); }
  void setText(const QString &text) { btn.setText(text); }
  template <typename Functor>
  void released(Functor functor) { QObject::connect(&btn, &QPushButton::released, functor); }

public slots:
  void setEnabled(bool enabled) {
    btn.setEnabled(enabled);
  };

private:
  QPushButton btn;
};

class ToggleControl : public AbstractControl {
  Q_OBJECT

public:
  ToggleControl(const QString &title, const QString &desc = "", const QString &icon = "", const bool state = false, QList<struct ConfigButton> *btns = {}, QWidget *parent = nullptr) : AbstractControl(title, desc, icon, btns, parent) {
    toggle.setFixedSize(150, 100);
    if (state) {
      toggle.togglePosition();
    }
    hlayout->addWidget(&toggle);
    QObject::connect(&toggle, &Toggle::stateChanged, this, &ToggleControl::toggleFlipped);
  }

  void setEnabled(bool enabled) { toggle.setEnabled(enabled); }

signals:
  void toggleFlipped(bool state);

protected:
  Toggle toggle;
};

// widget to toggle params
class ParamControl : public ToggleControl {
  Q_OBJECT

public:
  ParamControl(const QString &param, const QString &title, const QString &desc, const QString &icon, QList<struct ConfigButton> *btns = {}, QWidget *parent = nullptr) : ToggleControl(title, desc, icon, false, btns, parent) {
    // set initial state from param
    if (Params().read_db_bool(param.toStdString().c_str())) {
      toggle.togglePosition();
    }
    QObject::connect(this, &ToggleControl::toggleFlipped, [=](int state) {
      char value = state ? '1' : '0';
      Params().write_db_value(param.toStdString().c_str(), &value, 1);
    });
  }
};
