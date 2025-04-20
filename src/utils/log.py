# src/utils/log.py

import logging
import logging.handlers
import sys
import yaml
from pathlib import Path
from typing import Optional
import datetime

# --- Constants ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
LOG_DIR_NAME = "logs"
LOG_DIR_PATH = PROJECT_ROOT / LOG_DIR_NAME
LOG_FILE_NAME = "app.log"
LOG_FORMAT_FILE = "%(asctime)s - %(levelname)s - %(message)s"
LOG_FORMAT_CONSOLE = "%(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

SUCCESS_LEVEL_NUM = 25
logging.addLevelName(SUCCESS_LEVEL_NUM, "SUCCESS")

# --- Custom Formatter for Console Icons ---
class IconFormatter(logging.Formatter):
    LEVEL_ICONS = {
        logging.DEBUG: "🐞",
        logging.INFO: "ℹ️",
        SUCCESS_LEVEL_NUM: "✅",
        logging.WARNING: "⚠️",
        logging.ERROR: "❌",
        logging.CRITICAL: "🔥",
    }
    converter = datetime.datetime.fromtimestamp

    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        return ct.strftime("[%H:%M:%S]")

    def format(self, record):
        timestamp = self.formatTime(record)
        icon = self.LEVEL_ICONS.get(record.levelno, "➡️")
        message_part = record.getMessage()
        return f"{timestamp} {icon} {message_part}"

# --- Logger Setup ---
app_logger = logging.getLogger('RealEstateTranscriber')
_handlers_configured = False

def setup_logging(config_path: Path = DEFAULT_CONFIG_PATH, level: int = logging.INFO):
    global _handlers_configured
    if _handlers_configured:
        return

    logging_enabled = True
    log_level_from_config = level
    backup_count = 7

    try:
        if config_path.is_file():
            with open(config_path, "r", encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            logging_enabled = config.get("logging_enabled", True)
            lvl = str(config.get("log_level", logging.getLevelName(level))).upper()
            parsed = logging.getLevelName(lvl)
            if isinstance(parsed, int):
                log_level_from_config = parsed
            else:
                print(f"[Log Setup Warning] Invalid log_level '{config.get('log_level')}', using default.", file=sys.stderr)
            bc = config.get("log_backup_count", 7)
            if isinstance(bc, int) and bc >= 0:
                backup_count = bc
            else:
                print(f"[Log Setup Warning] Invalid log_backup_count '{bc}', using default.", file=sys.stderr)
    except Exception as e:
        print(f"[Log Setup Error] Failed to read log settings: {e}", file=sys.stderr)

    app_logger.setLevel(log_level_from_config)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(IconFormatter(fmt=LOG_FORMAT_CONSOLE))
    console_handler.setLevel(log_level_from_config)

    file_handler = None
    if logging_enabled:
        try:
            LOG_DIR_PATH.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.TimedRotatingFileHandler(
                LOG_DIR_PATH / LOG_FILE_NAME,
                when="midnight",
                interval=1,
                backupCount=backup_count,
                encoding='utf-8'
            )
            file_formatter = logging.Formatter(LOG_FORMAT_FILE, datefmt=LOG_DATE_FORMAT)
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(log_level_from_config)
        except Exception as e:
            print(f"[Log Setup Error] Could not create file handler: {e}", file=sys.stderr)

    if logging_enabled:
        app_logger.addHandler(console_handler)
        if file_handler:
            app_logger.addHandler(file_handler)
            target = f"console and file '{LOG_DIR_PATH / LOG_FILE_NAME}' (Backups: {backup_count})"
        else:
            target = "console only (file handler failed)"
        print(f"[Log Setup Info] Logging enabled. Level: {logging.getLevelName(app_logger.level)}. Output to {target}.")
    else:
        app_logger.addHandler(logging.NullHandler())
        print("[Log Setup Info] Logging disabled via configuration.")

    _handlers_configured = True

# --- Public Logging Function ---
def log(message: str,
        level: str = "INFO",
        job_id: Optional[str] = None,
        **kwargs):
    """
    Logs a message. If job_id is provided, prefixes it to the message.
    """
    if job_id:
        message = f"[{job_id}] {message}"

    level_upper = level.upper()
    logger_instance = logging.getLogger('RealEstateTranscriber')

    if level_upper == "DEBUG":
        logger_instance.debug(message)
    elif level_upper == "SUCCESS":
        logger_instance.log(SUCCESS_LEVEL_NUM, message)
    elif level_upper == "WARNING":
        logger_instance.warning(message)
    elif level_upper == "ERROR":
        logger_instance.error(message)
    elif level_upper == "CRITICAL":
        logger_instance.critical(message)
    else:
        prefix = f"({level}) " if level_upper != "INFO" else ""
        logger_instance.info(f"{prefix}{message}")
