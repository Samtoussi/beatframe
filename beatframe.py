from pathlib import Path
from renderer import render_video


project_dir = Path(".")

audio_files = list(project_dir.glob("*.wav"))
image_files = (
    list(project_dir.glob("*.jpg"))
    + list(project_dir.glob("*.jpeg"))
    + list(project_dir.glob("*.png"))
)

if len(audio_files) != 1:
    raise ValueError(f"Expected exactly 1 WAV file, found {len(audio_files)}")

if len(image_files) != 1:
    raise ValueError(f"Expected exactly 1 artwork file, found {len(image_files)}")

audio_path = audio_files[0]
image_path = image_files[0]

print(f"Audio:   {audio_path.name}")
print(f"Artwork: {image_path.name}")

output = render_video(
    image_path=str(image_path),
    audio_path=str(audio_path),
    output_dir=".",
)

print(f"Done: {output}")