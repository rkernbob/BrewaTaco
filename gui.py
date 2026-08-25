import sys
import time
from PySide6 import QtWidgets, QtCore
import pyqtgraph as pg

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("BrewaTaco Controller")
        self.resize(1200, 800)

        w = QtWidgets.QWidget()
        self.setCentralWidget(w)
        vbox = QtWidgets.QVBoxLayout(w)

        # Top controls
        controls = QtWidgets.QHBoxLayout()
        vbox.addLayout(controls)

        self.target_spin = QtWidgets.QDoubleSpinBox()
        self.target_spin.setRange(0, 150)
        try:
            self.target_spin.setValue(float(self.controller.pid.setpoint))
        except Exception:
            self.target_spin.setValue(65.0)
        self.target_spin.setSingleStep(0.5)
        self.target_spin.valueChanged.connect(self.on_target_changed)
        controls.addWidget(QtWidgets.QLabel("Target (°C):"))
        controls.addWidget(self.target_spin)

        self.sensor_combo = QtWidgets.QComboBox()
        self.sensor_combo.addItems(list(self.controller.sensors.keys()))
        # set current to configured
        idx = self.sensor_combo.findText(str(self.controller.target_sensor_name))
        if idx >= 0:
            self.sensor_combo.setCurrentIndex(idx)
        self.sensor_combo.currentTextChanged.connect(self.on_sensor_changed)
        controls.addWidget(QtWidgets.QLabel("Control sensor:"))
        controls.addWidget(self.sensor_combo)

        # Heater status label and duty
        self.status_label = QtWidgets.QLabel("Heater: off  Duty: 0.0%")
        controls.addWidget(self.status_label)

        # Plotting area
        self.plot_widget = pg.GraphicsLayoutWidget()
        vbox.addWidget(self.plot_widget, 1)

        self.plots = {}
        self.curves = {}
        self.max_points = 800

        for i, name in enumerate(self.controller.sensors.keys()):
            p = self.plot_widget.addPlot(row=i, col=0, title=name)
            p.showGrid(x=True, y=True)
            p.setLabel('left', '°C')
            p.setLabel('bottom', 'time', 's')
            curve = p.plot(pen=pg.mkPen(width=2))
            self.plots[name] = p
            self.curves[name] = curve

        # Hook controller signals
        self.controller.signals.data_updated.connect(self.on_data_updated)

        # GUI timer for stateless updates (optional)
        self.gui_timer = QtCore.QTimer()
        self.gui_timer.setInterval(1000)  # 1 Hz GUI refresh for large updates
        self.gui_timer.timeout.connect(self._refresh_plots)
        self._latest_payload = None
        self.gui_timer.start()

    def on_target_changed(self, v):
        self.controller.pid.setpoint = float(v)

    def on_sensor_changed(self, name):
        self.controller.target_sensor_name = name

    def on_data_updated(self, payload):
        # quick update of heater label and store payload for detailed plotting
        heater = payload.get("heater_duty", 0.0)
        sp = payload.get("pid_setpoint", None)
        tname = payload.get("target_sensor", "")
        self.status_label.setText(f"Heater: {'ENABLED' if self.controller.heater._enabled else 'DISABLED'}  Duty: {heater:.1f}%  SP: {sp}  TargetSensor: {tname}")
        self._latest_payload = payload

    def _refresh_plots(self):
        # update pyqtgraph curves from controller history
        tnow = time.time()
        for name in list(self.controller.sensors.keys()):
            hist = self.controller.get_history(name, max_points=self.max_points)
            if not hist:
                continue
            times = [t for (t, v) in hist]
            vals = [v if v is not None else float('nan') for (t, v) in hist]
            # plot relative time (seconds)
            t0 = times[0]
            rel = [tt - t0 for tt in times]
            self.curves[name].setData(rel, vals)

def run_gui(controller):
    app = QtWidgets.QApplication(sys.argv)
    mw = MainWindow(controller)
    mw.show()
    sys.exit(app.exec())
