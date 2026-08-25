import argparse
from controller import Controller
from gui import run_gui

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BrewaTaco controller (PySide6 GUI)")
    parser.add_argument("--config", default="config.yaml", help="path to config.yaml")
    parser.add_argument("--simulate", action="store_true", help="run in simulation mode")
    args = parser.parse_args()

    controller = Controller(config_path=args.config, simulate=args.simulate)
    try:
        run_gui(controller)
    except KeyboardInterrupt:
        pass
    finally:
        controller.stop()
