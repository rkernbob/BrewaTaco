import threading
import time
from collections import deque
import yaml

from pid_controller import PID
from heater import HeaterController
from sensors import OneWireSensor, MAX31856Sensor

from PySide6.QtCore import QObject, Signal

class DataSignals(QObject):
    # emitted with payload: dict{name: (timestamp, value), ...}, plus meta fields
    data_updated = Signal(dict)

class Controller:
    def __init__(self, config_path="config.yaml", simulate=False):
        # load config
        with open(config_path) as f:
            self.cfg = yaml.safe_load(f)
        self.simulate = simulate

        # create sensors
        self.sensors = {}
        for name, dev_id in self.cfg["sensors"]["one_wire_ids"].items():
            self.sensors[name] = OneWireSensor(name, device_id=dev_id, simulate=simulate)
        # max31856
        self.sensors["Boil_kettle"] = MAX31856Sensor("Boil_kettle",
                                                     cs_pin=self.cfg["sensors"]["max31856_cs_pin"],
                                                     simulate=simulate)

        sample_interval = float(self.cfg["logging"]["sample_interval_s"])
        history_len = int(self.cfg["logging"]["history_length"])
        maxlen = max(1, int(history_len))

        # ring buffers for each sensor: deque of (timestamp, value)
        self.data = {name: deque(maxlen=maxlen) for name in self.sensors.keys()}
        self._data_lock = threading.Lock()

        # signals for GUI
        self.signals = DataSignals()

        # heater
        self.heater = HeaterController(self.cfg["heater"]["gpio_pin"],
                                       cycle_time=self.cfg["control"]["cycle_time_seconds"],
                                       simulate=simulate)

        # PID
        p = self.cfg["control"]["pid"]
        self.pid = PID(p["Kp"], p["Ki"], p["Kd"],
                       setpoint=self.cfg["control"]["default_target"] if isinstance(self.cfg["control"]["default_target"], (int, float)) else 65.0,
                       output_limits=(0.0, 100.0),
                       integrator_limit=p.get("integrator_limit", None))
        # allow selecting sensor name as control target; default from config
        self.target_sensor_name = self.cfg["control"]["default_target"]
        if not isinstance(self.target_sensor_name, str):
            # if default is numeric, leave as numeric setpoint
            self.pid.setpoint = float(self.target_sensor_name)

        # safety params
        self.RIMS_MAX = float(self.cfg["safety"]["RIMS_MAX_C"])
        self.RIMS_HYST = float(self.cfg["safety"]["RIMS_HYSTERESIS_C"])
        self.sensor_timeout = float(self.cfg["safety"].get("sensor_timeout_s", 10.0))

        # control threading
        self._stop = False
        self._sample_interval = sample_interval
        self._control_interval = float(self.cfg["control"].get("control_interval_s", 0.5))

        # start threads
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._ctrl_thread = threading.Thread(target=self._control_loop, daemon=True)
        self._poll_thread.start()
        self._ctrl_thread.start()

    def stop(self):
        self._stop = True
        self.heater.stop()
        # threads exit on _stop

    def _poll_loop(self):
        while not self._stop:
            ts = time.time()
            with self._data_lock:
                for name, sensor in self.sensors.items():
                    try:
                        v = sensor.read()
                    except Exception:
                        v = None
                    self.data[name].append((ts, v))
                # emit a shallow copy of latest values for GUI
                latest = {name: (self.data[name][-1] if len(self.data[name]) else (ts, None)) for name in self.data}
            payload = {
                "timestamp": ts,
                "latest": latest,
                "heater_duty": self.heater._duty if hasattr(self.heater, "_duty") else 0.0,
                "pid_setpoint": self.pid.setpoint,
                "target_sensor": self.target_sensor_name
            }
            # thread-safe emit
            self.signals.data_updated.emit(payload)
            time.sleep(self._sample_interval)

    def _control_loop(self):
        rims_disabled = False
        while not self._stop:
            t0 = time.time()
            # snapshot latest safely
            with self._data_lock:
                latest = {name: (self.data[name][-1] if len(self.data[name]) else (None, None)) for name in self.data}
            # check sensor staleness and presence
            now = time.time()
            sensor_ok = True
            for name, entry in latest.items():
                if entry[0] is None:
                    # sensor has no data
                    sensor_ok = False
                    break
                ts, val = entry
                if val is None or (now - ts) > self.sensor_timeout:
                    sensor_ok = False
                    break

            # RIMS safety
            rims_entry = latest.get("RIMS_Kettle")
            rims_temp = None
            if rims_entry and rims_entry[0] is not None:
                rims_temp = rims_entry[1]
            if rims_temp is not None:
                if rims_temp >= self.RIMS_MAX:
                    # disable heater and reset PID integrator
                    self.heater.enable(False)
                    self.pid.reset()
                    rims_disabled = True
                elif rims_disabled and rims_temp <= (self.RIMS_MAX - self.RIMS_HYST):
                    # re-enable when safe
                    self.heater.enable(True)
                    rims_disabled = False

            if not sensor_ok:
                # safety: turn off heater
                self.heater.set_duty(0.0)
            else:
                # pick target sensor measurement
                meas = None
                if isinstance(self.target_sensor_name, str) and self.target_sensor_name in latest:
                    meas = latest[self.target_sensor_name][1]
                else:
                    # if user set a numeric string, or some other path, handle later; default is to skip
                    meas = None
                # If measurement available and pid.setpoint numeric, update pid
                try:
                    target_sp = float(self.pid.setpoint)
                except Exception:
                    target_sp = None
                if meas is not None and target_sp is not None and not rims_disabled:
                    duty = self.pid.update(meas)
                    self.heater.set_duty(duty)
                else:
                    # fallback: set duty 0
                    self.heater.set_duty(0.0)

            # throttle loop to configured interval
            elapsed = time.time() - t0
            time.sleep(max(0.0, self._control_interval - elapsed))

    # helper for GUI to fetch historical arrays (thread-safe)
    def get_history(self, sensor_name, max_points=1000):
        with self._data_lock:
            arr = list(self.data.get(sensor_name, []))
        if max_points and len(arr) > max_points:
            return arr[-max_points:]
        return arr
