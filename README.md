# 🎵 Anime MP3 Formatter

Download anime openings, endings and OSTs from YouTube as properly tagged MP3s,
ready to drop into Spotify's local files.

Give it a search term or a playlist URL and it downloads the audio, works out the
anime / type / number / song / artist with an LLM, and writes the tags, cover art
and a consistent filename:

```
Frieren ED 2 - Anytime Anywhere.mp3
```

I built this to stop fighting with messy filenames and missing tags every time I
added anime music to my Spotify library.

## Built with

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img alt="Flask" src="https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white">
  <img alt="React" src="https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB">
</p>

Flask API, React frontend. `yt-dlp` handles the download, `ffmpeg` the encoding
and loudness, `mutagen` the tags. The metadata comes from an OpenAI-compatible
LLM, backed by AniList and the iTunes Search API for names and cover art.

## How it works

Search YouTube for one track or paste a playlist URL. From there it's the same
either way:

1. Downloads the audio and lets you preview it.
2. The LLM fills in the metadata (anime, type, number, song, artist) from the
   video title and description, searching AniList and the iTunes catalog when it
   needs to.
3. You review and correct the metadata if needed.
4. On download it grabs square cover art, runs `ffmpeg loudnorm`, writes ID3v2.3
   tags (what Spotify's local files expect) and saves as `Anime TYPE N - Song.mp3`.

## Setup

You'll need Python 3.10+, Node 20+, and `ffmpeg` on your PATH.

**Windows:** double-click `start.bat`. First run sets up both sides and opens the
app; after that it just launches.

**Everything else, by hand:**

```bash
# backend
cd backend
python -m venv venv
source venv/bin/activate          # venv\Scripts\activate on Windows
pip install -r requirements.txt
python app.py                     # :5000

# frontend, in a second terminal
cd frontend
npm install
npm run dev                       # :5173
```

Then open <http://localhost:5173>.

The config is in `backend/config.json`.

### LLM config [Optional]

Automatic tagging needs an LLM. Copy `backend/.env.example` to `backend/.env`
and fill in one provider:

```ini
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen2.5:7b
```

I run `qwen2.5:7b` on a local Ollama. Any OpenAI-compatible endpoint
(OpenRouter, DeepSeek, and friends) works by swapping those three values.
Running without a key is fine too, you just fill the tags in yourself.
