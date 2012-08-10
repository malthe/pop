import os
import sys
import logging
import argparse
import pkg_resources

from zookeeper import set_log_stream

from pop import log
from pop.command import Command
from pop.command import run

LEVELS = (
    logging.DEBUG, logging.INFO
    )

DESCRIPTION = "Automated build, deployment and service management tool."


def configure_init_parser(subparsers):
    sub_parser = subparsers.add_parser(
        'init', help='initialize namespace',
        )

    sub_parser.add_argument(
        "--admin-identity",
        metavar="<username:password>",
        default="admin:admin",
        help="Admin access control identity for zookeeper ACLs"
        )

    return sub_parser


def parse(args):
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
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
        '--path-prefix', action='store', type=str,
        help='zookeeper path prefix', metavar='PATH',
        default="/",
        )

    parser.add_argument(
        '--verbose', '-v', action='count',
        help='increases output verbosity',
        default=0,
        )

    subparsers = parser.add_subparsers(
        title='command argument',
        metavar='<command>',
        )

    parsers = {}

    parsers['init'] = configure_init_parser(subparsers)

    for name, p in parsers.items():
        p.set_defaults(func=getattr(Command, "cmd_%s" % name))

    # Parse arguments
    return parser.parse_args(args)


def main(argv=sys.argv, quiet=False):
    args = parse(argv[1:])

    prog = os.path.basename(argv[0])
    title = "%s - %s" % (prog, DESCRIPTION.strip('.').lower())
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
    run(args)
