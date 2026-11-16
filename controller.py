import threading
import time
from collections import deque

import yaml
from PySide6.QtCore import QObject, Signal

from heater import HeaterController
from pid_controller import PID
from sensors import MAX31856Sensor, OneWireSensor


class DataSignals(QObject):
    # Emitted with latest sensor values and controller status for the GUI.
    data_updated = Signal(dict)


class Controller:
    def __init__(self, config_path="config.yaml", simulate=False):
        with open(config_path) as config_file:
            self.cfg = yaml.safe_load(config_file)
        self.simulate = simulate

        self.sensors = {}
        for name, device_id in self.cfg["sensors"]["one_wire_ids"].items():
            self.sensors[name] = OneWireSensor(name, device_id=device_id, simulate=simulate)
        self.sensors["Boil_kettle"] = MAX31856Sensor(
            "Boil_kettle",
            cs_pin=self.cfg["sensors"]["max31856_cs_pin"],
            simulate=simulate,
        )

        sample_interval = float(self.cfg["logging"]["sample_interval_s"])
        history_length = max(1, int(self.cfg["logging"]["history_length"]))
        self.data = {name: deque(maxlen=history_length) for name in self.sensors}
        self._data_lock = threading.Lock()
        self.signals = DataSignals()

        self.heater = HeaterController(
            self.cfg["heater"]["gpio_pin"],
            cycle_time=self.cfg["control"]["cycle_time_seconds"],
            simulate=simulate,
        )

        control_cfg = self.cfg["control"]
        pid_cfg = control_cfg["pid"]
        default_target = control_cfg["default_target"]
        self.pid = PID(
            pid_cfg["Kp"],
            pid_cfg["Ki"],
            pid_cfg["Kd"],
            setpoint=default_target if isinstance(default_target, (int, float)) else 65.0,
            output_limits=(0.0, 100.0),
            integrator_limit=pid_cfg.get("integrator_limit"),
        )
        self.target_sensor_name = default_target
        if not isinstance(default_target, str):
            self.pid.setpoint = float(default_target)

        safety_cfg = self.cfg["safety"]
        self.RIMS_MAX = float(safety_cfg["RIMS_MAX_C"])
        self.RIMS_HYST = float(safety_cfg["RIMS_HYSTERESIS_C"])
        self.sensor_timeout = float(safety_cfg.get("sensor_timeout_s", 10.0))

        # Manual output selections are honored only while sensor and RIMS
        # interlocks are healthy. The normal mode remains PID/automatic.
        self._mode_lock = threading.Lock()
        self._output_mode = "auto"
        self._stop = False
        self._sample_interval = sample_interval
        self._control_interval = float(control_cfg.get("control_interval_s", 0.5))

        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._ctrl_thread = threading.Thread(target=self._control_loop, daemon=True)
        self._poll_thread.start()
        self._ctrl_thread.start()

    @property
    def output_mode(self):
        with self._mode_lock:
            return self._output_mode

    def set_output_mode(self, mode):
        if mode not in {"auto", "off", "full"}:
            raise ValueError("Output mode must be 'auto', 'off', or 'full'.")
        with self._mode_lock:
            self._output_mode = mode

    def stop(self):
        self._stop = True
        self.heater.stop()

    def _poll_loop(self):
        while not self._stop:
            timestamp = time.time()
            with self._data_lock:
                for name, sensor in self.sensors.items():
                    try:
                        value = sensor.read()
                    except Exception:
                        value = None
                    self.data[name].append((timestamp, value))
                latest = {
                    name: self.data[name][-1] if self.data[name] else (timestamp, None)
                    for name in self.data
                }
            payload = {
                "timestamp": timestamp,
                "latest": latest,
                "heater_duty": self.heater._duty,
                "heater_enabled": self.heater._enabled,
                "output_mode": self.output_mode,
                "pid_setpoint": self.pid.setpoint,
                "target_sensor": self.target_sensor_name,
            }
            self.signals.data_updated.emit(payload)
            time.sleep(self._sample_interval)

    def _control_loop(self):
        rims_disabled = False
        while not self._stop:
            loop_started = time.time()
            with self._data_lock:
                latest = {
                    name: self.data[name][-1] if self.data[name] else (None, None)
                    for name in self.data
                }

            now = time.time()
            sensor_ok = all(
                timestamp is not None
                and value is not None
                and now - timestamp <= self.sensor_timeout
                for timestamp, value in latest.values()
            )

            rims_entry = latest.get("RIMS_Kettle")
            rims_temp = rims_entry[1] if rims_entry and rims_entry[0] is not None else None
            if rims_temp is not None:
                if rims_temp >= self.RIMS_MAX:
                    self.heater.enable(False)
                    self.pid.reset()
                    rims_disabled = True
                elif rims_disabled and rims_temp <= self.RIMS_MAX - self.RIMS_HYST:
                    self.heater.enable(True)
                    rims_disabled = False

            if not sensor_ok or rims_disabled:
                # Sensor watchdog and RIMS cutoff always override manual output.
                self.heater.set_duty(0.0)
            else:
                mode = self.output_mode
                if mode == "off":
                    self.heater.set_duty(0.0)
                elif mode == "full":
                    self.heater.set_duty(100.0)
                else:
                    measurement = None
                    if isinstance(self.target_sensor_name, str):
                        entry = latest.get(self.target_sensor_name)
                        measurement = entry[1] if entry else None
                    try:
                        setpoint = float(self.pid.setpoint)
                    except (TypeError, ValueError):
                        setpoint = None
                    if measurement is not None and setpoint is not None:
                        self.heater.set_duty(self.pid.update(measurement))
                    else:
                        self.heater.set_duty(0.0)

            elapsed = time.time() - loop_started
            time.sleep(max(0.0, self._control_interval - elapsed))

    def get_history(self, sensor_name, max_points=1000):
        with self._data_lock:
            history = list(self.data.get(sensor_name, []))
        if max_points and len(history) > max_points:
            return history[-max_points:]
        return history
