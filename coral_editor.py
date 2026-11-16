#!/usr/bin/env python3
"""Editor local assistido para gravações de concertos corais.

Usa somente a biblioteca padrão do Python e FFmpeg/FFprobe. Os arquivos de
origem nunca são alterados. A interface é servida apenas em 127.0.0.1.
"""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
import webbrowser
import zipfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable


VERSION = "2.1.0"
APP_ID = "concertos-coral"
DEFAULT_PORT = 8765
SCHEMA = "concertos-coral-project-v2"
WORK_FOLDER_NAME = "_CoralEditor"
PROJECT_FILE_NAME = "projeto.json"
INITIAL_PROJECT_NAMES = ("projeto_inicial.json", "Projeto_Coral.json")
PREVIEW_FILE_NAME = "preview.mp4"
ASS_FILE_NAME = "legendas.ass"
CHAPTERS_FILE_NAME = "capitulos_youtube.txt"
REPORT_FILE_NAME = "relatorio_exportacao.json"


def fail(message: str, code: int = 1) -> None:
    if sys.platform == "win32" and getattr(sys, "stderr", None) is None:
        try:
            ctypes.windll.user32.MessageBoxW(0, message, "Editor de Concertos", 0x10)
        except Exception:
            pass
    else:
        print(f"\nERRO: {message}", file=sys.stderr)
    raise SystemExit(code)


def hidden_startupinfo() -> Any:
    """Solicita janela oculta para subprocessos no Windows."""
    if sys.platform != "win32":
        return None
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    return startup


def hidden_process_kwargs() -> dict[str, Any]:
    """Impede console e entrada interativa em FFmpeg/FFprobe no Windows."""
    return {
        "stdin": subprocess.DEVNULL,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        "startupinfo": hidden_startupinfo(),
    }


def add_nostdin(command: list[str]) -> list[str]:
    command = list(command)
    if command and Path(str(command[0])).stem.lower() == "ffmpeg" and "-nostdin" not in command:
        command.insert(1, "-nostdin")
    return command


def locate_tool(name: str, script_dir: Path) -> str:
    for candidate in (script_dir / f"{name}.exe", script_dir / name):
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    fail(
        f"{name} não foi encontrado. Instale o FFmpeg ou coloque "
        f"{name}.exe na pasta do editor."
    )
    raise AssertionError("unreachable")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def seconds_to_clock(seconds: float, decimals: int = 3) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remaining = seconds % 60
    width = 2 + (1 + decimals if decimals else 0)
    return f"{hours:02d}:{minutes:02d}:{remaining:0{width}.{decimals}f}"


def seconds_to_youtube(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def seconds_to_ass(seconds: float) -> str:
    value = max(0.0, seconds)
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    secs = value % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def slugify(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())
    return normalized.strip("_") or "concerto"


def ass_escape(text: str) -> str:
    return (
        str(text)
        .replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\r\n", r"\N")
        .replace("\n", r"\N")
    )


def enabled_tracks(project: dict[str, Any]) -> list[dict[str, Any]]:
    return [track for track in project.get("tracks", []) if track.get("enabled", True)]


def trim_values(project: dict[str, Any]) -> tuple[float, float]:
    trim = project.get("trim", {})
    return float(trim.get("before_seconds", 10.0)), float(trim.get("after_seconds", 10.0))


def source_times(project: dict[str, Any]) -> dict[str, float]:
    tracks = enabled_tracks(project)
    if not tracks:
        raise ValueError("O projeto não possui músicas habilitadas.")
    first = float(tracks[0]["start_tascam"])
    last_end = float(project["last_end_tascam"])
    offset = float(project["sync"]["offset_seconds"])
    ratio = float(project["sync"]["clock_ratio"])
    video_pts_offset = float(project["sync"].get("video_pts_offset", 0.0))
    before, after = trim_values(project)

    first_camera = (first - offset) / ratio
    last_camera = (last_end - offset) / ratio
    camera_start = first_camera - before
    camera_end = last_camera + after
    audio_start = first - before * ratio
    audio_end = last_end + after * ratio
    return {
        "camera_start": camera_start,
        "camera_end": camera_end,
        "video_filter_start": camera_start - video_pts_offset,
        "video_filter_end": camera_end - video_pts_offset,
        "audio_start": audio_start,
        "audio_end": audio_end,
        "duration": camera_end - camera_start,
    }


def final_time(project: dict[str, Any], absolute_tascam: float) -> float:
    tracks = enabled_tracks(project)
    if not tracks:
        raise ValueError("O projeto não possui músicas habilitadas.")
    first = float(tracks[0]["start_tascam"])
    ratio = float(project["sync"]["clock_ratio"])
    before, _ = trim_values(project)
    return before + (float(absolute_tascam) - first) / ratio


def migrate_project(project: dict[str, Any]) -> dict[str, Any]:
    """Converte projetos da primeira versão sem perder dados do concerto."""
    migrated = json.loads(json.dumps(project))
    if migrated.get("schema") == SCHEMA:
        return migrated

    migrated["schema"] = SCHEMA
    migrated.setdefault("app_version", VERSION)
    migrated.setdefault("choir", "Coral Paineiras")
    migrated.setdefault("notice", "")
    migrated.setdefault("trim", {"before_seconds": 10.0, "after_seconds": 10.0})
    migrated.setdefault(
        "source_video",
        {"width": 1920, "height": 1080, "frame_rate": "30000/1001", "interlaced": True},
    )
    migrated.setdefault(
        "export",
        {
            "width": 1920,
            "height": 1080,
            "video_crf": 18,
            "video_preset": "slow",
            "audio_bitrate": "384k",
            "duration_tolerance_seconds": 0.5,
        },
    )
    migrated.setdefault("chapter_opening", f"Abertura - {migrated.get('event', 'Concerto')}")
    migrated.setdefault("overlay_duration_seconds", 7.0)
    migrated.setdefault("overlay_enabled", True)
    migrated.setdefault("audio_gain_db", 0.0)
    migrated.setdefault("sync", {"offset_seconds": 0.0, "clock_ratio": 1.0, "video_pts_offset": 0.0})
    migrated.setdefault("crop", {"width": 1920, "height": 1080, "x": 0, "y": 0})
    for position, track in enumerate(migrated.get("tracks", []), start=1):
        track["id"] = str(track.get("id") or uuid.uuid4())
        track.setdefault("kind", "music")
        track.setdefault("enabled", True)
        track.setdefault("title", f"Música {position}")
        track.setdefault("credits", "")
    migrated["app_version"] = VERSION
    return migrated


def validate_project(project: dict[str, Any]) -> None:
    tracks = enabled_tracks(project)
    if not tracks:
        raise ValueError("Pelo menos uma música deve permanecer habilitada.")
    starts = [float(track["start_tascam"]) for track in tracks]
    if starts != sorted(starts):
        raise ValueError("As músicas habilitadas precisam estar em ordem cronológica.")
    if any(right <= left for left, right in zip(starts, starts[1:])):
        raise ValueError("Duas músicas habilitadas não podem ter o mesmo início.")
    if any(not str(track.get("title", "")).strip() for track in tracks):
        raise ValueError("Toda música habilitada precisa ter título.")

    before, after = trim_values(project)
    if not 0 <= before <= 120 or not 0 <= after <= 120:
        raise ValueError("As margens de corte devem ficar entre 0 e 120 segundos.")
    if starts[0] < before:
        raise ValueError("Não há tempo disponível para a margem antes da primeira música.")
    last_end = float(project.get("last_end_tascam", 0))
    if last_end <= starts[-1]:
        raise ValueError("O fim musical deve ocorrer depois do início da última música.")

    raw_gain = project.get("audio_gain_db")
    if raw_gain is not None:
        gain = float(raw_gain)
        if not -24.0 <= gain <= 24.0:
            raise ValueError("O ganho de áudio deve ficar entre -24 dB e +24 dB.")
    ratio = float(project.get("sync", {}).get("clock_ratio", 0.0))
    if not 0.95 <= ratio <= 1.05:
        raise ValueError("A correção de relógio está fora do intervalo seguro.")

    source = project.get("source_video", {})
    source_width = int(source.get("width", 0))
    source_height = int(source.get("height", 0))
    crop = project.get("crop", {})
    width = int(crop.get("width", 0))
    height = int(crop.get("height", 0))
    x = int(crop.get("x", -1))
    y = int(crop.get("y", -1))
    if min(source_width, source_height, width, height) <= 0 or min(x, y) < 0:
        raise ValueError("O enquadramento contém valores inválidos.")
    if x + width > source_width or y + height > source_height:
        raise ValueError("O enquadramento ultrapassa os limites do vídeo original.")
    if any(value % 2 for value in (width, height, x, y)):
        raise ValueError("Posição e dimensões do enquadramento devem ser números pares.")
    export = project.get("export", {})
    target_ratio = float(export.get("width", 1920)) / float(export.get("height", 1080))
    if abs(width / height - target_ratio) > 0.002:
        raise ValueError("O enquadramento precisa manter a proporção da exportação.")


def resolve_sources(project: dict[str, Any], source: Path) -> tuple[list[Path], Path]:
    camera = [source / name for name in project.get("camera_files", [])]
    audio = source / str(project.get("audio_file", ""))
    if camera and all(path.is_file() for path in camera) and audio.is_file():
        return camera, audio

    camera = sorted(
        {
            path.resolve()
            for pattern in ("*.MTS", "*.mts", "*.M2TS", "*.m2ts")
            for path in source.glob(pattern)
        },
        key=lambda item: item.name.lower(),
    )
    wavs = sorted(
        {
            path.resolve()
            for pattern in ("*.WAV", "*.wav")
            for path in source.glob(pattern)
        },
        key=lambda item: item.name.lower(),
    )
    if not camera:
        raise ValueError("Nenhum arquivo MTS/M2TS foi encontrado na pasta do concerto.")
    if len(wavs) != 1:
        raise ValueError(f"Esperado exatamente um WAV; encontrados: {len(wavs)}.")
    project["camera_files"] = [path.name for path in camera]
    project["audio_file"] = wavs[0].name
    return camera, wavs[0]


def concat_protocol_url(paths: Iterable[Path]) -> str:
    normalized: list[str] = []
    for path in paths:
        value = path.resolve().as_posix()
        if "|" in value:
            raise ValueError("O caminho dos MTS não pode conter o caractere |.")
        normalized.append(value)
    return "concat:" + "|".join(normalized)


def probe_duration(ffprobe: str, path: Path) -> float:
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **hidden_process_kwargs(),
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Não foi possível medir a duração de {path.name}.")
    return float(completed.stdout.strip())


def detect_peak_gain(ffmpeg: str, audio_path: Path, project: dict[str, Any], log_path: Path) -> float:
    timing = source_times(project)
    command = add_nostdin([
        ffmpeg,
        "-hide_banner",
        "-nostats",
        "-ss",
        f"{timing['audio_start']:.6f}",
        "-t",
        f"{timing['audio_end'] - timing['audio_start']:.6f}",
        "-i",
        str(audio_path),
        "-af",
        "volumedetect",
        "-f",
        "null",
        "-",
    ])
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **hidden_process_kwargs(),
    )
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("\n[Análise de pico]\n")
        handle.write(subprocess.list2cmdline(command) + "\n")
        handle.write(completed.stderr + "\n")
    if completed.returncode != 0:
        raise RuntimeError("Falha ao analisar o nível do WAV.")
    match = re.search(r"max_volume:\s*([-+\d.]+)\s*dB", completed.stderr)
    if not match:
        raise RuntimeError("O FFmpeg não informou o pico máximo do WAV.")
    maximum = float(match.group(1))
    return round(max(-12.0, min(18.0, -2.0 - maximum)), 2)


def write_chapters(project: dict[str, Any], path: Path) -> None:
    lines = [f"00:00 {project.get('chapter_opening') or 'Abertura'}"]
    for track in enabled_tracks(project):
        stamp = seconds_to_youtube(final_time(project, float(track["start_tascam"])))
        lines.append(f"{stamp} {track['title']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_ass(project: dict[str, Any], path: Path) -> None:
    title = ass_escape(f"{project.get('choir', 'Coral')} - {project.get('event', 'Concerto')}")
    header = f"""[Script Info]
Title: {title}
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: LowerThird,Arial,44,&H00FFFFFF,&H00FFFFFF,&H96000000,&H78000000,-1,0,0,0,100,100,0,0,1,3,1,1,90,90,82,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""
    duration = float(project.get("overlay_duration_seconds", 7.0))
    lines = [header]
    for track in enabled_tracks(project):
        start = final_time(project, float(track["start_tascam"]))
        text = rf"{{\fad(300,550)\b1\fs44}}{ass_escape(track['title'])}"
        credits = ass_escape(track.get("credits", ""))
        if credits:
            text += rf"{{\b0\fs28}}\N{credits}"
        lines.append(
            f"Dialogue: 0,{seconds_to_ass(start)},{seconds_to_ass(start + duration)},"
            f"LowerThird,,0,0,0,,{text}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class RenderState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.data: dict[str, Any] = {
            "running": False,
            "kind": None,
            "progress": 0.0,
            "message": "Pronto.",
            "output": None,
            "archive": None,
            "verification": None,
            "error": None,
        }

    def update(self, **values: Any) -> None:
        with self.lock:
            self.data.update(values)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.data)


class CoralApplication:
    def __init__(self, source: Path, script_dir: Path, archive_root: Path | None = None) -> None:
        self.source = source
        self.script_dir = script_dir
        self.work_dir = source / WORK_FOLDER_NAME
        self.work_dir.mkdir(exist_ok=True)
        self.final_dir = self.work_dir / "final"
        self.final_dir.mkdir(exist_ok=True)
        self.project_path = self.work_dir / PROJECT_FILE_NAME
        self.html_path = script_dir / "editor.html"
        self.logo_path = script_dir / "assets" / "Logo_Clube.png"
        self.preview_path = self.work_dir / PREVIEW_FILE_NAME
        self.ass_path = self.work_dir / ASS_FILE_NAME
        self.chapters_path = self.work_dir / CHAPTERS_FILE_NAME
        self.report_path = self.work_dir / REPORT_FILE_NAME
        self.log_path = self.work_dir / "processamento.log"
        self.archive_root = archive_root or source.parent / "_CoralEditor_Arquivos"
        self.ffmpeg = locate_tool("ffmpeg", script_dir)
        self.ffprobe = locate_tool("ffprobe", script_dir)
        self.state = RenderState()

        if self.project_path.exists():
            raw_project = load_json(self.project_path)
        else:
            initial = next((source / name for name in INITIAL_PROJECT_NAMES if (source / name).is_file()), None)
            template = initial or script_dir / "projeto_modelo.json"
            raw_project = load_json(template)
        self.project = migrate_project(raw_project)
        self.project["source_folder"] = str(source)
        self.camera_paths, self.audio_path = resolve_sources(self.project, source)
        validate_project(self.project)
        if self.project.get("audio_gain_db") is None:
            print("Analisando o nível do áudio do Tascam...")
            self.project["audio_gain_db"] = detect_peak_gain(
                self.ffmpeg, self.audio_path, self.project, self.log_path
            )
        atomic_write_json(self.project_path, self.project)
        self.write_outputs()

    def reload_project(self) -> dict[str, Any]:
        self.project = migrate_project(load_json(self.project_path))
        validate_project(self.project)
        return self.project

    def write_outputs(self) -> None:
        write_chapters(self.project, self.chapters_path)
        write_ass(self.project, self.ass_path)

    def public_project(self) -> dict[str, Any]:
        project = json.loads(json.dumps(self.project))
        timing = source_times(project)
        preview = project.setdefault("preview", {})
        preview.setdefault("audio_start_tascam", timing["audio_start"])
        preview.setdefault("audio_end_tascam", timing["audio_end"])
        project["derived"] = {
            **timing,
            "duration_clock": seconds_to_clock(timing["duration"]),
            "final_times": {
                str(track["id"]): final_time(project, float(track["start_tascam"]))
                for track in enabled_tracks(project)
            },
            "last_end_final": final_time(project, float(project["last_end_tascam"])),
            "chapters_file": str(self.chapters_path),
            "final_folder": str(self.final_dir),
            "archive_folder": str(self.archive_root),
            "app_version": VERSION,
        }
        return project

    def save_from_browser(self, payload: dict[str, Any]) -> None:
        current = self.reload_project()
        incoming_tracks = payload.get("tracks")
        if not isinstance(incoming_tracks, list):
            raise ValueError("Lista de músicas ausente.")
        tracks: list[dict[str, Any]] = []
        ids: set[str] = set()
        for position, item in enumerate(incoming_tracks, start=1):
            track_id = str(item.get("id") or uuid.uuid4())
            if track_id in ids:
                track_id = str(uuid.uuid4())
            ids.add(track_id)
            tracks.append(
                {
                    "id": track_id,
                    "kind": "encore" if item.get("kind") == "encore" else "music",
                    "title": str(item.get("title", f"Música {position}")).strip(),
                    "credits": str(item.get("credits", "")).strip(),
                    "start_tascam": float(item["start_tascam"]),
                    "enabled": bool(item.get("enabled", True)),
                }
            )
        current["tracks"] = tracks
        current["event"] = str(payload.get("event", current.get("event", "Concerto"))).strip()
        current["event_date"] = str(payload.get("event_date", current.get("event_date", ""))).strip()
        current["choir"] = str(payload.get("choir", current.get("choir", "Coral Paineiras"))).strip()
        current["notice"] = str(payload.get("notice", current.get("notice", ""))).strip()
        current["chapter_opening"] = str(payload.get("chapter_opening", current.get("chapter_opening", "Abertura"))).strip()
        current["output_file"] = str(payload.get("output_file", current.get("output_file", "concerto.mp4"))).strip()
        if not current["output_file"].lower().endswith(".mp4"):
            current["output_file"] += ".mp4"
        current["last_end_tascam"] = float(payload["last_end_tascam"])
        current["overlay_enabled"] = bool(payload.get("overlay_enabled", True))
        current["audio_gain_db"] = float(payload.get("audio_gain_db", 0.0))
        current["trim"] = {
            "before_seconds": float(payload.get("trim_before_seconds", 10.0)),
            "after_seconds": float(payload.get("trim_after_seconds", 10.0)),
        }
        crop = payload.get("crop", {})
        current["crop"] = {key: int(crop[key]) for key in ("width", "height", "x", "y")}
        current["app_version"] = VERSION
        validate_project(current)
        self.project = current
        atomic_write_json(self.project_path, current)
        self.write_outputs()

    def filter_graph(self, project: dict[str, Any], final: bool) -> str:
        timing = source_times(project)
        ratio = float(project["sync"]["clock_ratio"])
        gain = float(project.get("audio_gain_db", 0.0))
        interlaced = bool(project.get("source_video", {}).get("interlaced", True))
        export = project.get("export", {})
        video_filters = [
            "setpts=PTS-STARTPTS",
            f"trim=start={timing['video_filter_start']:.6f}:end={timing['video_filter_end']:.6f}",
            "setpts=PTS-STARTPTS",
        ]
        if interlaced:
            video_filters.append(f"bwdif=mode={'send_field' if final else 'send_frame'}:parity=auto:deint=all")
        if final:
            crop = project["crop"]
            video_filters.extend(
                [
                    f"crop={int(crop['width'])}:{int(crop['height'])}:{int(crop['x'])}:{int(crop['y'])}",
                    f"scale={int(export.get('width', 1920))}:{int(export.get('height', 1080))}:flags=lanczos",
                ]
            )
        else:
            video_filters.append("scale=854:480:flags=lanczos")
        video_filters.append("format=yuv420p")
        if final and project.get("overlay_enabled", True):
            video_filters.append(f"ass={ASS_FILE_NAME}")
        audio_filters = [
            f"atrim=start={timing['audio_start']:.6f}:end={timing['audio_end']:.6f}",
            "asetpts=PTS-STARTPTS",
            "aresample=48000",
            f"atempo={ratio:.12f}",
            f"volume={gain:.2f}dB",
        ]
        return f"[0:v]{','.join(video_filters)}[v];[1:a]{','.join(audio_filters)}[a]"

    def ffmpeg_command(self, project: dict[str, Any], final: bool, output: Path) -> list[str]:
        export = project.get("export", {})
        command = add_nostdin([
            self.ffmpeg,
            "-hide_banner",
            "-y",
            "-i",
            concat_protocol_url(self.camera_paths),
            "-i",
            str(self.audio_path),
            "-filter_complex",
            self.filter_graph(project, final),
            "-map",
            "[v]",
            "-map",
            "[a]",
        ])
        if final:
            command.extend(
                [
                    "-c:v",
                    "libx264",
                    "-preset",
                    str(export.get("video_preset", "slow")),
                    "-crf",
                    str(export.get("video_crf", 18)),
                    "-profile:v",
                    "high",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    str(export.get("audio_bitrate", "384k")),
                    "-ar",
                    "48000",
                ]
            )
        else:
            command.extend(
                [
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-crf",
                    "28",
                    "-tune",
                    "fastdecode",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "160k",
                    "-ar",
                    "48000",
                ]
            )
        command.extend(
            [
                "-max_muxing_queue_size",
                "4096",
                "-shortest",
                "-movflags",
                "+faststart",
                "-progress",
                "pipe:1",
                "-nostats",
                str(output),
            ]
        )
        return command

    def verify_export(self, project: dict[str, Any], output: Path) -> dict[str, Any]:
        expected = source_times(project)["duration"]
        actual = probe_duration(self.ffprobe, output)
        difference = actual - expected
        tolerance = float(project.get("export", {}).get("duration_tolerance_seconds", 0.5))
        result = {
            "expected_seconds": round(expected, 6),
            "actual_seconds": round(actual, 6),
            "difference_seconds": round(difference, 6),
            "tolerance_seconds": tolerance,
            "status": "ok" if abs(difference) <= tolerance else "warning",
            "checked_at": dt.datetime.now().astimezone().isoformat(),
            "output_file": str(output),
        }
        atomic_write_json(self.report_path, result)
        return result

    def create_archive(self, project: dict[str, Any]) -> Path:
        self.archive_root.mkdir(parents=True, exist_ok=True)
        event_date = str(project.get("event_date") or "sem_data")
        base_name = f"{event_date}_{slugify(str(project.get('event', 'concerto')))}_projeto"
        archive_path = self.archive_root / f"{base_name}.zip"
        if archive_path.exists():
            timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_path = self.archive_root / f"{base_name}_{timestamp}.zip"
        candidates = [
            self.project_path,
            self.chapters_path,
            self.ass_path,
            self.report_path,
            self.log_path,
        ]
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for candidate in candidates:
                if candidate.is_file():
                    archive.write(candidate, arcname=candidate.name)
        return archive_path

    def run_render(self, final: bool) -> None:
        kind = "final" if final else "prévia"
        self.state.update(
            running=True,
            kind=kind,
            progress=0.0,
            message=f"Gerando {kind}...",
            output=None,
            archive=None,
            verification=None,
            error=None,
        )
        try:
            project = self.reload_project()
            self.write_outputs()
            timing = source_times(project)
            output = self.final_dir / project["output_file"] if final else self.preview_path
            temporary = output.with_name(output.stem + ".parcial" + output.suffix)
            command = self.ffmpeg_command(project, final, temporary)
            with self.log_path.open("a", encoding="utf-8") as log_handle:
                log_handle.write(f"\n[Renderização {kind}]\n")
                log_handle.write(subprocess.list2cmdline(command) + "\n")
                process = subprocess.Popen(
                    command,
                    cwd=self.work_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    **hidden_process_kwargs(),
                )
                assert process.stdout is not None
                for line in process.stdout:
                    log_handle.write(line)
                    if line.startswith("out_time="):
                        raw = line.partition("=")[2].strip()
                        try:
                            hours, minutes, seconds = raw.split(":")
                            elapsed = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                            progress = min(99.5, 100.0 * elapsed / timing["duration"])
                            self.state.update(progress=progress, message=f"Gerando {kind}: {progress:.1f}%")
                        except (ValueError, ZeroDivisionError):
                            pass
                return_code = process.wait()
            if return_code != 0:
                raise RuntimeError(f"FFmpeg terminou com código {return_code}.")
            os.replace(temporary, output)

            verification = None
            archive = None
            if final:
                verification = self.verify_export(project, output)
                archive = self.create_archive(project)
            else:
                project["preview"] = {
                    "audio_start_tascam": timing["audio_start"],
                    "audio_end_tascam": timing["audio_end"],
                    "uncropped": True,
                }
                self.project = project
                atomic_write_json(self.project_path, project)
            message = f"{kind.capitalize()} concluída."
            if verification and verification["status"] == "warning":
                message = "Vídeo concluído com alerta de duração; consulte o relatório."
            self.state.update(
                running=False,
                progress=100.0,
                message=message,
                output=str(output),
                archive=str(archive) if archive else None,
                verification=verification,
            )
        except Exception as exc:  # noqa: BLE001 - registro operacional
            self.state.update(running=False, message=f"Falha ao gerar {kind}.", error=str(exc))

    def start_render(self, final: bool) -> None:
        if self.state.snapshot()["running"]:
            raise RuntimeError("Já existe uma renderização em andamento.")
        threading.Thread(target=self.run_render, args=(final,), daemon=True).start()


class RequestHandler(BaseHTTPRequestHandler):
    app: CoralApplication

    def log_message(self, format_string: str, *args: Any) -> None:
        return

    def send_json(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_text(self, text: str, content_type: str = "text/html; charset=utf-8") -> None:
        payload = text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def serve_binary(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        payload = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(payload)

    def serve_file_with_range(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Arquivo ainda não foi gerado.")
            return
        size = path.stat().st_size
        range_header = self.headers.get("Range")
        start, end = 0, size - 1
        status = HTTPStatus.OK
        if range_header:
            match = re.match(r"bytes=(\d*)-(\d*)", range_header)
            if not match:
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                return
            first, last = match.groups()
            if first:
                start = int(first)
                end = int(last) if last else size - 1
            elif last:
                suffix = int(last)
                start = max(0, size - suffix)
                end = size - 1
            if start >= size or end < start:
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                return
            end = min(end, size - 1)
            status = HTTPStatus.PARTIAL_CONTENT
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self.send_text(self.app.html_path.read_text(encoding="utf-8"))
        elif parsed.path == "/assets/logo.png":
            self.serve_binary(self.app.logo_path, "image/png")
        elif parsed.path == "/api/identity":
            self.send_json(
                {
                    "app": APP_ID,
                    "version": VERSION,
                    "source_folder": str(self.app.source),
                }
            )
        elif parsed.path == "/api/project":
            self.send_json(self.app.public_project())
        elif parsed.path == "/api/status":
            self.send_json(self.app.state.snapshot())
        elif parsed.path == "/media/preview.mp4":
            self.serve_file_with_range(self.app.preview_path, "video/mp4")
        elif parsed.path == "/api/chapters":
            self.send_text(self.app.chapters_path.read_text(encoding="utf-8"), "text/plain; charset=utf-8")
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            if self.path == "/api/save":
                self.app.save_from_browser(payload)
                self.send_json({"ok": True, "project": self.app.public_project()})
            elif self.path == "/api/render-final":
                self.app.start_render(final=True)
                self.send_json({"ok": True}, HTTPStatus.ACCEPTED)
            elif self.path == "/api/render-preview":
                self.app.start_render(final=False)
                self.send_json({"ok": True}, HTTPStatus.ACCEPTED)
            elif self.path == "/api/shutdown":
                if self.app.state.snapshot()["running"]:
                    raise RuntimeError("Aguarde o término da renderização antes de encerrar.")
                self.send_json({"ok": True, "message": "Editor encerrado."})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except (ValueError, KeyError, TypeError, RuntimeError) as exc:
            self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)


def wait_for_render(app: CoralApplication) -> None:
    while app.state.snapshot()["running"]:
        state = app.state.snapshot()
        print(f"\r{state['message']:<70}", end="", flush=True)
        time.sleep(1)
    state = app.state.snapshot()
    print("\r" + " " * 80 + "\r", end="")
    if state.get("error"):
        fail(str(state["error"]))
    print(state["message"])
    if state.get("output"):
        print(f"Saída: {state['output']}")
    if state.get("archive"):
        print(f"Arquivo do projeto: {state['archive']}")


def running_instance(port: int) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/identity", timeout=0.8
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(
        os.path.abspath(str(right))
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=f"Editor de concertos corais v{VERSION}")
    parser.add_argument("--source", required=True, help="Pasta do concerto")
    parser.add_argument("--archive-root", help="Pasta externa para os ZIPs pequenos de projeto")
    parser.add_argument("--prepare-only", action="store_true", help="Gera somente a prévia")
    parser.add_argument("--render-final", action="store_true", help="Renderiza sem abrir a interface")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Porta local fixa")
    args = parser.parse_args()

    source = Path(args.source).expanduser()
    if not source.is_dir():
        fail(f"Pasta não encontrada: {source}")
    source = source.resolve()
    archive_root = Path(args.archive_root).expanduser().resolve() if args.archive_root else None
    script_dir = Path(__file__).resolve().parent

    if not args.prepare_only and not args.render_final:
        existing = running_instance(args.port)
        if existing and existing.get("app") == APP_ID:
            if same_path(existing.get("source_folder", ""), source):
                url = f"http://127.0.0.1:{args.port}/"
                webbrowser.open(url)
                print(f"O editor já estava aberto. Reutilizando: {url}")
                return
            fail(
                "Já existe um Editor de Concertos aberto para outra pasta. "
                "Use o botão Encerrar no editor atual antes de abrir outro concerto."
            )
    app = CoralApplication(source, script_dir, archive_root)

    if args.render_final:
        app.start_render(final=True)
        wait_for_render(app)
        return
    if not app.preview_path.exists():
        print("A prévia ainda não existe. A geração pode levar vários minutos.")
        app.start_render(final=False)
        wait_for_render(app)
    if args.prepare_only:
        print(f"Prévia: {app.preview_path}")
        return

    RequestHandler.app = app
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), RequestHandler)
    except OSError:
        fail(
            f"A porta local {args.port} está ocupada. Encerre a instância anterior "
            "do editor e tente novamente."
        )
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Editor aberto em: {url}")
    print("Mantenha esta janela aberta. Use Ctrl+C para encerrar.")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nEditor encerrado.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
