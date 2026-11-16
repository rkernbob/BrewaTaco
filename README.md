# BrewaTaco

BrewaTaco is a Python temperature-monitoring and mash-control application designed for a Raspberry Pi 4. It provides a PySide6 touchscreen-friendly dashboard, live temperature plots, PID control, and time-proportional heater output for homebrewing and similar temperature-managed tasks.

> **Safety:** Keep the heater disconnected while installing and testing. Software interlocks are not a substitute for correctly rated hardware thermal cutoffs, safe electrical wiring, or supervision by the operator.

## Features

- Reads configured DS18B20 one-wire probes and a MAX31856 thermocouple.
- Displays sensor readings, connection status, heater mode, and a live temperature plot.
- Supports automatic PID control and manual heater-off/full modes.
- Applies a sensor watchdog and RIMS over-temperature cutoff with hysteresis; these interlocks override manual output modes.
- Offers a simulation mode for exercising the application without sensor hardware.

## Requirements

- Raspberry Pi 4 running Raspberry Pi OS (or another supported Linux system) and Python 3.
- Hardware interfaces and libraries appropriate to your sensors and GPIO setup for real-hardware operation.
- Git, if you are cloning this repository.

## Install and run

Run these commands from a terminal on the Pi. If you already have the project directory, start with `cd` into it; otherwise clone the repository first:

```bash
git clone https://github.com/rkernbob/BrewaTaco.git
cd BrewaTaco
```

Create and activate a virtual environment (the creation step is needed only once):

```bash
python3 -m venv .venv
source .venv/bin/activate
```

If creating the environment reports that `venv` is unavailable, install the OS package that provides it (typically `python3-venv`), then retry. With the environment active, install the Python dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Start the application with hardware enabled:

```bash
python run.py
```

To start the GUI in simulation mode without accessing the physical sensors or heater, run:

```bash
python run.py --simulate
```

Press **Ctrl+C** in the terminal to stop the application. When you open a new terminal later, activate the existing environment again before running the app:

```bash
cd ~/BrewaTaco
source .venv/bin/activate
python run.py
```

Leave the environment with `deactivate` when finished. The `.venv` directory is local to your checkout and should not be committed.

## Hardware and configuration

Before running against real hardware:

1. Enable and verify the Raspberry Pi interfaces required by your wiring (one-wire and SPI, as applicable).
2. Edit `config.yaml`: replace the example one-wire sensor IDs with the IDs detected on your Pi, and check the MAX31856 chip-select and heater GPIO settings against your actual wiring.
3. Check all sensor names and probe locations, control and safety settings, and wiring before enabling heater output. Treat the supplied pin values, IDs, PID settings, and temperature thresholds as starting points to confirm against your actual installation.
4. First run with the heater disconnected. Confirm that sensors report plausible readings and test the interface in simulation mode. Have independent, correctly rated hardware over-temperature protection and a safe wiring layout before re-enabling real heater control.

The `--simulate` option substitutes simulated sensor/heater behavior; it does not validate physical wiring, real sensors, or hardware safety devices.

Key control values in `config.yaml`:

- `control.cycle_time_seconds`: the full duration of one heater duty cycle, in seconds. The controller switches the heater on and off across this window to achieve the requested duty percentage; shorter cycles respond more quickly, while longer cycles smooth the output. A value like `2.0` means the SSR can be on for 1.0s and off for 1.0s at 50% duty.
- `control.control_interval_s`: how often the application recalculates the PID output and updates the heater duty, in seconds. This should be short enough to keep the temperature loop responsive, but not so short that it overburdens the CPU or causes unnecessary chattering. A value like `0.5` means the controller checks and updates roughly twice per second.

## Project files

- `run.py` — application entry point (`--config` selects a configuration file; `--simulate` enables simulation).
- `config.yaml` — sensor IDs, pin settings, control parameters, safety limits, and display thresholds.
- `gui.py` — PySide6 dashboard and temperature plots.
- `controller.py` — sensor polling, PID control, and safety interlocks.
- `sensors.py` — DS18B20 and MAX31856 sensor interfaces.
- `pid_controller.py` — PID implementation.
- `heater.py` — time-proportional heater output control.
- `requirements.txt` — Python package dependencies.
- `brewataco.service` — example systemd unit; edit its user, paths, and Python executable to match your installation before using it.

## Troubleshooting

- **`python3 -m venv` fails:** install the OS package that provides Python's `venv` module, then recreate the environment.
- **A Python module is missing:** activate `.venv` and run `python -m pip install -r requirements.txt` again.
- **Sensor readings are missing:** check the configured sensor IDs, enabled interfaces, wiring, and permissions. The GUI indicates missing readings; the controller watchdog forces heater output to zero when it detects a stalled or invalid sensor.
- **GUI does not open:** run from the Pi's graphical desktop session and inspect the terminal output for Qt or display errors.

## Development notes

The GUI receives periodic updates from the controller. Sensor polling and control run in background threads, and temperature history is bounded by the `logging.history_length` setting in `config.yaml`.
