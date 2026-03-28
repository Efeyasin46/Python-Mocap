import logging
import os
from datetime import datetime

def setup_logger(name="MotionForge"):
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    # Formatter
    formatter = logging.Formatter('%(asctime)s | %(levelname)-8s | [%(name)s] %(message)s')
    
    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # File Handler
    log_file = os.path.join('logs', f"engine_{datetime.now().strftime('%Y%m%d')}.log")
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    if not logger.handlers:
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
        
    return logger

# Global Engine Logger
engine_logger = setup_logger("Engine")
