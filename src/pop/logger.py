import logging
import traceback

def handleError(self, record):
    traceback.print_stack()

logging.Handler.handleError = handleError
log = logging.getLogger('pop')
