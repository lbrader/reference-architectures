# --------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
# --------------------------------------------------------------------------------------------

"""
Logging for Azure CLI

- Loggers: The name of the parent logger is defined in AZ_ROOT_LOGGER_NAME variable. All the loggers used in the CLI
           must descends from it, otherwise it won't benefit from the logger handlers, filters and level configuration.

- Handlers: There are two default handlers will be added to both CLI parent logger and root logger. One is a colorized
            stream handler for console output and the other is a file logger handler. The file logger can be enabled or
            disabled through 'az configure' command. The logging file locates at path defined in AZ_LOGFILE_DIR.

- Level: Based on the verbosity option given by users, the logging levels for root and CLI parent loggers are:

               CLI Parent                  Root
            Console     File        Console     File
omitted     Warning     Debug       Critical    Debug
--verbose   Info        Debug       Critical    Debug
--debug     Debug       Debug       Debug       Debug

"""

import os
import platform
import logging
import logging.handlers
import colorama
import time


ROOT_LOGGER_NAME = 'app'


class JoaraLoggingLevelManager(object):  # pylint: disable=too-few-public-methods
    CONSOLE_LOG_CONFIGS = [
        # (default)
        {
            ROOT_LOGGER_NAME: logging.WARNING,
            'root': logging.CRITICAL,
        },
        # --verbose
        {
            ROOT_LOGGER_NAME: logging.INFO,
            'root': logging.WARNING,
        },
        # --debug
        {
            ROOT_LOGGER_NAME: logging.DEBUG,
            'root': logging.DEBUG,
        }]

    def __init__(self, argv):
        self.user_setting_level = self.determine_verbose_level(argv)

    def get_user_setting_level(self, logger):
        logger_name = logger.name if logger.name in (ROOT_LOGGER_NAME, 'root') else 'root'
        return self.CONSOLE_LOG_CONFIGS[self.user_setting_level][logger_name]

    @classmethod
    def determine_verbose_level(cls, argv):
        # Get verbose level by reading the arguments.
        # Remove any consumed args.
        verbose_level = 0
        i = 0
        while i < len(argv):
            arg = argv[i]
            if arg in ['--verbose']:
                verbose_level += 1
                argv.pop(i)
            elif arg in ['--debug']:
                verbose_level += 2
                argv.pop(i)
            else:
                i += 1

        # Use max verbose level if too much verbosity specified.
        return min(verbose_level, len(cls.CONSOLE_LOG_CONFIGS) - 1)


class ColorizedStreamHandler(logging.StreamHandler):
    COLOR_MAP = {
        logging.CRITICAL: colorama.Fore.RED,
        logging.ERROR: colorama.Fore.RED,
        logging.WARNING: colorama.Fore.YELLOW,
        logging.INFO: colorama.Fore.GREEN,
        logging.DEBUG: colorama.Fore.CYAN,
    }

    # Formats for console logging if coloring is enabled or not.
    # Show the level name if coloring is disabled (e.g. INFO).
    # Also, Root logger should show the logger name.
    CONSOLE_LOG_FORMAT = {
        'app': {
            True: '%(message)s',
            False: '%(levelname)s: %(message)s',
        },
        'root': {
            True: '%(name)s : %(message)s',
            False: '%(levelname)s: %(name)s : %(message)s',
        }
    }

    def __init__(self, stream, logger, level_manager):
        super(ColorizedStreamHandler, self).__init__(stream)

        if platform.system() == 'Windows':
            self.stream = colorama.AnsiToWin32(self.stream).stream

        fmt = self.CONSOLE_LOG_FORMAT[logger.name][self.enable_color]
        super(ColorizedStreamHandler, self).setFormatter(logging.Formatter(fmt))
        super(ColorizedStreamHandler, self).setLevel(level_manager.get_user_setting_level(logger))

    def format(self, record):
        msg = logging.StreamHandler.format(self, record)
        if self.enable_color:
            try:
                msg = '{}{}{}'.format(self.COLOR_MAP[record.levelno], msg, colorama.Style.RESET_ALL)
            except KeyError:
                pass
        return msg

    @property
    def enable_color(self):
        try:
            # Color if tty stream available
            if self.stream.isatty():
                return True
        except (AttributeError, ValueError):
            pass

        return False


class JoaraRotatingFileHandler(logging.handlers.RotatingFileHandler):
    from ..env.env import get_cluster_config


    def getboolean(value):
        _BOOLEAN_STATES = {'1': True, 'yes': True, 'true': True, 'on': True,
                           '0': False, 'no': False, 'false': False, 'off': False}
        try:
            val = str(value)
            if val.lower() not in _BOOLEAN_STATES:
                raise ValueError('Not a boolean: {}'.format(val))
            return _BOOLEAN_STATES[val.lower()]
        except:
            return False


    ENABLED = True
    LOGFILE_DIR = os.path.join(os.getcwd(), 'logs')
    cluster_config = get_cluster_config("common")
    if 'LOGGING_ENABLED' in cluster_config:
        ENABLED = getboolean(cluster_config['LOGGING_ENABLED'])

    if 'LOG_FOLDER' in cluster_config:
        LOGFILE_DIR = os.path.join(cluster_config['LOG_FOLDER'], 'logs')

    def __init__(self):
        logging_file_path = self.get_log_file_path()
        super(JoaraRotatingFileHandler, self).__init__(logging_file_path, maxBytes=10 * 1024 * 1024, backupCount=5)
        self.setFormatter(logging.Formatter('%(process)d : %(asctime)s : %(levelname)s : %(name)s : %(message)s'))
        self.setLevel(logging.DEBUG)

    def get_log_file_path(self):
        if not os.path.isdir(self.LOGFILE_DIR):
            os.makedirs(self.LOGFILE_DIR, exist_ok=True)
        millis = int(round(time.time() * 1000))
        return os.path.join(self.LOGFILE_DIR, 'app_{}.log'.format(millis))


def configure_logging(argv, stream=None):
    """
    Configuring the loggers and their handlers. In the production setting, the method is a single entry.
    However, when running in automation, the method could be entered multiple times. Therefore all the handlers will be
    cleared first.
    """
    level_manager = JoaraLoggingLevelManager(argv)
    loggers = [logging.getLogger(), logging.getLogger(ROOT_LOGGER_NAME)]

    logging.getLogger(ROOT_LOGGER_NAME).propagate = False

    for logger in loggers:
        # Set the levels of the loggers to lowest level.Handlers can override by choosing a higher level.
        logger.setLevel(logging.DEBUG)

        # clear the handlers. the handlers are not closed as this only effect the automation scenarios.
        kept = [h for h in logger.handlers if not isinstance(h, (ColorizedStreamHandler, JoaraRotatingFileHandler))]
        logger.handlers = kept

        # add colorized console handler
        logger.addHandler(ColorizedStreamHandler(stream, logger, level_manager))

       # add file handler
        if JoaraRotatingFileHandler.ENABLED:
            logger.addHandler(JoaraRotatingFileHandler())

    if JoaraRotatingFileHandler.ENABLED:
        get_logger(__name__).debug("File logging enabled - Writing logs to '%s'.", JoaraRotatingFileHandler.LOGFILE_DIR)


def get_logger(module_name=None):
    return logging.getLogger(ROOT_LOGGER_NAME).getChild(module_name) if module_name else logging.getLogger(
        ROOT_LOGGER_NAME)