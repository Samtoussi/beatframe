from pathlib import Path
import json
import subprocess
import tempfile
from typing import Callable, Optional


class MediaReadError(Exception):
    def __init__(
        self,
        media_type: str,
        media_path: str,
    ):
        self.media_type = media_type
        self.media_path = media_path

        super().__init__(
            f"Could not read {media_type}: {media_path}"
        )


class RenderError(Exception):
    pass


def get_media_duration(
    media_path: str,
    media_type: str = "media",
) -> float:
    probe_command = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        media_path,
    ]

    try:
        result = subprocess.run(
            probe_command,
            capture_output=True,
            text=True,
            check=True,
        )

        data = json.loads(result.stdout)
        duration = float(
            data["format"]["duration"]
        )

        if duration <= 0:
            raise ValueError(
                "Media duration must be positive."
            )

        return duration

    except (
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ):
        raise MediaReadError(
            media_type=media_type,
            media_path=media_path,
        )


def validate_image(
    image_path: str,
):
    probe_command = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=codec_type,width,height",
        "-of", "json",
        image_path,
    ]

    try:
        result = subprocess.run(
            probe_command,
            capture_output=True,
            text=True,
            check=True,
        )

        data = json.loads(result.stdout)
        streams = data.get("streams", [])

        if not streams:
            raise ValueError(
                "No image stream found."
            )

        stream = streams[0]

        if (
            stream.get("codec_type") != "video"
            or not stream.get("width")
            or not stream.get("height")
        ):
            raise ValueError(
                "Invalid image stream."
            )

    except (
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ):
        raise MediaReadError(
            media_type="image",
            media_path=image_path,
        )


def get_unique_output_path(
    output_folder: Path,
    stem: str,
) -> Path:
    output_path = (
        output_folder / f"{stem}.mp4"
    )

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
    progress_callback: Optional[
        Callable[[float], None]
    ] = None,
):
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    if process.stdout is None:
        raise RenderError(
            "Could not read FFmpeg progress."
        )

    for line in process.stdout:
        line = line.strip()

        if line.startswith("out_time_ms="):
            try:
                out_time_us = int(
                    line.split("=", 1)[1]
                )
            except ValueError:
                continue

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
        raise RenderError(
            "FFmpeg could not complete the render."
        )


def render_main_video(
    image_path: str,
    audio_path: str,
    output_path: str,
    fade_duration: float,
    audio_duration: float,
    progress_callback: Optional[
        Callable[[float], None]
    ] = None,
):
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
        "-t", str(audio_duration),
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
    progress_callback: Optional[
        Callable[[float], None]
    ] = None,
):
    intro_duration = get_media_duration(
        intro_path,
        media_type="intro",
    )

    main_duration = get_media_duration(
        main_video_path,
        media_type="video",
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
    progress_callback: Optional[
        Callable[[float], None]
    ] = None,
) -> Path:
    audio = Path(audio_path)
    image = Path(image_path)
    output_folder = Path(output_dir)

    if not audio.exists():
        raise FileNotFoundError(
            f"Audio file not found: {audio}"
        )

    if not image.exists():
        raise FileNotFoundError(
            f"Image file not found: {image}"
        )

    audio_duration = get_media_duration(
        audio_path,
        media_type="audio",
    )

    validate_image(image_path)

    output_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = get_unique_output_path(
        output_folder=output_folder,
        stem=audio.stem,
    )

    if not intro_path:
        render_main_video(
            image_path=image_path,
            audio_path=audio_path,
            output_path=str(output_path),
            fade_duration=fade_duration,
            audio_duration=audio_duration,
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
        str(intro),
        media_type="intro",
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
            audio_duration=audio_duration,
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