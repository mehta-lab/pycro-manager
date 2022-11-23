from pytest import fixture
import os
import glob
import json


@fixture(scope="session")
def enable_zmq():
    # FIXME: this enviroment variable only works on Windows
    profile_path = os.path.expandvars(r"%LOCALAPPDATA%\Micro-Manager\UserProfiles")
    profile_file = glob.glob(os.path.join(profile_path, "Default_*.json"))[0]
    with open(profile_file, "r") as f:
        profile = json.load(f)
    profile["map"]["Preferences"]["scalar"]["org.micromanager.internal.MMStudio"][
        "scalar"
    ]["run ZQM server"][
        "scalar"
    ] = True  # TODO: "ZQM" is an upstream typo https://github.com/micro-manager/micro-manager/issues/1574
    with open(profile_file, "w") as f:
        json.dump(profile, f)
