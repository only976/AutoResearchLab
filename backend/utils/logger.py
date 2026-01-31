import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler

def setup_logger(name, log_dir="logs", level=logging.INFO):
    """
    Sets up a logger with console and time-rotating file handlers.
    
    Args:
        name (str): Name of the logger (usually __name__).
        log_dir (str): Directory to store log files.
        level (int): Logging level.
        
    Returns:
        logging.Logger: Configured logger instance.
    """
    # Create logs directory if it doesn't exist
    # If log_dir is relative, make it absolute relative to project root (assuming we run from root)
    if not os.path.isabs(log_dir):
        base_dir = os.getcwd()
        log_dir = os.path.join(base_dir, log_dir)
        
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid adding handlers multiple times if logger is already configured
    if not logger.handlers:
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 1. Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # 2. Time Rotating File Handler
        # Rotates at midnight, keeps 30 days of backup
        log_file = os.path.join(log_dir, "system.log")
        file_handler = TimedRotatingFileHandler(
            log_file, 
            when="midnight", 
            interval=1, 
            backupCount=30,
            encoding='utf-8'
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # 3. Error File Handler (Capture errors separately)
        error_log_file = os.path.join(log_dir, "error.log")
        error_handler = TimedRotatingFileHandler(
            error_log_file,
            when="midnight",
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        logger.addHandler(error_handler)

    return logger
