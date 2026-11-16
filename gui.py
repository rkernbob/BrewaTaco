import sys
import time

import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets


# A high-contrast palette and generous hit areas work well on a small DSI panel,
# while the standard Qt controls remain comfortable with a mouse and keyboard.
APP_STYLE = """
QWidget {
    background: #101820;
    color: #eef4f6;
    font-family: sans-serif;
    font-size: 16px;
}
QLabel#muted { color: #9aabb5; }
QLabel#eyebrow { color: #9aabb5; font-size: 13px; font-weight: 600; }
QLabel#temperature { font-size: 34px; font-weight: 700; }
QLabel#pageTitle { font-size: 24px; font-weight: 700; }
QFrame#card, QFrame#panel {
    background: #1b2933;
    border: 1px solid #2d414e;
    border-radius: 12px;
}
QPushButton {
    background: #2b414e;
    border: 1px solid #3c5664;
    border-radius: 9px;
    min-height: 48px;
    padding: 0 16px;
    font-weight: 600;
}
QPushButton:hover { background: #385362; }
QPushButton:pressed { background: #22343e; }
QPushButton#primary { background: #147d78; border-color: #1b9b91; }
QPushButton#primary:hover { background: #19958d; }
QPushButton#danger { background: #923d3c; border-color: #b94d48; }
QPushButton#danger:hover { background: #a94946; }
QComboBox, QDoubleSpinBox {
    background: #0e171d;
    border: 1px solid #3c5664;
    border-radius: 8px;
    min-height: 48px;
    padding: 0 10px;
    font-size: 20px;
}
QComboBox QAbstractItemView { background: #1b2933; selection-background-color: #147d78; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 28px; }
QProgressBar {
    background: #0e171d;
    border: 0;
    border-radius: 7px;
    min-height: 14px;
    text-align: center;
}
QProgressBar::chunk { background: #24b49e; border-radius: 7px; }
"""


class SensorCard(QtWidgets.QFrame):
    def __init__(self, name):
        super().__init__()
        self.setObjectName("card")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(3)

        self.name_label = QtWidgets.QLabel(name.replace("_", " "))
        self.name_label.setObjectName("eyebrow")
        self.value_label = QtWidgets.QLabel("--.- °C")
        self.value_label.setObjectName("temperature")
        self.state_label = QtWidgets.QLabel("Waiting for reading")
        self.state_label.setObjectName("muted")
        layout.addWidget(self.name_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.state_label)

    def set_reading(self, reading):
        if reading is None:
            self.value_label.setText("--.- °C")
            self.state_label.setText("Sensor unavailable")
            self.value_label.setStyleSheet("color: #f08a82;")
        else:
            self.value_label.setText(f"{reading:.1f} °C")
            self.state_label.setText("Live")
            self.value_label.setStyleSheet("color: #eef4f6;")


class DetailsWindow(QtWidgets.QMainWindow):
    """Expanded sensor plots, intended for a connected HDMI monitor."""

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
        self.plots = {}
        for row, name in enumerate(controller.sensors):
            plot = self.plot_widget.addPlot(row=row, col=0, title=name.replace("_", " "))
            plot.showGrid(x=True, y=True, alpha=0.25)
            plot.setLabel("left", "Temperature", units="°C")
            plot.setLabel("bottom", "Elapsed time", units="s")
            plot.setMinimumHeight(150)
            self.plots[name] = plot
            self.curves[name] = plot.plot(pen=pg.mkPen("#42d6bd", width=2))

        self.setCentralWidget(container)
        self.refresh_timer = QtCore.QTimer(self)
        self.refresh_timer.setInterval(2000)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start()

    def refresh(self):
        for name, curve in self.curves.items():
            history = self.controller.get_history(name, max_points=1200)
            valid = [(timestamp, value) for timestamp, value in history if value is not None]
            if not history:
                continue
            origin = history[0][0]
            x_values = [timestamp - origin for timestamp, _ in history]
            y_values = [float("nan") if value is None else value for _, value in history]
            curve.setData(x_values, y_values)

    def closeEvent(self, event):
        # Keep the optional details view available from the dashboard button.
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

        self.sensor_names = list(controller.sensors.keys())
        self.cards = {}
        self._last_payload = {}

        root = QtWidgets.QWidget()
        root_layout = QtWidgets.QVBoxLayout(root)
        root_layout.setContentsMargins(18, 14, 18, 14)
        root_layout.setSpacing(12)
        self.setCentralWidget(root)

        # Header: product/status at a glance and a dedicated path to the detail view.
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

        # Large, glanceable sensor readings.
        readings = QtWidgets.QHBoxLayout()
        readings.setSpacing(10)
        for name in self.sensor_names:
            card = SensorCard(name)
            self.cards[name] = card
            readings.addWidget(card, 1)
        root_layout.addLayout(readings)

        # Main trend plot plus a compact control panel.
        content = QtWidgets.QHBoxLayout()
        content.setSpacing(12)
        plot_panel = QtWidgets.QFrame()
        plot_panel.setObjectName("panel")
        plot_layout = QtWidgets.QVBoxLayout(plot_panel)
        plot_layout.setContentsMargins(14, 12, 14, 12)
        plot_header = QtWidgets.QHBoxLayout()
        plot_title = QtWidgets.QLabel("Live temperature")
        plot_title.setObjectName("pageTitle")
        plot_header.addWidget(plot_title)
        plot_header.addStretch(1)
        plot_header.addWidget(QtWidgets.QLabel("Control sensor"))
        self.sensor_combo = QtWidgets.QComboBox()
        self.sensor_combo.addItems(self.sensor_names)
        current_sensor = str(controller.target_sensor_name)
        if current_sensor in self.sensor_names:
            self.sensor_combo.setCurrentText(current_sensor)
        self.sensor_combo.setMinimumWidth(190)
        plot_header.addWidget(self.sensor_combo)
        plot_layout.addLayout(plot_header)

        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        self.plot.setLabel("left", "Temperature", units="°C")
        self.plot.setLabel("bottom", "Elapsed time", units="s")
        self.plot.setMinimumHeight(300)
        self.temperature_curve = self.plot.plot(pen=pg.mkPen("#42d6bd", width=3))
        self.setpoint_line = pg.InfiniteLine(angle=0, movable=False,
                                             pen=pg.mkPen("#f1b85b", width=2, style=QtCore.Qt.PenStyle.DashLine))
        self.plot.addItem(self.setpoint_line)
        plot_layout.addWidget(self.plot, 1)
        content.addWidget(plot_panel, 7)

        controls = QtWidgets.QFrame()
        controls.setObjectName("panel")
        controls.setMinimumWidth(285)
        controls.setMaximumWidth(360)
        control_layout = QtWidgets.QVBoxLayout(controls)
        control_layout.setContentsMargins(18, 16, 18, 16)
        control_layout.setSpacing(10)

        target_title = QtWidgets.QLabel("Target temperature")
        target_title.setObjectName("eyebrow")
        control_layout.addWidget(target_title)
        target_row = QtWidgets.QHBoxLayout()
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
        target_row.addWidget(self.target_spin, 1)
        control_layout.addLayout(target_row)
        hint = QtWidgets.QLabel("Use the arrows, type a value, or scroll while focused.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        control_layout.addWidget(hint)

        control_layout.addSpacing(8)
        heater_title = QtWidgets.QLabel("Heater control")
        heater_title.setObjectName("eyebrow")
        control_layout.addWidget(heater_title)
        self.heater_button = QtWidgets.QPushButton("HEATER ENABLED")
        self.heater_button.setCheckable(True)
        self.heater_button.setChecked(bool(controller.heater._enabled))
        self.heater_button.setMinimumHeight(58)
        self.heater_button.clicked.connect(self.on_heater_toggled)
        control_layout.addWidget(self.heater_button)

        self.duty_label = QtWidgets.QLabel("0%")
        self.duty_label.setObjectName("temperature")
        self.duty_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        duty_caption = QtWidgets.QLabel("Controller output")
        duty_caption.setObjectName("muted")
        duty_caption.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        control_layout.addWidget(self.duty_label)
        control_layout.addWidget(duty_caption)
        self.duty_bar = QtWidgets.QProgressBar()
        self.duty_bar.setRange(0, 100)
        self.duty_bar.setTextVisible(False)
        control_layout.addWidget(self.duty_bar)

        self.safety_label = QtWidgets.QLabel("Safety status: waiting for sensor data")
        self.safety_label.setObjectName("muted")
        self.safety_label.setWordWrap(True)
        control_layout.addSpacing(8)
        control_layout.addWidget(self.safety_label)
        control_layout.addStretch(1)
        content.addWidget(controls, 3)
        root_layout.addLayout(content, 1)

        footer = QtWidgets.QLabel("Heater output is automatically removed if sensor data is missing or stale. Hardware thermal protection is still required.")
        footer.setObjectName("muted")
        footer.setWordWrap(True)
        root_layout.addWidget(footer)

        self.details_window = DetailsWindow(controller)
        self.details_button.clicked.connect(self.show_details)
        self.sensor_combo.currentTextChanged.connect(self.on_sensor_changed)
        self.target_spin.valueChanged.connect(self.on_target_changed)
        controller.signals.data_updated.connect(self.on_data_updated)

        self.gui_timer = QtCore.QTimer(self)
        self.gui_timer.setInterval(1000)
        self.gui_timer.timeout.connect(self.refresh_plot)
        self.gui_timer.start()

        self.details_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+D"), self)
        self.details_shortcut.activated.connect(self.show_details)
        self.heater_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Ctrl+E"), self)
        self.heater_shortcut.activated.connect(self.toggle_heater)

        self._update_heater_button()
        self._update_setpoint_line()

    def on_target_changed(self, value):
        self.controller.pid.setpoint = float(value)
        self._update_setpoint_line()

    def on_sensor_changed(self, name):
        self.controller.target_sensor_name = name
        self.refresh_plot()

    def on_heater_toggled(self, enabled):
        self.controller.heater.enable(enabled)
        self._update_heater_button()

    def toggle_heater(self):
        self.heater_button.setChecked(not self.heater_button.isChecked())
        self.on_heater_toggled(self.heater_button.isChecked())

    def _update_heater_button(self):
        enabled = bool(self.controller.heater._enabled)
        self.heater_button.blockSignals(True)
        self.heater_button.setChecked(enabled)
        self.heater_button.setText("HEATER ENABLED" if enabled else "HEATER DISABLED")
        self.heater_button.setObjectName("primary" if enabled else "danger")
        self.heater_button.style().unpolish(self.heater_button)
        self.heater_button.style().polish(self.heater_button)
        self.heater_button.blockSignals(False)

    def _update_setpoint_line(self):
        try:
            self.setpoint_line.setValue(float(self.controller.pid.setpoint))
        except (TypeError, ValueError):
            pass

    def on_data_updated(self, payload):
        self._last_payload = payload
        latest = payload.get("latest", {})
        any_missing = False
        for name, card in self.cards.items():
            entry = latest.get(name)
            value = entry[1] if entry else None
            card.set_reading(value)
            any_missing = any_missing or value is None

        duty = max(0, min(100, int(float(payload.get("heater_duty", 0.0) or 0.0))))
        self.duty_label.setText(f"{duty}%")
        self.duty_bar.setValue(duty)
        sensor_name = payload.get("target_sensor", "")
        if any_missing:
            self.connection_label.setText("●  Sensor fault / waiting")
            self.connection_label.setStyleSheet("color: #f08a82;")
            self.safety_label.setText("Safety status: heater output is held at 0% until all sensor readings are valid.")
            self.safety_label.setStyleSheet("color: #f08a82;")
        else:
            self.connection_label.setText("●  Sensors connected")
            self.connection_label.setStyleSheet("color: #73d5ad;")
            self.safety_label.setText(f"Safety status: sensor readings valid · controlling {sensor_name.replace('_', ' ')}")
            self.safety_label.setStyleSheet("color: #73d5ad;")
        self._update_heater_button()

    def refresh_plot(self):
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
        screens = QtWidgets.QApplication.screens()
        current_screen = self.screen()
        secondary = next((screen for screen in screens if screen != current_screen), None)
        if secondary is not None:
            self.details_window.setGeometry(secondary.availableGeometry())
            self.details_window.showMaximized()
        else:
            self.details_window.showMaximized()
            self.details_window.raise_()
            self.details_window.activateWindow()
        self.details_window.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        # If an HDMI display is attached, offer the full history view there at launch.
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
