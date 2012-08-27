import sys
import logging
import StringIO

from twisted.trial.unittest import TestCase as TrialTestCase
from twisted.internet.defer import setDebugging

setDebugging(True)


class TestCase(TrialTestCase):
    @property
    def reactor(self):
        from twisted.internet import reactor
        return reactor

    def capture_stream(self, stream_name):
        original = getattr(sys, stream_name)
        new = StringIO.StringIO()

        @self.addCleanup
        def reset_stream():
            setattr(sys, stream_name, original)

        setattr(sys, stream_name, new)
        return new

    def capture_logging(self, name="", level=logging.INFO,
                        log_file=None, formatter=None):
        if log_file is None:
            log_file = StringIO.StringIO()
        log_handler = logging.StreamHandler(log_file)
        if formatter:
            log_handler.setFormatter(formatter)
        logger = logging.getLogger(name)
        logger.addHandler(log_handler)
        old_logger_level = logger.level
        logger.setLevel(level)

        @self.addCleanup
        def reset_logging():
            logger.removeHandler(log_handler)
            logger.setLevel(old_logger_level)

        return log_file

