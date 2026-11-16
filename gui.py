import sys

import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets


APP_STYLE = """
QWidget { background: #101820; color: #eef4f6; font-family: sans-serif; font-size: 16px; }
QLabel#muted { color: #9aabb5; }
QLabel#eyebrow { color: #9aabb5; font-size: 13px; font-weight: 600; }
QLabel#temperature { font-size: 32px; font-weight: 700; }
QLabel#pageTitle { font-size: 24px; font-weight: 700; }
QFrame#card, QFrame#panel { background: #1b2933; border: 1px solid #2d414e; border-radius: 12px; }
QPushButton { background: #2b414e; border: 1px solid #3c5664; border-radius: 9px; min-height: 48px; padding: 0 16px; font-weight: 600; }
QPushButton:hover { background: #385362; }
QPushButton:checked { border: 2px solid #eef4f6; }
QPushButton#primary { background: #147d78; border-color: #1b9b91; }
QPushButton#primary:hover { background: #19958d; }
QPushButton#danger { background: #923d3c; border-color: #b94d48; }
QPushButton#warning { background: #8a6424; border-color: #c49336; }
QComboBox, QDoubleSpinBox { background: #0e171d; border: 1px solid #3c5664; border-radius: 8px; min-height: 48px; padding: 0 10px; font-size: 20px; }
QComboBox QAbstractItemView { background: #1b2933; selection-background-color: #147d78; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 28px; }
QProgressBar { background: #0e171d; border: 0; border-radius: 7px; min-height: 14px; text-align: center; }
QProgressBar::chunk { background: #24b49e; border-radius: 7px; }
"""

# A simple severity palette used consistently for every temperature card.
COLORS = {
    "cool": ("#18344a", "#62b9ee"),
    "normal": ("#193b35", "#74d5ad"),
    "warning": ("#49391d", "#f1bd61"),
    "critical": ("#4a2528", "#ff827b"),
    "unknown": ("#26333b", "#aab8bf"),
}


class SensorCard(QtWidgets.QFrame):
    def __init__(self, name, thresholds):
        super().__init__()
        self.sensor_name = name
        self.thresholds = thresholds
        self.setObjectName("card")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(4)

        self.name_label = QtWidgets.QLabel(name.replace("_", " "))
        self.name_label.setObjectName("eyebrow")
        self.value_label = QtWidgets.QLabel("--.- °C")
        self.value_label.setObjectName("temperature")
        self.state_label = QtWidgets.QLabel("Waiting for reading")
        self.state_label.setObjectName("muted")
        layout.addWidget(self.name_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.state_label)

    def _severity(self, value):
        warning = self.thresholds.get("warning_c")
        critical = self.thresholds.get("critical_c")
        cool_below = self.thresholds.get("cool_below_c")
        if critical is not None and value >= float(critical):
            return "critical", "Critical temperature"
        if warning is not None and value >= float(warning):
            return "warning", "Temperature elevated"
        if cool_below is not None and value < float(cool_below):
            return "cool", "Cool"
        return "normal", "In range"

    def set_reading(self, reading):
        if reading is None:
            severity, state = "unknown", "Sensor unavailable"
            self.value_label.setText("--.- °C")
        else:
            severity, state = self._severity(float(reading))
            self.value_label.setText(f"{reading:.1f} °C")
        background, foreground = COLORS[severity]
        self.setStyleSheet(
            f"QFrame#card {{ background-color: {background}; border: 1px solid {foreground}; border-radius: 12px; }}"
            f"QFrame#card QLabel {{ color: {foreground}; }}"
        )
        self.state_label.setText(state)


class DetailsWindow(QtWidgets.QMainWindow):
    """Expanded sensor plots, useful on a connected HDMI monitor."""

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("BrewaTaco — More details")
        self.resize(1000, 700)
        self.setMinimumSize(720, 520)

        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(18, 14, 18, 14)
        heading = QtWidgets.QLabel("Sensor history")
        heading.setObjectName("pageTitle")
        layout.addWidget(heading)

        self.plot_widget = pg.GraphicsLayoutWidget()
        layout.addWidget(self.plot_widget, 1)
        self.curves = {}
        for row, name in enumerate(controller.sensors):
            plot = self.plot_widget.addPlot(row=row, col=0, title=name.replace("_", " "))
            plot.showGrid(x=True, y=True, alpha=0.25)
            plot.setLabel("left", "Temperature", units="°C")
            plot.setLabel("bottom", "Elapsed time", units="s")
            plot.setMinimumHeight(150)
            self.curves[name] = plot.plot(pen=pg.mkPen("#42d6bd", width=2))

        self.setCentralWidget(container)
        self.refresh_timer = QtCore.QTimer(self)
        self.refresh_timer.setInterval(2000)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start()

    def refresh(self):
        for name, curve in self.curves.items():
            history = self.controller.get_history(name, max_points=1200)
            if not history:
                continue
            origin = history[0][0]
            x_values = [timestamp - origin for timestamp, _ in history]
            y_values = [float("nan") if value is None else value for _, value in history]
            curve.setData(x_values, y_values)

    def closeEvent(self, event):
        event.ignore()
        self.hide()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("BrewaTaco Controller")
        self.setMinimumSize(900, 600)
        self.setStyleSheet(APP_STYLE)
        pg.setConfigOptions(antialias=False, background="#101820", foreground="#dce7eb")
        self.sensor_names = list(controller.sensors)
        self.cards = {}
        self._latest_payload = {}
        thresholds = controller.cfg.get("display", {}).get("temperature_thresholds_c", {})

        root = QtWidgets.QWidget()
        root_layout = QtWidgets.QVBoxLayout(root)
        root_layout.setContentsMargins(16, 12, 16, 12)
        root_layout.setSpacing(10)
        self.setCentralWidget(root)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("BrewaTaco")
        title.setObjectName("pageTitle")
        self.connection_label = QtWidgets.QLabel("●  Starting sensors")
        self.connection_label.setObjectName("muted")
        header.addWidget(title)
        header.addSpacing(12)
        header.addWidget(self.connection_label)
        header.addStretch(1)
        self.details_button = QtWidgets.QPushButton("More details  ·  Ctrl+D")
        header.addWidget(self.details_button)
        root_layout.addLayout(header)

        # Five equal-width cards make the newly added enclosure sensor visible
        # alongside the brewing probes without taking space from the controls.
        readings = QtWidgets.QHBoxLayout()
        readings.setSpacing(9)
        for name in self.sensor_names:
            card = SensorCard(name, thresholds.get(name, {}))
            self.cards[name] = card
            readings.addWidget(card, 1)
        root_layout.addLayout(readings)

        plot_panel = QtWidgets.QFrame()
        plot_panel.setObjectName("panel")
        plot_layout = QtWidgets.QVBoxLayout(plot_panel)
        plot_layout.setContentsMargins(14, 10, 14, 10)
        plot_header = QtWidgets.QHBoxLayout()
        plot_title = QtWidgets.QLabel("Live temperature")
        plot_title.setObjectName("pageTitle")
        plot_header.addWidget(plot_title)
        plot_header.addStretch(1)
        plot_header.addWidget(QtWidgets.QLabel("Showing"))
        self.sensor_combo = QtWidgets.QComboBox()
        self.sensor_combo.addItems(self.sensor_names)
        configured_sensor = str(controller.target_sensor_name)
        if configured_sensor in self.sensor_names:
            self.sensor_combo.setCurrentText(configured_sensor)
        self.sensor_combo.setMinimumWidth(180)
        plot_header.addWidget(self.sensor_combo)
        plot_layout.addLayout(plot_header)

        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setLabel("left", "Temperature", units="°C")
        self.plot.setLabel("bottom", "Elapsed time", units="s")
        self.plot.setMinimumHeight(260)
        self.temperature_curve = self.plot.plot(pen=pg.mkPen("#42d6bd", width=3))
        self.setpoint_line = pg.InfiniteLine(
            angle=0,
            movable=False,
            pen=pg.mkPen("#f1b85b", width=2, style=QtCore.Qt.PenStyle.DashLine),
        )
        self.plot.addItem(self.setpoint_line)
        plot_layout.addWidget(self.plot, 1)
        root_layout.addWidget(plot_panel, 1)

        # Controls have their own horizontal row beneath the chart so the
        # landscape 1280x800 panel uses its available vertical space.
        controls = QtWidgets.QFrame()
        controls.setObjectName("panel")
        controls_layout = QtWidgets.QHBoxLayout(controls)
        controls_layout.setContentsMargins(14, 10, 14, 10)
        controls_layout.setSpacing(12)

        target_group = QtWidgets.QVBoxLayout()
        target_label = QtWidgets.QLabel("Target temperature")
        target_label.setObjectName("eyebrow")
        self.target_spin = QtWidgets.QDoubleSpinBox()
        self.target_spin.setRange(0, 150)
        self.target_spin.setDecimals(1)
        self.target_spin.setSingleStep(0.5)
        self.target_spin.setSuffix(" °C")
        self.target_spin.setKeyboardTracking(False)
        try:
            self.target_spin.setValue(float(controller.pid.setpoint))
        except (TypeError, ValueError):
            self.target_spin.setValue(65.0)
        target_group.addWidget(target_label)
        target_group.addWidget(self.target_spin)
        controls_layout.addLayout(target_group, 2)

        mode_group = QtWidgets.QVBoxLayout()
        mode_label = QtWidgets.QLabel("Heater quick controls")
        mode_label.setObjectName("eyebrow")
        buttons = QtWidgets.QHBoxLayout()
        self.auto_button = QtWidgets.QPushButton("AUTO")
        self.off_button = QtWidgets.QPushButton("HEATER OFF")
        self.full_button = QtWidgets.QPushButton("HEATER 100%")
        self.mode_buttons = {"auto": self.auto_button, "off": self.off_button, "full": self.full_button}
        for mode, button in self.mode_buttons.items():
            button.setCheckable(True)
            button.setMinimumHeight(54)
            button.clicked.connect(lambda checked=False, selected=mode: self.set_output_mode(selected))
            buttons.addWidget(button, 1)
        mode_group.addWidget(mode_label)
        mode_group.addLayout(buttons)
        controls_layout.addLayout(mode_group, 4)

        output_group = QtWidgets.QVBoxLayout()
        output_label = QtWidgets.QLabel("Heater output")
        output_label.setObjectName("eyebrow")
        self.duty_label = QtWidgets.QLabel("0%")
        self.duty_label.setObjectName("temperature")
        self.duty_bar = QtWidgets.QProgressBar()
        self.duty_bar.setRange(0, 100)
        self.duty_bar.setTextVisible(False)
        output_group.addWidget(output_label)
        output_group.addWidget(self.duty_label)
        output_group.addWidget(self.duty_bar)
        controls_layout.addLayout(output_group, 1)
        root_layout.addWidget(controls)

        self.safety_label = QtWidgets.QLabel("Safety status: waiting for sensor data")
        self.safety_label.setObjectName("muted")
        self.safety_label.setWordWrap(True)
        root_layout.addWidget(self.safety_label)

        self.details_window = DetailsWindow(controller)
        self.details_button.clicked.connect(self.show_details)
        self.sensor_combo.currentTextChanged.connect(self.refresh_plot)
        self.target_spin.valueChanged.connect(self.on_target_changed)
        controller.signals.data_updated.connect(self.on_data_updated)

        self.gui_timer = QtCore.QTimer(self)
        self.gui_timer.setInterval(1000)
        self.gui_timer.timeout.connect(self.refresh_plot)
        self.gui_timer.start()

        self.details_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+D"), self)
        self.details_shortcut.activated.connect(self.show_details)
        self.auto_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+1"), self)
        self.auto_shortcut.activated.connect(lambda: self.set_output_mode("auto"))
        self.off_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+2"), self)
        self.off_shortcut.activated.connect(lambda: self.set_output_mode("off"))
        self.full_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+3"), self)
        self.full_shortcut.activated.connect(lambda: self.set_output_mode("full"))
        self._sync_mode_buttons(controller.output_mode)
        self._update_setpoint_line()

    def on_target_changed(self, value):
        self.controller.pid.setpoint = float(value)
        self._update_setpoint_line()

    def set_output_mode(self, mode):
        self.controller.set_output_mode(mode)
        self._sync_mode_buttons(mode)

    def _sync_mode_buttons(self, mode):
        for name, button in self.mode_buttons.items():
            button.blockSignals(True)
            button.setChecked(name == mode)
            button.setObjectName({"auto": "primary", "off": "danger", "full": "warning"}[name])
            button.style().unpolish(button)
            button.style().polish(button)
            button.blockSignals(False)

    def _update_setpoint_line(self):
        try:
            self.setpoint_line.setValue(float(self.controller.pid.setpoint))
        except (TypeError, ValueError):
            pass

    def on_data_updated(self, payload):
        self._latest_payload = payload
        latest = payload.get("latest", {})
        readings_ok = True
        for name, card in self.cards.items():
            entry = latest.get(name)
            value = entry[1] if entry else None
            card.set_reading(value)
            readings_ok = readings_ok and value is not None

        duty = max(0, min(100, int(float(payload.get("heater_duty", 0.0) or 0.0))))
        self.duty_label.setText(f"{duty}%")
        self.duty_bar.setValue(duty)
        mode = payload.get("output_mode", "auto")
        self._sync_mode_buttons(mode)

        rims_entry = latest.get("RIMS_Kettle")
        rims_value = rims_entry[1] if rims_entry else None
        if not readings_ok:
            text = "Safety: sensor reading missing — heater output forced to 0%."
            color = "#ff827b"
        elif rims_value is not None and float(rims_value) >= self.controller.RIMS_MAX:
            text = f"SAFETY CUTOFF: RIMS at {float(rims_value):.1f} °C; heater disabled until it cools below the reset threshold."
            color = "#ff827b"
        elif mode == "full":
            text = "Manual 100% output selected. Sensor watchdog and RIMS over-temperature cutoff remain active."
            color = "#f1bd61"
        elif mode == "off":
            text = "Heater output is off. Select AUTO to return to PID temperature control."
            color = "#aab8bf"
        else:
            text = "Safety interlocks active · PID automatic control"
            color = "#74d5ad"
        self.safety_label.setText(text)
        self.safety_label.setStyleSheet(f"color: {color};")
        if readings_ok:
            self.connection_label.setText("●  Sensors connected")
            self.connection_label.setStyleSheet("color: #74d5ad;")
        else:
            self.connection_label.setText("●  Sensor fault / waiting")
            self.connection_label.setStyleSheet("color: #ff827b;")

    def refresh_plot(self, *_):
        name = self.sensor_combo.currentText()
        if not name:
            return
        history = self.controller.get_history(name, max_points=600)
        if history:
            origin = history[0][0]
            x_values = [timestamp - origin for timestamp, _ in history]
            y_values = [float("nan") if value is None else value for _, value in history]
            self.temperature_curve.setData(x_values, y_values)
        self._update_setpoint_line()

    def show_details(self):
        app = QtWidgets.QApplication.instance()
        current_screen = self.screen()
        secondary = next((screen for screen in app.screens() if screen != current_screen), None)
        if secondary is not None:
            self.details_window.setGeometry(secondary.availableGeometry())
        self.details_window.showMaximized()
        self.details_window.raise_()
        self.details_window.activateWindow()
        self.details_window.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        if len(QtWidgets.QApplication.screens()) > 1:
            QtCore.QTimer.singleShot(0, self.show_details)

    def closeEvent(self, event):
        self.details_window.hide()
        super().closeEvent(event)


def run_gui(controller):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setApplicationName("BrewaTaco")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)
    window = MainWindow(controller)
    primary = app.primaryScreen()
    if primary is not None:
        window.setGeometry(primary.availableGeometry())
    window.showMaximized()
    sys.exit(app.exec())
