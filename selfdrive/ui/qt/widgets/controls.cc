#include "controls.hpp"
#include "widgets/input.hpp"
#include "selfdrive/hardware/hw.h"

QFrame *horizontal_line(QWidget *parent) {
  QFrame *line = new QFrame(parent);
  line->setFrameShape(QFrame::StyledPanel);
  line->setStyleSheet(R"(
    margin-left: 40px;
    margin-right: 40px;
    border-width: 1px;
    border-bottom-style: solid;
    border-color: gray;
  )");
  line->setFixedHeight(2);
  return line;
}

AbstractControl::AbstractControl(const QString &title, const QString &desc, const QString &icon, QList<struct ConfigButton> *btns, QWidget *parent) : QFrame(parent) {
  QVBoxLayout *vlayout = new QVBoxLayout();
  vlayout->setMargin(0);

  hlayout = new QHBoxLayout;
  hlayout->setMargin(0);
  hlayout->setSpacing(20);

  // left icon
  if (!icon.isEmpty()) {
    QPixmap pix(icon);
    QLabel *icon = new QLabel();
    icon->setPixmap(pix.scaledToWidth(80, Qt::SmoothTransformation));
    icon->setSizePolicy(QSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed));
    hlayout->addWidget(icon);
  }

  // title
  title_label = new QPushButton(title);
  title_label->setStyleSheet("font-size: 50px; font-weight: 400; text-align: left;");
  hlayout->addWidget(title_label);

  vlayout->addLayout(hlayout);

  QVBoxLayout *config_layout = new QVBoxLayout;

  bool hasToggle = false;
  // description
  if (!desc.isEmpty()) {
    hasToggle = true;
    description = new QLabel(desc);
    description->setContentsMargins(40, 20, 40, 20);
    description->setStyleSheet("font-size: 40px; color:grey");
    description->setWordWrap(true);
    config_layout->addWidget(description);
  }

  if (btns && btns->size() > 0) {
    hasToggle = true;
    for (int i = 0; i < btns->size(); i++) {
      config_layout->addWidget(horizontal_line());
      const ConfigButton btn = btns->at(i);

      const auto value = Params().get(btn.param);
      const auto title = QString::fromStdString(btn.title.toStdString() + ": " + value);
      const auto b = new ButtonControl(title, "CHANGE", btn.text, [=]() {});
      b->released([=]() { 
          auto set_value = InputDialog::getConfigDecimal(title, value);
          if (set_value.length() > 0) {
            Params().write_db_value(btn.param, set_value.toStdString());
            b->setLabel(QString::fromStdString(btn.title.toStdString() + ": " + set_value.toStdString()));
          } 
        });
      b->setContentsMargins(40, 20, 0, 0);

      config_layout->addWidget(b);      
    }
  }

  if (hasToggle) {
    QWidget *config_widget = new QWidget;
    config_widget->setVisible(false);
    config_widget->setLayout(config_layout);
    connect(title_label, &QPushButton::clicked, [=]() {
        config_widget->setVisible(!config_widget->isVisible());
    });
    vlayout->addWidget(config_widget);
  }

  setLayout(vlayout);
  setStyleSheet("background-color: transparent;");
}
