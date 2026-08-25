import threading
import time

try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except Exception:
    HAS_GPIO = False

class HeaterController:
    """
    Time-proportional SSR controller.
    set_duty(percent) controls fraction of cycle_time the SSR is ON.
    enable(False) forces duty to 0 without losing the stored duty (so you can re-enable).
    """
    def __init__(self, gpio_pin, cycle_time=2.0, simulate=False):
        self.gpio_pin = int(gpio_pin)
        self.cycle_time = float(cycle_time)
        self.simulate = simulate
        self._duty = 0.0
        self._enabled = True
        self._stop = False
        self._lock = threading.Lock()
        if not self.simulate and not HAS_GPIO:
            raise RuntimeError("RPi.GPIO is not available.")
        if not self.simulate:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.gpio_pin, GPIO.OUT)
            GPIO.output(self.gpio_pin, GPIO.LOW)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def set_duty(self, percent):
        with self._lock:
            self._duty = max(0.0, min(100.0, float(percent)))

    def enable(self, v=True):
        with self._lock:
            self._enabled = bool(v)

    def stop(self):
        self._stop = True
        self._thread.join(timeout=2.0)
        if not self.simulate:
            GPIO.output(self.gpio_pin, GPIO.LOW)
            GPIO.cleanup(self.gpio_pin)

    def _run(self):
        while not self._stop:
            with self._lock:
                duty = self._duty if self._enabled else 0.0
            on_time = (duty / 100.0) * self.cycle_time
            off_time = self.cycle_time - on_time
            if on_time > 0:
                if not self.simulate:
                    GPIO.output(self.gpio_pin, GPIO.HIGH)
                time.sleep(on_time)
            if off_time > 0:
                if not self.simulate:
                    GPIO.output(self.gpio_pin, GPIO.LOW)
                time.sleep(off_time)
