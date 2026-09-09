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


def build_video_filter(
    fade_duration: float,
    audio_duration: float,
) -> str:
    fade_out_start = max(
        0,
        audio_duration - fade_duration,
    )

    return (
        f"fade=t=in:st=0:d={fade_duration},"
        f"fade=t=out:"
        f"st={fade_out_start}:d={fade_duration}"
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
    """
    Final render when no intro is used.
    The source audio is AAC-encoded exactly once.
    """
    video_filter = build_video_filter(
        fade_duration=fade_duration,
        audio_duration=audio_duration,
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
        "-aac_pns", "0",
        "-ar", "48000",
        "-ac", "2",
        "-pix_fmt", "yuv420p",
        "-t", str(audio_duration),
        "-shortest",
        "-movflags", "+faststart",
        "-progress", "pipe:1",
        "-nostats",
        output_path,
    ]

    run_ffmpeg_with_progress(
        command=command,
        duration=audio_duration,
        progress_callback=progress_callback,
    )


def preprocess_artwork_1080p(
    image_path: str,
    output_path: str,
):
    """
    Pre-scale and pad static artwork once to 1920x1080.

    This avoids repeating the same scale/pad work for every video frame.
    """
    command = [
        "ffmpeg",
        "-y",
        "-i", image_path,
        "-vf",
        (
            "scale=1920:1080:"
            "force_original_aspect_ratio=decrease,"
            "pad=1920:1080:"
            "(ow-iw)/2:(oh-ih)/2:black"
        ),
        "-frames:v", "1",
        output_path,
    ]

    completed = subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if completed.returncode != 0:
        raise RenderError(
            "Artwork couldn't be preprocessed."
        )


def concatenate_intro(
    intro_path: str,
    image_path: str,
    audio_path: str,
    audio_duration: float,
    output_path: str,
    fade_duration: float,
    progress_callback: Optional[
        Callable[[float], None]
    ] = None,
):
    """
    Render intro + normalized artwork + original beat audio in one pass.

    The beat audio is AAC-encoded exactly once.
    """
    intro_duration = get_media_duration(
        intro_path,
        media_type="intro",
    )

    total_duration = intro_duration + audio_duration
    fade_out_start = max(0, audio_duration - fade_duration)

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
        f"fade=t=in:st=0:d={fade_duration},"
        f"fade=t=out:st={fade_out_start}:d={fade_duration},"
        "fps=24000/1001,"
        "format=yuv420p,"
        "setpts=PTS-STARTPTS"
        "[v1];"

        "[2:a]"
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
        "-loop", "1",
        "-framerate", "24000/1001",
        "-t", str(audio_duration),
        "-i", image_path,
        "-i", audio_path,
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
        "-aac_pns", "0",
        "-ar", "48000",
        "-ac", "2",
        "-pix_fmt", "yuv420p",
        "-t", str(total_duration),
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

    with tempfile.TemporaryDirectory() as temp_dir:
        normalized_artwork = (
            Path(temp_dir) / "artwork_1080p.png"
        )

        preprocess_artwork_1080p(
            image_path=image_path,
            output_path=str(normalized_artwork),
        )

        if not intro_path:
            render_main_video(
                image_path=str(normalized_artwork),
                audio_path=audio_path,
                output_path=str(output_path),
                fade_duration=fade_duration,
                audio_duration=audio_duration,
                progress_callback=progress_callback,
            )
        else:
            intro = Path(intro_path)

            if not intro.exists():
                raise FileNotFoundError(
                    f"Intro file not found: {intro}"
                )

            concatenate_intro(
                intro_path=str(intro),
                image_path=str(normalized_artwork),
                audio_path=audio_path,
                audio_duration=audio_duration,
                output_path=str(output_path),
                fade_duration=fade_duration,
                progress_callback=progress_callback,
            )

    if progress_callback:
        progress_callback(1.0)

    return output_path
