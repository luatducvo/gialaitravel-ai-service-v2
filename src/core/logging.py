from loguru import logger
import sys

def setup_logging():
    logger.remove()  # Remove default handler
    
    # Console: colorful, human-readable
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level="DEBUG",
        colorize=True,
    )
    
    # File: JSON structured, rotate daily
    logger.add(
        "logs/ai_service_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}",
        rotation="1 day",
        retention="7 days",
        level="INFO",
    )
