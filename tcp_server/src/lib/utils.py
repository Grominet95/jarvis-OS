import time
import sys
import json
from .constants import SETTINGS_PATH


class ThrottledCallback:
    def __init__(self, callback, min_interval):
        self.callback = callback
        self.min_interval = min_interval
        self.last_call = 0

    def __call__(self, *args, **kwargs):
        current_time = time.time()
        if current_time - self.last_call > self.min_interval:
            self.callback(*args, **kwargs)
            self.last_call = current_time


def is_macos():
    return sys.platform == 'darwin'


def is_windows():
    return sys.platform == 'win32'


def is_linux():
    return sys.platform == 'linux'


def get_settings(key):
    with open(SETTINGS_PATH) as f:
        settings = json.load(f)

    return settings[key]
