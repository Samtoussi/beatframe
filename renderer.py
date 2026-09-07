from pathlib import Path
import json
import subprocess
from typing import Callable, Optional


def get_audio_duration(audio_path: str) -> float:
    probe_command = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        audio_path,
    ]

    result = subprocess.run(
        probe_command,
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def render_video(
    image_path: str,
    audio_path: str,
    output_dir: str,
    fade_duration: float = 6.5,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> Path:
    image = Path(image_path)
    audio = Path(audio_path)
    output_folder = Path(output_dir)

    output_folder.mkdir(parents=True, exist_ok=True)

    output_path = output_folder / f"{audio.stem}.mp4"

    audio_duration = get_audio_duration(str(audio))
    fade_out_start = max(0, audio_duration - fade_duration)

    command = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-i", str(image),
        "-i", str(audio),
        "-vf",
        (
            f"fade=t=in:st=0:d={fade_duration},"
            f"fade=t=out:st={fade_out_start}:d={fade_duration}"
        ),
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "320k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        "-progress", "pipe:1",
        "-nostats",
        str(output_path),
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    if process.stdout is None:
        raise RuntimeError("Could not read FFmpeg progress output.")

    for line in process.stdout:
        line = line.strip()

        if line.startswith("out_time_ms="):
            out_time_us = int(line.split("=", 1)[1])
            current_seconds = out_time_us / 1_000_000

            progress = min(current_seconds / audio_duration, 1.0)

            if progress_callback:
                progress_callback(progress)

    return_code = process.wait()

    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, command)

    if progress_callback:
        progress_callback(1.0)

    return output_path