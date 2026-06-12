# Copyright 2026 J Code
# SPDX-License-Identifier: Apache-2.0
import os
import logging
import logging.handlers
from typing import Dict, Optional

class LogManager:
    def __init__(self):
        self._enabled = False
        self._loggers: Dict[str, logging.Logger] = {}
        self._log_dir = 'logs'
        self._level = logging.INFO
        self._console = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value
        if value and not self._loggers:
            self._initialize_default_logger()

    def configure(self, enabled: bool = True, log_dir: str = 'logs',
                  level: int = logging.INFO, console: bool = True):
        self._enabled = enabled
        self._log_dir = log_dir
        self._level = level
        self._console = console
        if enabled:
            self._initialize_default_logger()
            self.info("LogManager", "Logging system initialized")

    def _initialize_default_logger(self):
        if 'JWebs' not in self._loggers:
            self.get_logger('JWebs')

    def get_logger(self, name: str) -> Optional[logging.Logger]:
        if not self._enabled:
            return None
        if name in self._loggers:
            return self._loggers[name]
        logger = logging.getLogger(f"jwebs.{name}")
        logger.setLevel(self._level)
        if not logger.handlers:
            self._setup_handlers(logger, name)
        self._loggers[name] = logger
        return logger

    def _setup_handlers(self, logger: logging.Logger, name: str):
        os.makedirs(self._log_dir, exist_ok=True)
        file_format = logging.Formatter(
            '%(asctime)s | %(name)-20s | %(levelname)-8s | %(filename)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_format = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s',
            datefmt='%H:%M:%S'
        )
        main_handler = logging.handlers.RotatingFileHandler(
            os.path.join(self._log_dir, f'{name}.log'),
            maxBytes=10_485_760, backupCount=5
        )
        main_handler.setLevel(logging.DEBUG)
        main_handler.setFormatter(file_format)
        logger.addHandler(main_handler)
        error_handler = logging.handlers.RotatingFileHandler(
            os.path.join(self._log_dir, f'{name}_errors.log'),
            maxBytes=10_485_760, backupCount=5
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_format)
        logger.addHandler(error_handler)
        if self._console:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(console_format)
            logger.addHandler(console_handler)

    def _log(self, level: int, logger_name: str, msg: str, *args, **kwargs):
        if not self._enabled:
            return
        lgr = self.get_logger(logger_name)
        if lgr:
            lgr.log(level, msg, *args, **kwargs)

    def debug(self, logger_name: str, msg: str, *args, **kwargs):
        self._log(logging.DEBUG, logger_name, msg, *args, **kwargs)

    def info(self, logger_name: str, msg: str, *args, **kwargs):
        self._log(logging.INFO, logger_name, msg, *args, **kwargs)

    def warning(self, logger_name: str, msg: str, *args, **kwargs):
        self._log(logging.WARNING, logger_name, msg, *args, **kwargs)

    def error(self, logger_name: str, msg: str, *args, exc_info: bool = False, **kwargs):
        if exc_info:
            kwargs['exc_info'] = True
        self._log(logging.ERROR, logger_name, msg, *args, **kwargs)

    def critical(self, logger_name: str, msg: str, *args, **kwargs):
        self._log(logging.CRITICAL, logger_name, msg, *args, **kwargs)

    def exception(self, logger_name: str, msg: str, *args, **kwargs):
        if self._enabled:
            lgr = self.get_logger(logger_name)
            if lgr:
                lgr.exception(msg, *args, **kwargs)

    def clear_logs(self):
        self._loggers.clear()

logger = LogManager()