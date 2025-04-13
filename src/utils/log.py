# src/utils/log.py

import logging
import logging.handlers
import sys
import yaml
from pathlib import Path
from typing import Optional
import datetime # Import datetime directly as needed

# --- Constants ---
# Define PROJECT_ROOT directly within this module for robustness during initialization
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent # src/utils/log.py -> src/utils -> src -> project root

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
LOG_DIR_NAME = "logs"
LOG_DIR_PATH = PROJECT_ROOT / LOG_DIR_NAME
LOG_FILE_NAME = "app.log" # Base name, rotation adds date
LOG_FORMAT_FILE = "%(asctime)s - %(levelname)s - %(message)s"
# Console format only includes the message; timestamp/icon are added by the formatter
LOG_FORMAT_CONSOLE = "%(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S" # Used by file handler and formatter

# Define custom SUCCESS log level
SUCCESS_LEVEL_NUM = 25
logging.addLevelName(SUCCESS_LEVEL_NUM, "SUCCESS")

# --- Custom Formatter for Console Icons ---
class IconFormatter(logging.Formatter):
    """Custom formatter to add icons and specific timestamp format for console output."""
    LEVEL_ICONS = {
        logging.DEBUG: "🐞",
        logging.INFO: "ℹ️",
        SUCCESS_LEVEL_NUM: "✅",
        logging.WARNING: "⚠️",
        logging.ERROR: "❌",
        logging.CRITICAL: "🔥",
    }
    # Use datetime for timestamp formatting (required for strftime)
    converter = datetime.datetime.fromtimestamp

    def formatTime(self, record, datefmt=None):
        """Overrides formatTime to produce [HH:MM:SS] format for console."""
        ct = self.converter(record.created)
        # Format specifically for console prefix, ignore datefmt passed by default handler
        s = ct.strftime("[%H:%M:%S]")
        return s

    def format(self, record):
        """Formats the log record with timestamp, icon, and message."""
        # Get the timestamp string using our overridden formatTime
        timestamp = self.formatTime(record)
        # Get the appropriate icon based on the log level
        icon = self.LEVEL_ICONS.get(record.levelno, "➡️") # Default icon if level unknown

        # Format the main message part using the formatter's base style
        # This resolves '%(message)s' etc. from the LOG_FORMAT_CONSOLE string
        # We need a temporary basic formatter to do this resolution correctly
        # Using the base class method ensures correct handling of exception info etc.
        # record.message = record.getMessage() # Ensure message is resolved
        # if self.usesTime(): record.asctime = self.formatTime(record, self.datefmt) # Not needed for this format
        # message_part = self._style._fmt % record.__dict__ # This might be too simple if format includes more fields
        # A safer way is to let the base class format the message part based on the console format string
        formatter = logging.Formatter(self._style._fmt) # Create temporary formatter with just the message format
        # Get the already formatted message string from the record
        message_part = record.getMessage()


        # Combine timestamp, icon, and the formatted message
        return f"{timestamp} {icon} {message_part}"


# --- Logger Setup ---
# Get the specific logger instance for this application
app_logger = logging.getLogger('RealEstateTranscriber')
_handlers_configured = False # Flag to prevent adding handlers multiple times

def setup_logging(config_path: Path = DEFAULT_CONFIG_PATH, level: int = logging.INFO):
    """
    Configures the application logger ('RealEstateTranscriber') based on settings
    from the config file. Sets up console (stdout) and rotating file logging.
    Should be called once at application startup.

    Args:
        config_path: Path to the configuration YAML file.
        level: Default logging level if config file is not found or lacks setting.
    """
    global _handlers_configured
    if _handlers_configured:
        # Avoid reconfiguring if already done
        return

    logging_enabled = True
    log_level_from_config = level # Start with the default level passed
    backup_count = 7 # Default number of log files to keep

    # Load logging settings from config file safely
    try:
        if config_path.is_file():
            with open(config_path, "r", encoding='utf-8') as f:
                config = yaml.safe_load(f) or {} # Handle empty config file

            # Get settings from config, falling back to defaults
            logging_enabled = config.get("logging_enabled", True)
            config_level_name = str(config.get("log_level", logging.getLevelName(level))).upper()
            parsed_level = logging.getLevelName(config_level_name) # Converts name to number

            # Validate parsed level
            if isinstance(parsed_level, int):
                log_level_from_config = parsed_level
            else:
                 # Print to stderr as logger might not be fully setup
                 print(f"[Log Setup Warning] Invalid log_level '{config.get('log_level')}' in config, using default: {logging.getLevelName(level)}.", file=sys.stderr)

            # Get backup count from config, ensure it's a valid integer
            backup_count_config = config.get("log_backup_count", 7)
            if isinstance(backup_count_config, int) and backup_count_config >= 0:
                 backup_count = backup_count_config
            else:
                 print(f"[Log Setup Warning] Invalid log_backup_count '{backup_count_config}' in config, using default: 7.", file=sys.stderr)
                 backup_count = 7
        else:
             # Config file not found, use defaults provided to function
             print(f"[Log Setup Info] Config file not found at '{config_path}', using default logging settings (Enabled: {logging_enabled}, Level: {logging.getLevelName(log_level_from_config)}).", file=sys.stderr)
    except Exception as e:
        # Print error if config reading fails
        print(f"[Log Setup Error] Failed to read log settings from '{config_path}': {e}", file=sys.stderr)
        # Continue with default settings

    # Set the overall level for the application logger
    app_logger.setLevel(log_level_from_config)

    # --- Configure Console Handler ---
    console_handler = logging.StreamHandler(sys.stdout)
    # Use the custom IconFormatter, passing only the message format string
    console_handler.setFormatter(IconFormatter(fmt=LOG_FORMAT_CONSOLE))
    console_handler.setLevel(log_level_from_config) # Console shows messages at the configured level

    # --- Configure Rotating File Handler (only if logging is enabled) ---
    file_handler = None
    if logging_enabled:
        try:
            # Ensure the log directory exists
            LOG_DIR_PATH.mkdir(parents=True, exist_ok=True)
            log_file_path = LOG_DIR_PATH / LOG_FILE_NAME

            # Create a handler that rotates logs at midnight, keeping 'backup_count' old files
            file_handler = logging.handlers.TimedRotatingFileHandler(
                log_file_path,
                when="midnight",      # Rotate daily
                interval=1,           # Check every day
                backupCount=backup_count, # Number of old logs to keep
                encoding='utf-8'      # Use UTF-8 encoding
            )
            # Use a standard formatter for the log file
            file_formatter = logging.Formatter(LOG_FORMAT_FILE, datefmt=LOG_DATE_FORMAT)
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(log_level_from_config) # File logs messages at the configured level
        except Exception as e:
            # Print error if file handler setup fails
            print(f"[Log Setup Error] Failed to create file handler for path '{LOG_DIR_PATH / LOG_FILE_NAME}': {e}", file=sys.stderr)
            file_handler = None # Ensure file_handler is None if setup failed

    # --- Add Handlers to the Logger ---
    if logging_enabled:
        # Add console handler regardless of file handler success
        app_logger.addHandler(console_handler)

        log_target = "console"
        if file_handler:
            app_logger.addHandler(file_handler)
            log_target += f" and file '{LOG_DIR_PATH / LOG_FILE_NAME}' (Backups: {backup_count})"
        else:
            log_target += " only (File handler setup failed)"

        # Use print for the final setup message as well
        print(f"[Log Setup Info] Logging enabled. Level: {logging.getLevelName(app_logger.level)}. Output to {log_target}.")
        _handlers_configured = True
    else:
        # If logging is disabled in config, add a NullHandler to prevent warnings
        app_logger.addHandler(logging.NullHandler())
        print("[Log Setup Info] Logging disabled via configuration.")
        _handlers_configured = True

# --- Public Logging Function ---
def log(message: str, level: str = "INFO"):
    """
    Logs a message using the configured application logger ('RealEstateTranscriber').

    Args:
        message: The message string to log.
        level: The logging level ('DEBUG', 'INFO', 'SUCCESS', 'WARNING', 'ERROR', 'CRITICAL').
               Case-insensitive. Defaults to 'INFO'.
    """
    level_upper = level.upper()
    # Get the logger instance (same instance configured by setup_logging)
    logger_instance = logging.getLogger('RealEstateTranscriber')

    # Call the appropriate logging method based on the level string
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
    else: # Default to INFO for unknown levels or explicit 'INFO'
        # Optionally prepend the original level if it wasn't 'INFO'
        log_prefix = f"({level}) " if level_upper != "INFO" else ""
        logger_instance.info(f"{log_prefix}{message}")


# Example usage / test block (no changes needed)
if __name__ == "__main__":
    print("-" * 40)
    print("--- Testing Logging Setup ---")
    print(f"Project Root: {PROJECT_ROOT}")
    print(f"Default Config Path: {DEFAULT_CONFIG_PATH}")
    print(f"Log Directory: {LOG_DIR_PATH}")
    # Setup logging with DEBUG level for testing purposes
    setup_logging(level=logging.DEBUG)
    print("\n--- Sending Test Log Messages ---")
    log("This is a DEBUG message.", "debug")
    log("This is an INFO message.", "info")
    log("This is a SUCCESS message.", "SUCCESS")
    log("This is a WARNING message.", "warning")
    log("This is an ERROR message.", "error")
    log("This is a CRITICAL message.", "critical")
    log("This is an unknown level message.", "VERBOSE") # Test fallback
    print("\nCheck console output above and the log file in the 'logs' directory.")
    print("--- Logging Test Complete ---")
    print("-" * 40)