from pathlib import Path
import json
import subprocess
import tempfile
from typing import Callable, Optional


def get_media_duration(media_path: str) -> float:
    probe_command = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        media_path,
    ]

    result = subprocess.run(
        probe_command,
        capture_output=True,
        text=True,
        check=True,
    )

    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def get_unique_output_path(
    output_folder: Path,
    stem: str,
) -> Path:
    output_path = output_folder / f"{stem}.mp4"

    if not output_path.exists():
        return output_path

    counter = 2

    while True:
        candidate = (
            output_folder
            / f"{stem}_{counter}.mp4"
        )

        if not candidate.exists():
            return candidate

        counter += 1


def run_ffmpeg_with_progress(
    command: list,
    duration: float,
    progress_callback: Optional[Callable[[float], None]] = None,
):
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    if process.stdout is None:
        raise RuntimeError(
            "Could not read FFmpeg progress output."
        )

    for line in process.stdout:
        line = line.strip()

        if line.startswith("out_time_ms="):
            out_time_us = int(
                line.split("=", 1)[1]
            )

            current_seconds = (
                out_time_us / 1_000_000
            )

            progress = min(
                current_seconds / duration,
                1.0,
            )

            if progress_callback:
                progress_callback(progress)

    return_code = process.wait()

    if return_code != 0:
        raise subprocess.CalledProcessError(
            return_code,
            command,
        )


def render_main_video(
    image_path: str,
    audio_path: str,
    output_path: str,
    fade_duration: float,
    progress_callback: Optional[Callable[[float], None]] = None,
):
    audio_duration = get_media_duration(
        audio_path
    )

    fade_out_start = max(
        0,
        audio_duration - fade_duration,
    )

    video_filter = (
        "scale=1920:1080:"
        "force_original_aspect_ratio=decrease,"
        "pad=1920:1080:"
        "(ow-iw)/2:(oh-ih)/2:black,"
        f"fade=t=in:st=0:d={fade_duration},"
        f"fade=t=out:"
        f"st={fade_out_start}:d={fade_duration}"
    )

    command = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-framerate", "24000/1001",
        "-i", image_path,
        "-i", audio_path,
        "-vf", video_filter,
        "-c:v", "libx264",
        "-preset", "medium",
        "-b:v", "16M",
        "-maxrate", "16M",
        "-bufsize", "32M",
        "-r", "24000/1001",
        "-c:a", "aac",
        "-b:a", "320k",
        "-ar", "48000",
        "-ac", "2",
        "-pix_fmt", "yuv420p",
        "-shortest",
        "-progress", "pipe:1",
        "-nostats",
        output_path,
    ]

    run_ffmpeg_with_progress(
        command=command,
        duration=audio_duration,
        progress_callback=progress_callback,
    )


def concatenate_intro(
    intro_path: str,
    main_video_path: str,
    output_path: str,
    progress_callback: Optional[Callable[[float], None]] = None,
):
    intro_duration = get_media_duration(
        intro_path
    )

    main_duration = get_media_duration(
        main_video_path
    )

    total_duration = (
        intro_duration + main_duration
    )

    filter_complex = (
        "[0:v]"
        "scale=1920:1080:"
        "force_original_aspect_ratio=decrease,"
        "pad=1920:1080:"
        "(ow-iw)/2:(oh-ih)/2:black,"
        "fps=24000/1001,"
        "format=yuv420p,"
        "setpts=PTS-STARTPTS"
        "[v0];"

        "[0:a]"
        "aresample=48000,"
        "aformat=sample_fmts=fltp:"
        "channel_layouts=stereo,"
        "asetpts=PTS-STARTPTS"
        "[a0];"

        "[1:v]"
        "fps=24000/1001,"
        "format=yuv420p,"
        "setpts=PTS-STARTPTS"
        "[v1];"

        "[1:a]"
        "aresample=48000,"
        "aformat=sample_fmts=fltp:"
        "channel_layouts=stereo,"
        "asetpts=PTS-STARTPTS"
        "[a1];"

        "[v0][a0][v1][a1]"
        "concat=n=2:v=1:a=1"
        "[v][a]"
    )

    command = [
        "ffmpeg",
        "-y",
        "-i", intro_path,
        "-i", main_video_path,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-preset", "medium",
        "-b:v", "16M",
        "-maxrate", "16M",
        "-bufsize", "32M",
        "-c:a", "aac",
        "-b:a", "320k",
        "-ar", "48000",
        "-ac", "2",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        "-nostats",
        output_path,
    ]

    run_ffmpeg_with_progress(
        command=command,
        duration=total_duration,
        progress_callback=progress_callback,
    )


def render_video(
    image_path: str,
    audio_path: str,
    output_dir: str,
    fade_duration: float = 6.5,
    intro_path: Optional[str] = None,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> Path:
    audio = Path(audio_path)
    output_folder = Path(output_dir)

    output_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = get_unique_output_path(
        output_folder=output_folder,
        stem=audio.stem,
    )

    audio_duration = get_media_duration(
        audio_path
    )

    if not intro_path:
        render_main_video(
            image_path=image_path,
            audio_path=audio_path,
            output_path=str(output_path),
            fade_duration=fade_duration,
            progress_callback=progress_callback,
        )

        if progress_callback:
            progress_callback(1.0)

        return output_path

    intro = Path(intro_path)

    if not intro.exists():
        raise FileNotFoundError(
            f"Intro file not found: {intro}"
        )

    intro_duration = get_media_duration(
        str(intro)
    )

    main_work = audio_duration

    concat_work = (
        audio_duration + intro_duration
    )

    total_work = (
        main_work + concat_work
    )

    main_weight = (
        main_work / total_work
    )

    concat_weight = (
        concat_work / total_work
    )

    def report_main_progress(
        progress: float,
    ):
        if progress_callback:
            progress_callback(
                progress * main_weight
            )

    def report_concat_progress(
        progress: float,
    ):
        if progress_callback:
            progress_callback(
                main_weight
                + progress * concat_weight
            )

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_main = (
            Path(temp_dir)
            / "main_video.mp4"
        )

        render_main_video(
            image_path=image_path,
            audio_path=audio_path,
            output_path=str(temp_main),
            fade_duration=fade_duration,
            progress_callback=report_main_progress,
        )

        concatenate_intro(
            intro_path=str(intro),
            main_video_path=str(temp_main),
            output_path=str(output_path),
            progress_callback=report_concat_progress,
        )

    if progress_callback:
        progress_callback(1.0)

    return output_path