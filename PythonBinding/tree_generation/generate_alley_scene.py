import os
import runpy
from pathlib import Path

os.environ["ECOSYSLAB_SCENE_KIND"] = "alley"
runpy.run_path(Path(__file__).with_name("_generate_tree_scene.py"), run_name="__main__")
