import shutil

from yt_dlp import YoutubeDL

FFMPEG_LOCATION = shutil.which("ffmpeg")


def get_audio_stream_url(video_id):
    ydl_opts = {"quiet": True, "format": "bestaudio/best", "noplaylist": True}
    if FFMPEG_LOCATION:
        ydl_opts["ffmpeg_location"] = FFMPEG_LOCATION

    url = f"https://www.youtube.com/watch?v={video_id}"
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    stream_url = info.get("url")
    if not stream_url and info.get("requested_formats"):
        stream_url = info["requested_formats"][0].get("url")
    return stream_url


def download_audio(video_id, work_dir):
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(work_dir / "%(id)s.%(ext)s"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        ],
        "quiet": True,
        "noplaylist": True,
        "noprogress": True,
    }
    if FFMPEG_LOCATION:
        ydl_opts["ffmpeg_location"] = FFMPEG_LOCATION

    url = f"https://www.youtube.com/watch?v={video_id}"
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    mp3_path = work_dir / f"{info['id']}.mp3"
    thumbnail_url = info.get("thumbnail")
    return mp3_path, thumbnail_url


def get_video_description(video_id):
    ydl_opts = {"quiet": True, "skip_download": True}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    return info.get("description") or ""
