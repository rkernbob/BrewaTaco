import time
import random

# DS18B20 via kernel w1
try:
    from w1thermsensor import W1ThermSensor, Sensor as W1SensorType
    from w1thermsensor.errors import NoSensorFoundError
    HAS_W1 = True
except Exception:
    HAS_W1 = False
    NoSensorFoundError = None

# MAX31856 via Adafruit CircuitPython
try:
    import board
    import busio
    import digitalio
    import adafruit_max31856
    HAS_MAX = True
except Exception:
    HAS_MAX = False

class OneWireSensor:
    def __init__(self, name, device_id=None, simulate=False):
        self.name = name
        self.device_id = device_id
        self.simulate = simulate
        self.value_c = None
        self.error = None
        self._sensor = None
        if not self.simulate and not HAS_W1:
            raise RuntimeError("w1thermsensor not found. Install w1thermsensor and enable w1 on the Pi.")
        if not self.simulate:
            try:
                if device_id:
                    # create sensor by ID
                    self._sensor = W1ThermSensor(sensor_type=W1SensorType.DS18B20, sensor_id=device_id)
                else:
                    # fallback: first sensor
                    self._sensor = W1ThermSensor()
            except NoSensorFoundError as error:
                # Keep the application running; read() will report no value and
                # the GUI will display this probe as unavailable.
                self.error = str(error)

    def read(self):
        if self.simulate:
            self.value_c = 20.0 + 15.0 * random.random()
            return self.value_c
        if self._sensor is None:
            self.value_c = None
            return None
        try:
            self.value_c = self._sensor.get_temperature()
        except Exception:
            self.value_c = None
        return self.value_c

class MAX31856Sensor:
    def __init__(self, name, cs_pin, simulate=False):
        self.name = name
        self.cs_pin = cs_pin
        self.simulate = simulate
        self.value_c = None
        if not self.simulate and not HAS_MAX:
            raise RuntimeError("Adafruit MAX31856 support not available (install adafruit-blinka and adafruit-circuitpython-max31856)")
        if not self.simulate:
            # Create SPI object and digital CS pin. On Raspberry Pi with Blinka, board.SCLK/MOSI/MISO exist.
            spi = busio.SPI(board.SCLK, board.MOSI, board.MISO)
            # cs_pin should be a board pin name like board.D5 (if using numeric int in config, adapt here)
            try:
                cs = digitalio.DigitalInOut(getattr(board, f"D{int(self.cs_pin)}"))
            except Exception:
                # try using CE0/CE1 names if user passed 0 or 1
                if str(self.cs_pin) in ("0", "1", 0, 1):
                    cs = digitalio.DigitalInOut(getattr(board, f"CE{self.cs_pin}"))
                else:
                    raise
            self._max = adafruit_max31856.MAX31856(spi, cs)
        else:
            self._max = None

    def read(self):
        if self.simulate:
            self.value_c = 90.0 * random.random()
            return self.value_c
        try:
            self.value_c = self._max.temperature
        except Exception:
            self.value_c = None
        return self.value_c
