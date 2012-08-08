import subprocess
import uuid

def local_machine_uuid():
    """Return local machine unique identifier.

    >>> uuid = local_machine_uuid()

    """

    result = subprocess.check_output(
        'hal-get-property --udi '
        '/org/freedesktop/Hal/devices/computer '
        '--key system.hardware.uuid'.split()
        ).strip()

    return uuid.UUID(hex=result)
