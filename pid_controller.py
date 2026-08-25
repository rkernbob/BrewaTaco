import time

class PID:
    def __init__(self, kp, ki, kd, setpoint=0.0, output_limits=(0.0, 100.0), integrator_limit=None):
        self.kp = float(kp)
        self.ki = float(ki)
        self.kd = float(kd)
        self.setpoint = float(setpoint)
        self.output_limits = output_limits
        self.integrator_limit = integrator_limit
        self._last_time = time.monotonic()
        self._last_error = 0.0
        self._integral = 0.0

    def reset(self):
        self._last_time = time.monotonic()
        self._last_error = 0.0
        self._integral = 0.0

    def update(self, measurement):
        now = time.monotonic()
        dt = now - self._last_time
        if dt <= 0:
            return 0.0
        error = float(self.setpoint) - float(measurement)
        self._integral += error * dt
        if self.integrator_limit is not None:
            self._integral = max(min(self._integral, self.integrator_limit), -self.integrator_limit)
        derivative = (error - self._last_error) / dt if dt > 0 else 0.0

        out = (self.kp * error) + (self.ki * self._integral) + (self.kd * derivative)
        out = max(self.output_limits[0], min(self.output_limits[1], out))

        self._last_error = error
        self._last_time = now
        return out
