from pytest import fixture
import os
import glob
import json


@fixture(scope="session")
def enable_zmq():
    # FIXME: this enviroment variable only works on Windows
    profile_path = os.path.expandvars(r"%LOCALAPPDATA%\Micro-Manager\UserProfiles")
    profile_file = glob.glob(os.path.join(profile_path, "Default_*.json"))[0]
    with open(profile_file, "r+") as f:
        profile = json.load(f)
        profile["map"]["Preferences"]["scalar"]["org.micromanager.internal.MMStudio"][
            "scalar"
        ]["run ZMQ server"]["scalar"] = True
        json.dump(profile, f)
