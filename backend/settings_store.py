import json
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
DEFAULT_OUTPUT_DIR = str(Path.home() / "Music" / "AnimeMp3")


def load_config():
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if data.get("output_dir"):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {"output_dir": DEFAULT_OUTPUT_DIR}


def save_config(config):
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
