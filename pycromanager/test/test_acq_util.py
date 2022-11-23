import os
# tested code
from pycromanager import start_headless

def test_start_headless():
    mm_app_path = "C:\Program Files\Micro-Manager-2.0"
    config_file = os.path.join(mm_app_path, "MMConfig_demo.cfg")
    start_headless(mm_app_path, config_file, timeout=5000)