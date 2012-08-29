import gc
import os
import sys
import traceback

from twisted.internet.process import _listOpenFDs
from pop.exceptions import ProcessForked


def fork(uid=None, gid=None):
    settingUID = (uid is not None) or (gid is not None)
    collectorEnabled = gc.isenabled()
    gc.disable()

    if settingUID:
        curegid = os.getegid()
        currgid = os.getgid()
        cureuid = os.geteuid()
        curruid = os.getuid()
        if uid is None:
            uid = cureuid
        if gid is None:
            gid = curegid

        # Prepare to change UID in subprocess.
        os.setuid(0)
        os.setgid(0)

    try:
        pid = os.fork()
    except:
        # Still in the parent process.
        if settingUID:
            os.setregid(currgid, curegid)
            os.setreuid(curruid, cureuid)
        if collectorEnabled:
            gc.enable()
        raise
    else:
        if pid == 0:  # pid is 0 in the child process
            # do not put *ANY* code outside the try block. The
            # child process must either exec or _exit. If it gets
            # outside this block (due to an exception that is not
            # handled here, but which might be handled higher up),
            # there will be two copies of the parent running in
            # parallel, doing all kinds of damage.

            # After each change to this code, review it to make sure there
            # are no exit paths.
            try:
                # Stop debugging. If I am, I don't care anymore.
                sys.settrace(None)

                for fd in _listOpenFDs():
                    if fd > 2:
                        try:
                            os.dup(fd)
                        except:
                            pass
            except:
                try:
                    stderr = os.fdopen(2, 'w')
                    traceback.print_exc(file=stderr)
                    stderr.flush()
                    for fd in range(3):
                        os.close(fd)
                except:
                    pass  # make *sure* the child terminates
            else:
                raise ProcessForked()

            # Did you read the comment about not adding code here?
            os._exit(1)

    # we are now in parent process
    if settingUID:
        os.setregid(currgid, curegid)
        os.setreuid(curruid, cureuid)

    if collectorEnabled:
        gc.enable()

    return pid
