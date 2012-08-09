import sys
import logging
import argparse
import pkg_resources

from zookeeper import set_log_stream

from pop import log
from pop.command import Command

LEVELS = (
    logging.DEBUG, logging.INFO
    )


def configure_init_parser(subparsers):
    sub_parser = subparsers.add_parser(
        'init', help='initialize namespace',
        )

    sub_parser.add_argument(
        "--admin-identity",
        default="admin:admin",
        help="Admin access control identity for zookeeper ACLs"
        )

    return sub_parser


def main(argv=sys.argv, quiet=False):
    parser = argparse.ArgumentParser(
        description='Automated build, deployment and service management tool.',
        epilog="Have a nice day!",
        )

    parser.add_argument(
        '--force', '-f', action='store_true',
        help='force operation',
        )

    parser.add_argument(
        '--host', action='store',
        help='zookeeper host',
        default='localhost',
        )

    parser.add_argument(
        '--port', action='store', type=int,
        help='zookeeper port',
        default=2181,
        )

    parser.add_argument(
        '--verbose', '-v', action='count',
        help='increases output verbosity',
        default=0,
        )

    subparsers = parser.add_subparsers(
        title='command argument',
        metavar='<command>\n',
        )

    parsers = {}

    parsers['init'] = configure_init_parser(subparsers)

    command = Command()
    for name, p in parsers.items():
        p.set_defaults(func=getattr(command, "cmd_%s" % name))

    # Parse arguments
    args = parser.parse_args(argv[1:])

    title = "%s - %s" % (parser.prog, parser.description.strip('.').lower())
    print(title + "\n" + "-" * len(title))

    # Set up logging
    levels = tuple(reversed(LEVELS))
    log.setLevel(levels[min(args.verbose, len(levels) - 1)])

    if args.verbose:
        FORMAT = '%(asctime)-15s %(message)s'
    else:
        FORMAT = '>>> %(message)s'

    logging.basicConfig(format=FORMAT)
    logging.getLogger().setLevel(logging.WARN)
    set_log_stream(open('/dev/null', 'w'))

    log.debug("all arguments parsed.")
    package = pkg_resources.get_distribution("pop")
    log.debug("%s system initialized." % package.egg_name().lower())

    # Invoke command
    args.func(args)
