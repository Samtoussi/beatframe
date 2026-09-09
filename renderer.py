from pathlib import Path
import json
import subprocess
import sys
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


def get_tool_path(tool_name: str) -> str:
    """
    Resolve FFmpeg tools in both development and packaged builds.

    Priority:
    1. Bundled BeatFrame bin directory.
    2. System PATH as a development fallback.
    """
    resource_dir = Path(
        getattr(
            sys,
            "_MEIPASS",
            Path(__file__).resolve().parent,
        )
    )

    executable_name = (
        f"{tool_name}.exe"
        if sys.platform == "win32"
        else tool_name
    )

    bundled_tool = (
        resource_dir
        / "bin"
        / executable_name
    )

    if bundled_tool.exists():
        return str(bundled_tool)

    return tool_name


FFMPEG = get_tool_path("ffmpeg")
FFPROBE = get_tool_path("ffprobe")


WINDOWS_SUBPROCESS_FLAGS = (
    subprocess.CREATE_NO_WINDOW
    if sys.platform == "win32"
    else 0
)


def get_media_duration(
    media_path: str,
    media_type: str = "media",
) -> float:
    probe_command = [
        FFPROBE,
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
            creationflags=WINDOWS_SUBPROCESS_FLAGS,
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
        FFPROBE,
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
            creationflags=WINDOWS_SUBPROCESS_FLAGS,
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
        creationflags=WINDOWS_SUBPROCESS_FLAGS,
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


def encode_beat_audio(
    audio_path: str,
    output_path: str,
):
    """
    Encode the source beat independently to the production AAC stream.

    Keeping this encode separate from the intro preserves the same AAC
    encoding path as the approved standalone audio test.
    """
    command = [
        FFMPEG,
        "-y",
        "-i", audio_path,
        "-vn",
        "-c:a", "aac",
        "-b:a", "384k",
        "-aac_pns", "0",
        "-ar", "48000",
        "-ac", "2",
        output_path,
    ]

    completed = subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=WINDOWS_SUBPROCESS_FLAGS,
    )

    if completed.returncode != 0:
        raise RenderError(
            "Beat audio couldn't be encoded."
        )


def render_main_video(
    image_path: str,
    encoded_audio_path: str,
    output_path: str,
    fade_duration: float,
    audio_duration: float,
    progress_callback: Optional[
        Callable[[float], None]
    ] = None,
):
    """
    Final render when no intro is used.

    The already-encoded production AAC stream is muxed without re-encoding.
    """
    video_filter = build_video_filter(
        fade_duration=fade_duration,
        audio_duration=audio_duration,
    )

    command = [
        FFMPEG,
        "-y",
        "-loop", "1",
        "-framerate", "24000/1001",
        "-i", image_path,
        "-i", encoded_audio_path,
        "-vf", video_filter,
        "-c:v", "libx264",
        "-preset", "medium",
        "-b:v", "16M",
        "-maxrate", "16M",
        "-bufsize", "32M",
        "-r", "24000/1001",
        "-c:a", "copy",
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
        FFMPEG,
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
        creationflags=WINDOWS_SUBPROCESS_FLAGS,
    )

    if completed.returncode != 0:
        raise RenderError(
            "Artwork couldn't be preprocessed."
        )


def extract_intro_audio(
    intro_path: str,
    output_path: str,
):
    """
    Copy the intro's existing AAC audio stream without re-encoding it.
    """
    command = [
        FFMPEG,
        "-y",
        "-i", intro_path,
        "-vn",
        "-c:a", "copy",
        output_path,
    ]

    completed = subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=WINDOWS_SUBPROCESS_FLAGS,
    )

    if completed.returncode != 0:
        raise RenderError(
            "Intro audio couldn't be extracted."
        )


def concatenate_audio_streams(
    intro_audio_path: str,
    beat_audio_path: str,
    output_path: str,
    concat_list_path: str,
):
    """
    Concatenate intro AAC + independently encoded beat AAC using stream copy.
    """
    intro = Path(intro_audio_path).resolve().as_posix()
    beat = Path(beat_audio_path).resolve().as_posix()

    concat_contents = (
        f"file '{intro}'\n"
        f"file '{beat}'\n"
    )

    Path(concat_list_path).write_text(
        concat_contents,
        encoding="utf-8",
    )

    command = [
        FFMPEG,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list_path,
        "-c", "copy",
        output_path,
    ]

    completed = subprocess.run(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=WINDOWS_SUBPROCESS_FLAGS,
    )

    if completed.returncode != 0:
        raise RenderError(
            "Intro and beat audio couldn't be concatenated."
        )


def concatenate_intro(
    intro_path: str,
    image_path: str,
    full_audio_path: str,
    audio_duration: float,
    output_path: str,
    fade_duration: float,
    progress_callback: Optional[
        Callable[[float], None]
    ] = None,
):
    """
    Render intro + normalized artwork video in one pass, then mux the
    prebuilt intro + beat AAC track without any further audio encoding.
    """
    intro_duration = get_media_duration(
        intro_path,
        media_type="intro",
    )

    total_duration = intro_duration + audio_duration
    fade_out_start = max(
        0,
        audio_duration - fade_duration,
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

        "[1:v]"
        f"fade=t=in:st=0:d={fade_duration},"
        f"fade=t=out:st={fade_out_start}:d={fade_duration},"
        "fps=24000/1001,"
        "format=yuv420p,"
        "setpts=PTS-STARTPTS"
        "[v1];"

        "[v0][v1]"
        "concat=n=2:v=1:a=0"
        "[v]"
    )

    command = [
        FFMPEG,
        "-y",
        "-i", intro_path,
        "-loop", "1",
        "-framerate", "24000/1001",
        "-t", str(audio_duration),
        "-i", image_path,
        "-i", full_audio_path,
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "2:a:0",
        "-c:v", "libx264",
        "-preset", "medium",
        "-b:v", "16M",
        "-maxrate", "16M",
        "-bufsize", "32M",
        "-c:a", "copy",
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
        encoded_beat_audio = (
            Path(temp_dir) / "beat_audio.m4a"
        )

        preprocess_artwork_1080p(
            image_path=image_path,
            output_path=str(normalized_artwork),
        )

        encode_beat_audio(
            audio_path=audio_path,
            output_path=str(encoded_beat_audio),
        )

        if not intro_path:
            render_main_video(
                image_path=str(normalized_artwork),
                encoded_audio_path=str(encoded_beat_audio),
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

            intro_audio = (
                Path(temp_dir) / "intro_audio.m4a"
            )
            full_audio = (
                Path(temp_dir) / "full_audio.m4a"
            )
            concat_list = (
                Path(temp_dir) / "audio_concat.txt"
            )

            extract_intro_audio(
                intro_path=str(intro),
                output_path=str(intro_audio),
            )

            concatenate_audio_streams(
                intro_audio_path=str(intro_audio),
                beat_audio_path=str(encoded_beat_audio),
                output_path=str(full_audio),
                concat_list_path=str(concat_list),
            )

            concatenate_intro(
                intro_path=str(intro),
                image_path=str(normalized_artwork),
                full_audio_path=str(full_audio),
                audio_duration=audio_duration,
                output_path=str(output_path),
                fade_duration=fade_duration,
                progress_callback=progress_callback,
            )

    if progress_callback:
        progress_callback(1.0)

    return output_path
