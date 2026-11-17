import json
import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coral_editor import (  # noqa: E402
    CoralApplication,
    SCHEMA,
    VERSION,
    _best_lag,
    add_nostdin,
    final_time,
    hidden_process_kwargs,
    is_placeholder_project,
    migrate_project,
    parse_repertoire_text,
    source_times,
    validate_media_bounds,
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

    def test_long_margins_and_cuts_are_not_limited_to_120_seconds(self):
        project = sample_project()
        project["tracks"][0]["start_tascam"] = 400.0
        project["tracks"][1]["start_tascam"] = 500.0
        project["last_end_tascam"] = 600.0
        project["trim"] = {"before_seconds": 200.0, "after_seconds": 180.0}
        project["sync"] = {"offset_seconds": 0.0, "clock_ratio": 1.0}
        project["camera_duration_seconds"] = 900.0
        project["audio_duration_seconds"] = 900.0
        validate_project(project)
        times = source_times(project)
        self.assertEqual(times["camera_start"], 200.0)
        self.assertEqual(times["camera_end"], 780.0)

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

    def test_markdown_repertoire_numbered_list(self):
        text = """# Programa\n\n1. Aquarela do Brasil — Ary Barroso\n2. Trem das Onze | Adoniran Barbosa\n3. BIS\n"""
        tracks = parse_repertoire_text(text)
        self.assertEqual([track["title"] for track in tracks], ["Aquarela do Brasil", "Trem das Onze", "BIS"])
        self.assertEqual(tracks[0]["credits"], "Ary Barroso")
        self.assertEqual(tracks[1]["credits"], "Adoniran Barbosa")

    def test_multiline_numbered_program_keeps_credits_with_their_music(self):
        text = (
            "Programa do concerto\n\n1\\)\n**Cuitelinho&#xA0;**\n"
            "Tema tradicional de Mato Grosso\nContribuições de intérpretes\n\n"
            "2) Haikais de Primavera | Yara Campos\n\n3)\n"
            "**Estão voltando as flores**\nPaulo Soledade"
        )
        self.assertEqual(parse_repertoire_text(text), [
            {"title": "Cuitelinho", "credits": "Tema tradicional de Mato Grosso Contribuições de intérpretes"},
            {"title": "Haikais de Primavera", "credits": "Yara Campos"},
            {"title": "Estão voltando as flores", "credits": "Paulo Soledade"},
        ])

    def test_sync_sample_uses_camera_time_and_unsaved_settings(self):
        app = CoralApplication.__new__(CoralApplication)
        app.work_dir = Path("unused")
        app.project = sample_project()
        app.project.update(camera_duration_seconds=300, audio_duration_seconds=310)
        saved = dict(app.project["sync"])
        output, project, timing = app.sync_sample(
            {"slot": "B", "camera_start": 250, "offset": 6.7, "ratio": 1.001}
        )
        self.assertEqual(output.name, "sync-B.mp4")
        self.assertAlmostEqual(timing["audio_start"], 256.95)
        self.assertAlmostEqual(timing["audio_end"], 266.96)
        self.assertEqual(timing["duration"], 10)
        self.assertEqual(project["sync"]["offset_seconds"], 6.7)
        self.assertEqual(app.project["sync"], saved)
        with self.assertRaisesRegex(ValueError, "área comum"):
            app.sync_sample({"slot": "A", "camera_start": 295, "offset": 6.7, "ratio": 1})

    def test_placeholder_from_version_21_is_detected(self):
        project = migrate_project(
            {
                "schema": SCHEMA,
                "event": "Novo concerto",
                "tracks": [
                    {
                        "title": "Primeira música",
                        "start_tascam": 60.0,
                        "enabled": True,
                    }
                ],
                "last_end_tascam": 120.0,
            }
        )
        self.assertTrue(is_placeholder_project(project))

    def test_best_lag_reports_tascam_lead_in(self):
        camera = [0.0, 1.0, -0.5, 0.25, 0.75, -1.0]
        tascam = [0.3, -0.2, 0.1] + camera + [0.4]
        lag, score = _best_lag(camera, tascam, -5, 5, 5)
        self.assertEqual(lag, 3)
        self.assertGreater(score, 0.99)

    def test_offset_clips_to_real_media_instead_of_negative_trim(self):
        project = sample_project()
        project["tracks"][0]["start_tascam"] = 10.0
        project["tracks"][1]["start_tascam"] = 50.0
        project["last_end_tascam"] = 70.0
        project["sync"]["offset_seconds"] = 6.0
        project["sync"]["clock_ratio"] = 1.0
        project["camera_duration_seconds"] = 80.0
        project["audio_duration_seconds"] = 90.0
        times = source_times(project)
        self.assertEqual(times["camera_start"], 0.0)
        self.assertEqual(times["audio_start"], 6.0)
        self.assertTrue(times["trim_clipped_start"])
        self.assertAlmostEqual(final_time(project, 10.0), 4.0)

    def test_incompatible_offset_is_reported_without_invalid_trim(self):
        project = sample_project()
        project["tracks"][0]["start_tascam"] = 1.0
        project["tracks"][1]["start_tascam"] = 4.0
        project["last_end_tascam"] = 7.0
        project["sync"]["offset_seconds"] = 6.0
        project["sync"]["clock_ratio"] = 1.0
        project["camera_duration_seconds"] = 8.0
        project["audio_duration_seconds"] = 10.0
        times = source_times(project)
        self.assertEqual(times["camera_start"], 0.0)
        self.assertTrue(times["markers_outside_overlap"])

    def test_balanced_audio_uses_compression_and_loudness_normalization(self):
        project = sample_project()
        project["audio_processing"] = {"mode": "balanced"}
        app = CoralApplication.__new__(CoralApplication)
        graph = app.filter_graph(project, final=False)
        self.assertIn("acompressor=", graph)
        self.assertIn("loudnorm=I=-16.0:LRA=9.0:TP=-1.5", graph)

    def test_previous_preview_supplies_fallback_for_invalid_sync(self):
        project = sample_project()
        project["preview"] = {"audio_start_tascam": 12.0, "audio_end_tascam": 72.0}
        timing = CoralApplication.preview_fallback_timing(project)
        self.assertEqual(timing["audio_start"], 12.0)
        self.assertEqual(timing["audio_end"], 72.0)
        self.assertTrue(timing["using_previous_preview"])

    def test_windows_launcher_prefers_offline_videos_folder(self):
        launcher = (Path(__file__).resolve().parents[1] / "Editor de Concertos.vbs").read_text(
            encoding="utf-8"
        )
        self.assertIn(r'D:\OFFline\Videos', launcher)
        self.assertIn("FolderExists(startFolder)", launcher)

    def test_interface_detects_outdated_server_without_json_parse_error(self):
        root = Path(__file__).resolve().parents[1]
        interface = (root / "editor.html").read_text(encoding="utf-8")
        backend = (root / "coral_editor.py").read_text(encoding="utf-8")
        model = json.loads((root / "projeto_modelo.json").read_text(encoding="utf-8"))
        self.assertIn(f"const UI_VERSION='{VERSION}'", interface)
        self.assertIn("response.text()", interface)
        self.assertNotIn("response.json()", interface)
        self.assertIn("if(s.running&&!wasRendering)", interface)
        self.assertIn("if args.prepare_only:\n                wait_for_render(app, fatal=True)", backend)
        self.assertEqual(model["app_version"], VERSION)

    def test_media_bounds_reject_corrupted_markers(self):
        project = sample_project()
        project["audio_duration_seconds"] = 300.0
        project["tracks"][0]["start_tascam"] = 2_497.0
        project["last_end_tascam"] = 10_726.0
        with self.assertRaisesRegex(ValueError, "Reparar marcações"):
            validate_media_bounds(project)

    def test_timeline_repair_archives_and_redistributes_enabled_tracks(self):
        project = sample_project()
        project["camera_duration_seconds"] = 1_637.182
        project["audio_duration_seconds"] = 1_645.793
        project["tracks"][0]["start_tascam"] = 2_497.0
        project["tracks"][1]["start_tascam"] = 3_687.0
        project["last_end_tascam"] = 10_726.0
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = CoralApplication.__new__(CoralApplication)
            app.work_dir = root
            app.project_path = root / "projeto.json"
            app.chapters_path = root / "capitulos.txt"
            app.ass_path = root / "legendas.ass"
            app.project_path.write_text(json.dumps(project), encoding="utf-8")
            backup = app.repair_timeline()
            repaired = json.loads(app.project_path.read_text(encoding="utf-8"))
        self.assertTrue(backup.name.startswith("projeto_antes_reparo_"))
        self.assertEqual(repaired["tracks"][0]["start_tascam"], 10.0)
        self.assertLess(repaired["tracks"][-1]["start_tascam"], 1_637.182)
        self.assertFalse(repaired["tracks"][0]["confirmed"])
        self.assertFalse(repaired["last_end_confirmed"])


if __name__ == "__main__":
    unittest.main()
