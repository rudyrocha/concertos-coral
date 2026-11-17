#!/usr/bin/env python3
"""Editor local assistido para gravações de concertos corais.

Usa somente a biblioteca padrão do Python e FFmpeg/FFprobe. Os arquivos de
origem nunca são alterados. A interface é servida apenas em 127.0.0.1.
"""

from __future__ import annotations

import argparse
import array
import ctypes
import datetime as dt
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
import zipfile
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable


VERSION = "2.3.4"
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

    requested_audio_start = first - before * ratio
    requested_audio_end = last_end + after * ratio
    requested_camera_start = (requested_audio_start - offset) / ratio
    requested_camera_end = (requested_audio_end - offset) / ratio

    # Usa somente a interseção realmente existente entre câmera e Tascam.
    # Isso é especialmente importante quando o deslocamento é alterado: um
    # início negativo enviado ao filtro trim pode gerar uma prévia vazia.
    camera_floor = max(0.0, -offset / ratio)
    camera_ceiling = float("inf")
    camera_duration = project.get("camera_duration_seconds")
    audio_duration = project.get("audio_duration_seconds")
    if camera_duration is not None:
        camera_ceiling = min(camera_ceiling, float(camera_duration))
    if audio_duration is not None:
        camera_ceiling = min(camera_ceiling, (float(audio_duration) - offset) / ratio)
    camera_start = max(requested_camera_start, camera_floor)
    camera_end = min(requested_camera_end, camera_ceiling)
    if not math.isfinite(camera_end):
        camera_end = requested_camera_end
    if camera_end <= camera_start:
        raise ValueError(
            "O deslocamento informado não deixa um trecho comum entre vídeo e áudio. "
            "Revise o sinal e o valor do sincronismo."
        )
    audio_start = offset + ratio * camera_start
    audio_end = offset + ratio * camera_end
    markers_outside_overlap = first < audio_start - 0.001 or last_end > audio_end + 0.001
    clipped_start = camera_start > requested_camera_start + 0.001
    clipped_end = camera_end < requested_camera_end - 0.001
    return {
        "camera_start": camera_start,
        "camera_end": camera_end,
        "video_filter_start": camera_start - video_pts_offset,
        "video_filter_end": camera_end - video_pts_offset,
        "audio_start": audio_start,
        "audio_end": audio_end,
        "duration": camera_end - camera_start,
        "effective_before": max(0.0, (first - audio_start) / ratio),
        "effective_after": max(0.0, (audio_end - last_end) / ratio),
        "trim_clipped": clipped_start or clipped_end,
        "trim_clipped_start": clipped_start,
        "trim_clipped_end": clipped_end,
        "markers_outside_overlap": markers_outside_overlap,
    }


def final_time(project: dict[str, Any], absolute_tascam: float) -> float:
    ratio = float(project["sync"]["clock_ratio"])
    return (float(absolute_tascam) - source_times(project)["audio_start"]) / ratio


def migrate_project(project: dict[str, Any]) -> dict[str, Any]:
    """Converte projetos da primeira versão sem perder dados do concerto."""
    migrated = json.loads(json.dumps(project))
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
    migrated.setdefault(
        "audio_processing",
        {
            "mode": "balanced",
            "target_lufs": -16.0,
            "loudness_range": 9.0,
            "true_peak_db": -1.5,
        },
    )
    migrated.setdefault("sync", {"offset_seconds": 0.0, "clock_ratio": 1.0, "video_pts_offset": 0.0})
    migrated.setdefault("crop", {"width": 1920, "height": 1080, "x": 0, "y": 0})
    for position, track in enumerate(migrated.get("tracks", []), start=1):
        track["id"] = str(track.get("id") or uuid.uuid4())
        track.setdefault("kind", "music")
        track.setdefault("enabled", True)
        track.setdefault("title", f"Música {position}")
        track.setdefault("credits", "")
        track.setdefault("confirmed", True)
    migrated.setdefault("last_end_confirmed", True)
    migrated.setdefault("setup_complete", True)
    migrated.setdefault("preview_needs_regeneration", False)
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
    if not math.isfinite(before) or not math.isfinite(after) or before < 0 or after < 0:
        raise ValueError("As margens antes e depois das músicas devem ser valores positivos.")
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
    audio_mode = str(project.get("audio_processing", {}).get("mode", "balanced"))
    if audio_mode not in {"natural", "balanced"}:
        raise ValueError("Modo de tratamento de áudio inválido.")

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


def validate_media_bounds(project: dict[str, Any]) -> None:
    """Impede que a interface grave marcadores fora das fontes reconhecidas."""
    audio_duration = project.get("audio_duration_seconds")
    if audio_duration is None:
        return
    maximum = float(audio_duration) + 0.5
    invalid = [
        track.get("title", "Música")
        for track in enabled_tracks(project)
        if float(track["start_tascam"]) < 0 or float(track["start_tascam"]) > maximum
    ]
    if invalid or float(project.get("last_end_tascam", 0.0)) > maximum:
        raise ValueError(
            "Há marcações fora da duração do Tascam. Use “Reparar marcações e prévia” "
            "antes de salvar novos pontos."
        )


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


def _clean_markdown(value: str) -> str:
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    value = re.sub(r"[*_`]+", "", value)
    return value.strip().strip("|").strip()


def _split_repertoire_entry(value: str) -> tuple[str, str]:
    value = _clean_markdown(value)
    for separator in (" | ", " — ", " – ", " :: "):
        if separator in value:
            title, credits = value.split(separator, 1)
            return title.strip(), credits.strip()
    return value, ""


def parse_repertoire_text(text: str) -> list[dict[str, str]]:
    """Extrai uma lista ordenada simples de um Markdown ou TXT."""
    list_entries: list[str] = []
    table_entries: list[str] = []
    heading_entries: list[str] = []
    general = re.compile(
        r"^(repert[oó]rio|programa|m[uú]sicas?|ordem|concerto|coral|observa[cç][oõ]es?)\b",
        re.IGNORECASE,
    )
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line or line.startswith("<!--") or line.startswith("```"):
            continue
        match = re.match(r"^(?:[-*+]\s+|\d+[.)]\s+)(.+)$", line)
        if match:
            list_entries.append(match.group(1).strip())
            continue
        if line.startswith("|") and line.count("|") >= 2:
            cells = [_clean_markdown(cell) for cell in line.strip("|").split("|")]
            if cells and not all(re.fullmatch(r":?-{2,}:?", cell or "-") for cell in cells):
                first = cells[0].strip()
                if first and not re.search(r"^(ordem|n[ºo]?|t[ií]tulo|m[uú]sica)$", first, re.I):
                    table_entries.append(" | ".join(cell for cell in cells if cell))
            continue
        heading = re.match(r"^#{2,6}\s+(.+)$", line)
        if heading and not general.match(_clean_markdown(heading.group(1))):
            heading_entries.append(heading.group(1).strip())

    entries = list_entries or table_entries or heading_entries
    if not entries:
        for raw_line in text.replace("\r\n", "\n").split("\n"):
            line = _clean_markdown(raw_line.lstrip("# ").strip())
            if not line or general.match(line) or line.startswith("---"):
                continue
            entries.append(line)

    tracks: list[dict[str, str]] = []
    for entry in entries:
        title, credits = _split_repertoire_entry(entry)
        if title and not re.fullmatch(r"[-:| ]+", title):
            tracks.append({"title": title, "credits": credits})
    return tracks


def discover_repertoire(source: Path) -> tuple[Path | None, list[dict[str, str]]]:
    candidates = [
        path
        for pattern in ("*.md", "*.MD", "*.txt", "*.TXT")
        for path in source.glob(pattern)
        if path.is_file() and not path.name.lower().startswith(("readme", "observacoes", "observações"))
    ]
    keywords = ("repert", "musica", "música", "programa", "ordem", "lista")
    candidates.sort(
        key=lambda path: (
            -sum(keyword in path.name.lower() for keyword in keywords),
            path.name.lower(),
        )
    )
    for path in candidates:
        try:
            tracks = parse_repertoire_text(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError):
            continue
        if tracks:
            return path, tracks
    return None, []


def is_placeholder_project(project: dict[str, Any]) -> bool:
    if project.get("bootstrap_completed"):
        return False
    tracks = project.get("tracks", [])
    if project.get("setup_complete") is False:
        return True
    return (
        str(project.get("event", "")).strip().lower() == "novo concerto"
        and len(tracks) == 1
        and str(tracks[0].get("title", "")).strip().lower() == "primeira música"
        and abs(float(tracks[0].get("start_tascam", 0)) - 60.0) < 0.001
        and abs(float(project.get("last_end_tascam", 0)) - 120.0) < 0.001
    )


def probe_video_info(ffprobe: str, path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate,field_order",
            "-of",
            "json",
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
        raise RuntimeError(f"Não foi possível analisar o vídeo {path.name}.")
    streams = json.loads(completed.stdout or "{}").get("streams", [])
    if not streams:
        raise RuntimeError(f"Nenhuma faixa de vídeo encontrada em {path.name}.")
    stream = streams[0]
    field_order = str(stream.get("field_order", "unknown")).lower()
    return {
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "frame_rate": str(stream.get("avg_frame_rate") or "30000/1001"),
        "interlaced": field_order not in ("progressive", "unknown", ""),
        "field_order": field_order,
    }


def _audio_envelope(ffmpeg: str, input_path: str, sample_rate: int = 200) -> list[float]:
    command = add_nostdin(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            input_path,
            "-map",
            "0:a:0",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-f",
            "s16le",
            "pipe:1",
        ]
    )
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        **hidden_process_kwargs(),
    )
    if completed.returncode != 0 or not completed.stdout:
        detail = completed.stderr.decode("utf-8", errors="replace")[-1200:]
        raise RuntimeError(f"Falha ao extrair áudio para sincronização. {detail}")
    samples = array.array("h")
    samples.frombytes(completed.stdout)
    if sys.byteorder != "little":
        samples.byteswap()
    window = max(1, sample_rate // 20)
    envelope: list[float] = []
    for index in range(0, len(samples) - window + 1, window):
        block = samples[index : index + window]
        rms = math.sqrt(sum(float(value) * float(value) for value in block) / len(block))
        envelope.append(math.log1p(rms))
    return envelope


def _normalized(values: list[float]) -> list[float]:
    if len(values) < 3:
        return values
    changes = [values[index] - values[index - 1] for index in range(1, len(values))]
    mean = sum(changes) / len(changes)
    variance = sum((value - mean) ** 2 for value in changes) / len(changes)
    scale = math.sqrt(variance) or 1.0
    return [(value - mean) / scale for value in changes]


def _best_lag(
    camera: list[float], tascam: list[float], minimum: int, maximum: int, min_overlap: int
) -> tuple[int, float]:
    best_lag = 0
    best_score = -2.0
    for lag in range(minimum, maximum + 1):
        camera_start = max(0, -lag)
        tascam_start = max(0, lag)
        overlap = min(len(camera) - camera_start, len(tascam) - tascam_start)
        if overlap < min_overlap:
            continue
        dot = 0.0
        camera_power = 0.0
        tascam_power = 0.0
        for offset in range(overlap):
            left = camera[camera_start + offset]
            right = tascam[tascam_start + offset]
            dot += left * right
            camera_power += left * left
            tascam_power += right * right
        denominator = math.sqrt(camera_power * tascam_power)
        score = dot / denominator if denominator else -2.0
        if score > best_score:
            best_lag, best_score = lag, score
    return best_lag, best_score


def estimate_sync_offset(ffmpeg: str, camera_paths: list[Path], audio_path: Path) -> tuple[float, float]:
    """Estima tascam_time = camera_time + offset por envelopes de energia."""
    camera = _normalized(_audio_envelope(ffmpeg, concat_protocol_url(camera_paths)))
    tascam = _normalized(_audio_envelope(ffmpeg, str(audio_path)))
    if min(len(camera), len(tascam)) < 400:
        raise RuntimeError("Gravação curta demais para sincronização automática.")

    coarse_camera = camera[::5]
    coarse_tascam = tascam[::5]
    coarse_rate = 4
    max_lag = min(120 * coarse_rate, max(len(coarse_camera), len(coarse_tascam)) // 2)
    min_overlap = min(len(coarse_camera), len(coarse_tascam), 60 * coarse_rate)
    coarse_lag, _ = _best_lag(
        coarse_camera, coarse_tascam, -max_lag, max_lag, max(80, min_overlap)
    )
    center = coarse_lag * 5
    refined_lag, score = _best_lag(
        camera,
        tascam,
        center - 25,
        center + 25,
        max(400, min(len(camera), len(tascam)) // 3),
    )
    return round(refined_lag / 20.0, 3), round(score, 4)


def bootstrap_project(
    project: dict[str, Any],
    source: Path,
    camera_paths: list[Path],
    audio_path: Path,
    ffmpeg: str,
    ffprobe: str,
) -> dict[str, Any]:
    """Substitui os marcadores fictícios por uma configuração inicial real."""
    camera_duration = sum(probe_duration(ffprobe, path) for path in camera_paths)
    audio_duration = probe_duration(ffprobe, audio_path)
    video_info = probe_video_info(ffprobe, camera_paths[0])
    repertoire_path, repertoire = discover_repertoire(source)
    if not repertoire:
        repertoire = [{"title": "Música 1", "credits": ""}]

    try:
        offset, confidence = estimate_sync_offset(ffmpeg, camera_paths, audio_path)
    except Exception:
        offset, confidence = 0.0, 0.0
    # O procedimento normal inicia o Tascam antes da câmera. Correlações fracas
    # ou negativas não são seguras o bastante para definir o corte inicial.
    if offset < 0 or confidence < 0.12:
        offset, confidence = 0.0, 0.0
    available_camera = min(camera_duration, max(1.0, audio_duration - max(0.0, offset)))
    margin = min(10.0, max(1.0, available_camera / 20.0))
    span = max(1.0, available_camera - 2 * margin)
    track_count = len(repertoire)
    tracks: list[dict[str, Any]] = []
    for index, item in enumerate(repertoire):
        camera_time = margin + span * index / max(1, track_count)
        tracks.append(
            {
                "id": str(uuid.uuid4()),
                "kind": "music",
                "title": item["title"],
                "credits": item.get("credits", ""),
                "start_tascam": round(offset + camera_time, 3),
                "enabled": True,
                "confirmed": False,
            }
        )

    project["event"] = source.name
    project["chapter_opening"] = f"Abertura - {source.name}"
    project["source_video"] = video_info
    project["crop"] = {
        "width": video_info["width"] - video_info["width"] % 2,
        "height": video_info["height"] - video_info["height"] % 2,
        "x": 0,
        "y": 0,
    }
    project["export"]["width"] = project["crop"]["width"]
    project["export"]["height"] = project["crop"]["height"]
    project["sync"] = {
        "offset_seconds": offset,
        "clock_ratio": 1.0,
        "video_pts_offset": 0.0,
        "auto_estimated": True,
        "confidence": confidence,
    }
    project["trim"] = {"before_seconds": margin, "after_seconds": margin}
    project["tracks"] = tracks
    project["last_end_tascam"] = round(offset + available_camera - margin, 3)
    project["last_end_confirmed"] = False
    project["setup_complete"] = False
    project["bootstrap_completed"] = True
    project["preview_needs_regeneration"] = True
    project["camera_duration_seconds"] = round(camera_duration, 3)
    project["audio_duration_seconds"] = round(audio_duration, 3)
    project["repertoire_source"] = repertoire_path.name if repertoire_path else None
    project["audio_gain_db"] = None
    project["audio_processing"] = {
        "mode": "balanced",
        "target_lufs": -16.0,
        "loudness_range": 9.0,
        "true_peak_db": -1.5,
    }
    project["output_file"] = f"{slugify(source.name)}.mp4"
    source_note = (
        f"Repertório importado de {repertoire_path.name}. " if repertoire_path else
        "Nenhum arquivo de repertório foi reconhecido; edite a lista manualmente. "
    )
    confidence_note = (
        f"Sincronismo automático sugerido: {offset:+.3f} s (confiança {confidence:.2f})."
        if confidence > 0
        else "Sincronismo automático inconclusivo; confira câmera e Tascam."
    )
    project["notice"] = source_note + confidence_note + " Confirme todos os marcadores antes da exportação."
    return project


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
        if is_placeholder_project(self.project):
            print("Preparando concerto novo e importando o repertório...")
            self.project = bootstrap_project(
                self.project,
                source,
                self.camera_paths,
                self.audio_path,
                self.ffmpeg,
                self.ffprobe,
            )
        validate_project(self.project)
        if self.project.get("audio_gain_db") is None:
            print("Analisando o nível do áudio do Tascam...")
            try:
                self.project["audio_gain_db"] = detect_peak_gain(
                    self.ffmpeg, self.audio_path, self.project, self.log_path
                )
            except ValueError as exc:
                self.project["audio_gain_db"] = 0.0
                self.project["timing_error"] = str(exc)
        self.refresh_outputs()
        atomic_write_json(self.project_path, self.project)

    def reload_project(self) -> dict[str, Any]:
        self.project = migrate_project(load_json(self.project_path))
        validate_project(self.project)
        return self.project

    def write_outputs(self) -> None:
        write_chapters(self.project, self.chapters_path)
        write_ass(self.project, self.ass_path)

    def refresh_outputs(self) -> bool:
        """Atualiza derivados quando o sincronismo é válido, sem impedir a abertura."""
        try:
            timing = source_times(self.project)
            if timing.get("markers_outside_overlap"):
                raise ValueError(
                    "O sincronismo informado coloca parte da apresentação fora do trecho comum "
                    "entre vídeo e áudio. Revise o deslocamento."
                )
            self.write_outputs()
        except ValueError as exc:
            self.project["timing_error"] = str(exc)
            return False
        self.project.pop("timing_error", None)
        return True

    def repair_timeline(self) -> Path:
        """Arquiva timecodes inválidos e recria uma base provisória dentro das fontes."""
        current = self.reload_project()
        tracks = [dict(track) for track in enabled_tracks(current)]
        if not tracks:
            raise ValueError("Não há músicas habilitadas para reparar.")
        camera_duration = float(current.get("camera_duration_seconds", 0.0))
        audio_duration = float(current.get("audio_duration_seconds", 0.0))
        available = min(camera_duration, audio_duration)
        if available <= 2.0:
            raise ValueError("As durações das fontes não permitem reconstruir a linha do tempo.")

        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = self.work_dir / f"projeto_antes_reparo_{timestamp}.json"
        shutil.copy2(self.project_path, backup)

        margin = min(10.0, max(1.0, available / 20.0))
        span = max(1.0, available - 2 * margin)
        for index, track in enumerate(tracks):
            track["start_tascam"] = round(margin + span * index / max(1, len(tracks)), 3)
            track["enabled"] = True
            track["confirmed"] = False

        current["tracks"] = tracks
        current["sync"]["offset_seconds"] = 0.0
        current["sync"]["clock_ratio"] = 1.0
        current["trim"] = {"before_seconds": margin, "after_seconds": margin}
        current["last_end_tascam"] = round(available - margin, 3)
        current["last_end_confirmed"] = False
        current["setup_complete"] = False
        current["preview"] = {
            "audio_start_tascam": 0.0,
            "audio_end_tascam": available,
            "uncropped": True,
        }
        current["preview_needs_regeneration"] = True
        current["recovery_backup"] = str(backup)
        current["notice"] = (
            "Linha do tempo reparada. Os marcadores foram redistribuídos provisoriamente; "
            "confirme novamente o início de cada música e o fim musical."
        )
        current.pop("timing_error", None)
        self.project = current
        self.refresh_outputs()
        atomic_write_json(self.project_path, current)
        return backup

    @staticmethod
    def preview_fallback_timing(project: dict[str, Any]) -> dict[str, Any]:
        """Descreve a prévia anterior quando o novo sincronismo não é calculável."""
        preview = project.get("preview", {})
        ratio = max(0.000001, float(project.get("sync", {}).get("clock_ratio", 1.0)))
        tracks = enabled_tracks(project)
        first = float(tracks[0]["start_tascam"]) if tracks else 0.0
        last_end = float(project.get("last_end_tascam", first + 1.0))
        audio_start = float(preview.get("audio_start_tascam", max(0.0, first)))
        audio_end = float(preview.get("audio_end_tascam", max(audio_start + 0.001, last_end)))
        if audio_end <= audio_start:
            audio_end = audio_start + 0.001
        duration = (audio_end - audio_start) / ratio
        return {
            "camera_start": 0.0,
            "camera_end": duration,
            "video_filter_start": 0.0,
            "video_filter_end": duration,
            "audio_start": audio_start,
            "audio_end": audio_end,
            "duration": duration,
            "effective_before": max(0.0, (first - audio_start) / ratio),
            "effective_after": max(0.0, (audio_end - last_end) / ratio),
            "trim_clipped": True,
            "trim_clipped_start": True,
            "trim_clipped_end": True,
            "markers_outside_overlap": True,
            "using_previous_preview": True,
        }

    def public_project(self) -> dict[str, Any]:
        project = json.loads(json.dumps(self.project))
        timing_error = project.get("timing_error")
        try:
            timing = source_times(project)
            if timing.get("markers_outside_overlap"):
                timing_error = (
                    "O sincronismo informado coloca parte da apresentação fora do trecho comum "
                    "entre vídeo e áudio. Revise o deslocamento."
                )
        except ValueError as exc:
            timing_error = str(exc)
            timing = self.preview_fallback_timing(project)
        preview = project.setdefault("preview", {})
        preview.setdefault("audio_start_tascam", timing["audio_start"])
        preview.setdefault("audio_end_tascam", timing["audio_end"])
        project["derived"] = {
            **timing,
            "duration_clock": seconds_to_clock(timing["duration"]),
            "final_times": {
                str(track["id"]):
                (float(track["start_tascam"]) - timing["audio_start"])
                / float(project["sync"]["clock_ratio"])
                for track in enabled_tracks(project)
            },
            "last_end_final":
            (float(project["last_end_tascam"]) - timing["audio_start"])
            / float(project["sync"]["clock_ratio"]),
            "chapters_file": str(self.chapters_path),
            "final_folder": str(self.final_dir),
            "archive_folder": str(self.archive_root),
            "app_version": VERSION,
            "pending_markers": sum(
                1 for track in enabled_tracks(project) if not track.get("confirmed", False)
            ) + (0 if project.get("last_end_confirmed", False) else 1),
            "timing_error": timing_error,
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
                    "confirmed": bool(item.get("confirmed", False)),
                }
            )
        old_enabled = enabled_tracks(current)
        previous_timing = (
            float(current["sync"].get("offset_seconds", 0.0)),
            float(current["sync"].get("clock_ratio", 1.0)),
            float(current.get("trim", {}).get("before_seconds", 10.0)),
            float(current.get("trim", {}).get("after_seconds", 10.0)),
            float(current.get("last_end_tascam", 0.0)),
            float(old_enabled[0]["start_tascam"]) if old_enabled else None,
            float(current.get("audio_gain_db", 0.0)),
            str(current.get("audio_processing", {}).get("mode", "balanced")),
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
        current["last_end_confirmed"] = bool(payload.get("last_end_confirmed", False))
        current["overlay_enabled"] = bool(payload.get("overlay_enabled", True))
        current["audio_gain_db"] = float(payload.get("audio_gain_db", 0.0))
        audio_mode = str(payload.get("audio_processing_mode", "balanced"))
        current.setdefault("audio_processing", {})["mode"] = audio_mode
        current["trim"] = {
            "before_seconds": float(payload.get("trim_before_seconds", 10.0)),
            "after_seconds": float(payload.get("trim_after_seconds", 10.0)),
        }
        current["sync"]["offset_seconds"] = float(
            payload.get("sync_offset_seconds", current["sync"].get("offset_seconds", 0.0))
        )
        current["sync"]["clock_ratio"] = float(
            payload.get("clock_ratio", current["sync"].get("clock_ratio", 1.0))
        )
        crop = payload.get("crop", {})
        current["crop"] = {key: int(crop[key]) for key in ("width", "height", "x", "y")}
        current["app_version"] = VERSION
        current["setup_complete"] = bool(current["last_end_confirmed"]) and all(
            track.get("confirmed", False) for track in enabled_tracks(current)
        )
        new_timing = (
            float(current["sync"].get("offset_seconds", 0.0)),
            float(current["sync"].get("clock_ratio", 1.0)),
            float(current["trim"]["before_seconds"]),
            float(current["trim"]["after_seconds"]),
            float(current["last_end_tascam"]),
            float(enabled_tracks(current)[0]["start_tascam"]),
            float(current.get("audio_gain_db", 0.0)),
            str(current.get("audio_processing", {}).get("mode", "balanced")),
        )
        if new_timing != previous_timing:
            current["preview_needs_regeneration"] = True
        validate_project(current)
        validate_media_bounds(current)
        self.project = current
        self.refresh_outputs()
        atomic_write_json(self.project_path, current)

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
            f"atempo={ratio:.12f}",
            f"volume={gain:.2f}dB",
        ]
        audio_processing = project.get("audio_processing", {})
        if audio_processing.get("mode", "balanced") == "balanced":
            target = float(audio_processing.get("target_lufs", -16.0))
            loudness_range = float(audio_processing.get("loudness_range", 9.0))
            true_peak = float(audio_processing.get("true_peak_db", -1.5))
            audio_filters.extend(
                [
                    # Compressão moderada reduz aplausos muito acima do coro.
                    "acompressor=threshold=0.125:ratio=3:attack=20:release=500:"
                    "makeup=1:knee=4:link=maximum:detection=rms",
                    # EBU R128 eleva a percepção das músicas e limita picos.
                    f"loudnorm=I={target:.1f}:LRA={loudness_range:.1f}:TP={true_peak:.1f}",
                ]
            )
        audio_filters.append("aresample=48000")
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
            if final and not project.get("setup_complete", False):
                pending = sum(
                    1 for track in enabled_tracks(project) if not track.get("confirmed", False)
                ) + (0 if project.get("last_end_confirmed", False) else 1)
                raise RuntimeError(
                    f"Confirme os {pending} marcadores pendentes antes da exportação final."
                )
            timing = source_times(project)
            if timing.get("markers_outside_overlap"):
                raise RuntimeError(
                    "O sincronismo informado coloca parte da apresentação fora do trecho comum "
                    "entre vídeo e áudio. Revise o deslocamento; a prévia anterior foi preservada."
                )
            self.write_outputs()
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
            try:
                rendered_duration = probe_duration(self.ffprobe, temporary)
            except RuntimeError as exc:
                temporary.unlink(missing_ok=True)
                raise RuntimeError(
                    f"O FFmpeg não produziu uma {kind} utilizável; a saída anterior foi preservada."
                ) from exc
            minimum_duration = max(0.5, float(timing["duration"]) * 0.90)
            if rendered_duration < minimum_duration:
                temporary.unlink(missing_ok=True)
                raise RuntimeError(
                    f"A {kind} ficou incompleta ({rendered_duration:.1f} s de "
                    f"{timing['duration']:.1f} s); a saída anterior foi preservada."
                )
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
                project["preview_needs_regeneration"] = False
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
            elif self.path == "/api/repair-timeline":
                if self.app.state.snapshot()["running"]:
                    raise RuntimeError("Aguarde o término da renderização antes do reparo.")
                backup = self.app.repair_timeline()
                self.send_json(
                    {
                        "ok": True,
                        "backup": str(backup),
                        "project": self.app.public_project(),
                    }
                )
            elif self.path == "/api/shutdown":
                if self.app.state.snapshot()["running"]:
                    raise RuntimeError("Aguarde o término da renderização antes de encerrar.")
                self.send_json({"ok": True, "message": "Editor encerrado."})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except (ValueError, KeyError, TypeError, RuntimeError) as exc:
            self.send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)


def wait_for_render(app: CoralApplication, fatal: bool = True) -> bool:
    while app.state.snapshot()["running"]:
        state = app.state.snapshot()
        print(f"\r{state['message']:<70}", end="", flush=True)
        time.sleep(1)
    state = app.state.snapshot()
    print("\r" + " " * 80 + "\r", end="")
    if state.get("error"):
        if fatal:
            fail(str(state["error"]))
        print(f"A nova prévia falhou; a anterior foi preservada: {state['error']}")
        return False
    print(state["message"])
    if state.get("output"):
        print(f"Saída: {state['output']}")
    if state.get("archive"):
        print(f"Arquivo do projeto: {state['archive']}")
    return True


def running_instance(port: int) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/identity", timeout=0.8
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def shutdown_outdated_instance(port: int) -> None:
    """Encerra uma instância antiga antes de carregar arquivos da versão nova."""
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/shutdown",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2.0) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8") or "{}")
            detail = payload.get("error")
        except Exception:
            detail = None
        raise RuntimeError(
            detail or "A versão anterior não pôde ser encerrada automaticamente."
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            "A versão anterior não pôde ser encerrada automaticamente."
        ) from exc
    if payload.get("ok") is False:
        raise RuntimeError(payload.get("error") or "Falha ao encerrar a versão anterior.")
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if running_instance(port) is None:
            return
        time.sleep(0.1)
    raise RuntimeError("A versão anterior ainda está em execução.")


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
                if existing.get("version") == VERSION:
                    url = f"http://127.0.0.1:{args.port}/"
                    webbrowser.open(url)
                    print(f"O editor já estava aberto. Reutilizando: {url}")
                    return
                old_version = existing.get("version", "desconhecida")
                print(
                    f"Encerrando a versão anterior ({old_version}) para iniciar a {VERSION}..."
                )
                try:
                    shutdown_outdated_instance(args.port)
                except RuntimeError as exc:
                    fail(
                        "Existe uma versão anterior do editor em execução. "
                        f"{exc} Use o botão Encerrar editor e abra novamente."
                    )
            else:
                fail(
                    "Já existe um Editor de Concertos aberto para outra pasta. "
                    "Use o botão Encerrar no editor atual antes de abrir outro concerto."
                )
    app = CoralApplication(source, script_dir, archive_root)

    if args.render_final:
        app.start_render(final=True)
        wait_for_render(app)
        return
    had_preview = app.preview_path.exists()
    if not had_preview or app.project.get("preview_needs_regeneration", False):
        if had_preview and app.project.get("timing_error") and not args.prepare_only:
            print("A prévia anterior será aberta para permitir o reparo da linha do tempo.")
        else:
            print("A prévia ainda não existe. A geração pode levar vários minutos.")
            app.start_render(final=False)
            wait_for_render(app, fatal=args.prepare_only or not had_preview)
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
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - último recurso para o lançador sem console
        detail = traceback.format_exc()
        try:
            error_log = Path(__file__).resolve().parent / "editor_erro.log"
            error_log.write_text(
                f"{dt.datetime.now().isoformat()}\n{detail}", encoding="utf-8"
            )
        except Exception:
            error_log = None
        message = f"O Editor de Concertos não pôde iniciar.\n\n{exc}"
        if error_log:
            message += f"\n\nDiagnóstico salvo em:\n{error_log}"
        if sys.platform == "win32":
            try:
                ctypes.windll.user32.MessageBoxW(0, message, "Editor de Concertos", 0x10)
            except Exception:
                pass
        else:
            print(detail, file=sys.stderr)
        raise SystemExit(1)
