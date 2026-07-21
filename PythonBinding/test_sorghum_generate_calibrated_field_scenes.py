from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sorghum_generate_calibrated_field_scenes import promote_staged_scene


class SorghumScenePromotionTest(unittest.TestCase):
    def test_promotes_scene_and_renames_metadata_without_rewriting_staged_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            assets = project / "Assets"
            folder = assets / "GeneratedAssets" / "Scenes"
            folder.mkdir(parents=True)
            staged = Path("GeneratedAssets/Scenes/_Staging_Field_123.evescene")
            target = Path("GeneratedAssets/Scenes/Field.evescene")
            (assets / staged).write_text("new scene", encoding="utf-8")
            (assets / f"{staged.as_posix()}.evefilemeta").write_text(
                "name: _Staging_Field_123\n", encoding="utf-8"
            )
            (assets / target).write_text("old scene", encoding="utf-8")
            (assets / f"{target.as_posix()}.evefilemeta").write_text("name: Field\n", encoding="utf-8")

            promote_staged_scene(project, staged, target)

            self.assertEqual((assets / target).read_text(encoding="utf-8"), "new scene")
            self.assertEqual(
                (assets / f"{target.as_posix()}.evefilemeta").read_text(encoding="utf-8"),
                "name: Field\n",
            )
            self.assertFalse((assets / staged).exists())
            self.assertFalse((assets / f"{staged.as_posix()}.evefilemeta").exists())


if __name__ == "__main__":
    unittest.main()
