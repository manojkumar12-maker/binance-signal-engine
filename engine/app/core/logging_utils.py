import logging
import sys

class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[36m',
        'INFO': '\033[32m',
        'WARNING': '\033[33m',
        'ERROR': '\033[31m',
        'CRITICAL': '\033[35m',
        'RESET': '\033[0m',
        'BOLD': '\033[1m',
        'DIM': '\033[2m'
    }
    
    def __init__(self):
        super().__init__(fmt='%(message)s')
    
    def format(self, record):
        if hasattr(sys, '_run_from_cmdline'):
            return record.getMessage()
        
        level = record.levelname
        color = self.COLORS.get(level, '')
        reset = self.COLORS['RESET']
        
        record.levelname = f"{color}{level}{reset}"
        return record.getMessage()


def setup_logger(name: str = None, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(ColoredFormatter())
        logger.addHandler(handler)
    
    return logger


def log_section(title: str, logger: logging.Logger = None):
    if logger is None:
        logger = logging.getLogger(__name__)
    
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"  {title}")
    logger.info("=" * 60)


def log_subsection(title: str, logger: logging.Logger = None):
    if logger is None:
        logger = logging.getLogger(__name__)
    
    logger.info("")
    logger.info("-" * 50)
    logger.info(f"  {title}")
    logger.info("-" * 50)


def log_progress(current: int, total: int, prefix: str = "", logger: logging.Logger = None):
    if logger is None:
        logger = logging.getLogger(__name__)
    
    pct = int(current / total * 20)
    bar = "█" * pct + "░" * (20 - pct)
    logger.info(f"{prefix} [{bar}] {current}/{total}")


def log_stats(stats: dict, logger: logging.Logger = None):
    if logger is None:
        logger = logging.getLogger(__name__)
    
    logger.info("")
    logger.info("┌" + "─" * 40 + "┐")
    logger.info("│" + " STATISTICS ".center(40) + "│")
    logger.info("├" + "─" * 40 + "┤")
    
    for key, value in stats.items():
        logger.info(f"│  {key:<20} {str(value):>15} │")
    
    logger.info("└" + "─" * 40 + "┘")


DEFAULT_LOGGER = setup_logger()
