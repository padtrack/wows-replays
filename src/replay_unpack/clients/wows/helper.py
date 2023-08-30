import importlib
import os

from replay_unpack.core.entity_def.definitions import Definitions

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def get_definitions(version):
    return Definitions(os.path.join(BASE_DIR, "versions", version))


def get_controller(version):
    """
    Get real controller class by game version.
    """
    try:
        module = importlib.import_module(f".versions.{version}", package=__package__)
    except ModuleNotFoundError:
        raise RuntimeError(f"Version {version} is unsupported")

    try:
        return module.BattleController
    except AttributeError:
        raise AssertionError(f"Version {version} does not contain a BattleController")
