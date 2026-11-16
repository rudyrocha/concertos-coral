import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coral_editor import (  # noqa: E402
    SCHEMA,
    add_nostdin,
    final_time,
    hidden_process_kwargs,
    migrate_project,
    source_times,
    validate_project,
    write_chapters,
)


def sample_project():
    return {
        "schema": SCHEMA,
        "event": "Teste",
        "event_date": "2026-01-01",
        "choir": "Coral",
        "chapter_opening": "Abertura - Teste",
        "sync": {"offset_seconds": 5.0, "clock_ratio": 1.00001, "video_pts_offset": 0.05},
        "source_video": {"width": 1920, "height": 1080, "interlaced": True},
        "crop": {"width": 1728, "height": 972, "x": 96, "y": 54},
        "trim": {"before_seconds": 10.0, "after_seconds": 10.0},
        "tracks": [
            {"id": "a", "kind": "music", "title": "Faixa 1", "credits": "A", "start_tascam": 100.0, "enabled": True},
            {"id": "b", "kind": "encore", "title": "BIS", "credits": "B", "start_tascam": 200.0, "enabled": True},
        ],
        "last_end_tascam": 260.0,
        "audio_gain_db": 1.0,
        "overlay_enabled": True,
        "overlay_duration_seconds": 7.0,
        "export": {"width": 1920, "height": 1080, "duration_tolerance_seconds": 0.5},
        "output_file": "teste.mp4",
    }


class ProjectRulesTest(unittest.TestCase):
    def test_ffmpeg_receives_nostdin(self):
        command = add_nostdin(["ffmpeg", "-i", "entrada.wav"])
        self.assertEqual(command[1], "-nostdin")
        self.assertEqual(command.count("-nostdin"), 1)
        self.assertEqual(add_nostdin(command).count("-nostdin"), 1)

    def test_hidden_process_disables_stdin(self):
        kwargs = hidden_process_kwargs()
        self.assertIsNotNone(kwargs["stdin"])
        self.assertIn("creationflags", kwargs)
        self.assertIn("startupinfo", kwargs)

    def test_time_mapping_and_duration(self):
        project = sample_project()
        times = source_times(project)
        self.assertAlmostEqual(times["camera_start"], (100.0 - 5.0) / 1.00001 - 10.0)
        self.assertAlmostEqual(times["audio_start"], 100.0 - 10.0 * 1.00001)
        self.assertAlmostEqual(final_time(project, 100.0), 10.0)
        self.assertAlmostEqual(final_time(project, 200.0), 10.0 + 100.0 / 1.00001)

    def test_validation_accepts_valid_project(self):
        validate_project(sample_project())

    def test_validation_rejects_non_chronological_tracks(self):
        project = sample_project()
        project["tracks"][0]["start_tascam"] = 220.0
        with self.assertRaisesRegex(ValueError, "cronológica"):
            validate_project(project)

    def test_validation_rejects_crop_outside_source(self):
        project = sample_project()
        project["crop"]["x"] = 300
        with self.assertRaisesRegex(ValueError, "limites"):
            validate_project(project)

    def test_v1_migration_preserves_content(self):
        old = {
            "schema": "coral-paineiras-project-v1",
            "event": "Antigo",
            "sync": {"offset_seconds": 4.9, "clock_ratio": 1.0},
            "crop": {"width": 1920, "height": 1080, "x": 0, "y": 0},
            "tracks": [{"id": 1, "title": "Canção", "credits": "Autor", "start_tascam": 60, "enabled": True}],
            "last_end_tascam": 120,
            "audio_gain_db": None,
            "output_file": "antigo.mp4",
        }
        migrated = migrate_project(old)
        self.assertEqual(migrated["schema"], SCHEMA)
        self.assertEqual(migrated["event"], "Antigo")
        self.assertEqual(migrated["tracks"][0]["title"], "Canção")
        self.assertEqual(migrated["tracks"][0]["kind"], "music")
        self.assertEqual(migrated["trim"]["before_seconds"], 10.0)
        validate_project(migrated)

    def test_chapters_include_encore(self):
        project = sample_project()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chapters.txt"
            write_chapters(project, path)
            text = path.read_text(encoding="utf-8")
        self.assertIn("00:00 Abertura - Teste", text)
        self.assertIn("00:10 Faixa 1", text)
        self.assertIn("BIS", text)


if __name__ == "__main__":
    unittest.main()
