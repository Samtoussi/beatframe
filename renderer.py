from pathlib import Path
import json
import subprocess


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
        str(output_path),
    ]

    subprocess.run(command, check=True)

    return output_path