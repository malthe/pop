import os
import sys
import logging
import argparse
import venusian
import pkg_resources

from zookeeper import set_log_stream
from pop.client import ZookeeperClient

from pop import log
from pop.command import Command
from pop.command import run
from pop import services

LEVELS = (
    logging.DEBUG, logging.INFO
    )

DESCRIPTION = "Automated build, deployment and service management tool."


class CommandConfiguration(object):
    available_parsers = []
    register = available_parsers.append

    def __init__(self, subparsers):
        self.subparsers = subparsers

        scanner = venusian.Scanner()
        scanner.scan(services)

        self.services = scanner.registry

    def __call__(self):
        for configure in self.available_parsers:
            p = configure(self)
            name = p.prog.split()[-1]
            func = self.get_command(name)
            p.set_defaults(func=func)

    def get_command(self, name):
        """Wrap command class in constructor."""

        def command(options):
            client = ZookeeperClient(
                "%s:%d" % (options.pop('host'), options.pop('port')),
                session_timeout=1000
                )

            path = options.pop('path_prefix')
            force = options.pop('force')

            controller = Command(client, path, self.services, force)
            method = getattr(controller, "cmd_%s" % name)
            return method(**options)

        return command

    @register
    def configure_add_parser(self):
        sub_parser = self.subparsers.add_parser(
            'add', help='add service',
            )

        sub_parser.add_argument(
            '--name', action='store', dest='name',
            help='provide a name for the service',
            )

        service_parser = sub_parser.add_subparsers(
            title='available service',
            metavar='<service>',
            dest='factory_name',
            )

        # XXX: It's possible to convert the
        # service name to an object here, but it's unclear
        # that it's a good programming pattern.
        # service_parser.type = converter

        for name, factory in self.services.items():
            if factory is None:
                continue

            if factory.description is None:
                p = argparse.ArgumentParser()
            else:
                p = service_parser.add_parser(
                    name, help=factory.description,
                    )

            service_parser.choices[name] = p

        return sub_parser

    @register
    def configure_deploy_parser(self):
        sub_parser = self.subparsers.add_parser(
            'deploy', help='deploy service',
            )

        sub_parser.add_argument(
            dest='name',
            help='name of the service to deploy',
            )

        sub_parser.add_argument(
            '--machine', action='store',
            help='name of the machine on which to deploy service',
            )

        return sub_parser

    @register
    def configure_fg_parser(self):
        sub_parser = self.subparsers.add_parser(
            'fg', help='start machine or service agent in foreground',
            )

        sub_parser.add_argument(
            'name', action='store', default=None,
            help='name of the service to start',
            )

        return sub_parser

    @register
    def configure_start_parser(self):
        sub_parser = self.subparsers.add_parser(
            'start', help='start machine or service agent in background',
            )

        sub_parser.add_argument(
            'name', action='store', default=None,
            help='name of the service to start',
            )

        return sub_parser

    @register
    def configure_status_parser(self):
        sub_parser = self.subparsers.add_parser(
            'status', help='show status of service',
            )

        sub_parser.add_argument(
            'name', action='store',
            help='name of the service to display status for',
            )

        return sub_parser

    @register
    def configure_stop_parser(self):
        sub_parser = self.subparsers.add_parser(
            'stop', help='stop machine or service agent running in background',
            )

        sub_parser.add_argument(
            'name', action='store', default=None,
            help='name of the service to stop',
            )

        return sub_parser

    @register
    def configure_dump_parser(self):
        sub_parser = self.subparsers.add_parser(
            'dump', help='dump namespace',
            )

        sub_parser.add_argument(
            "--format",
            metavar="FORMAT",
            default="yaml",
            help="output format (default: '%(default)s')"
            )

        return sub_parser

    @register
    def configure_init_parser(self):
        sub_parser = self.subparsers.add_parser(
            'init', help='initialize namespace',
            )

        sub_parser.add_argument(
            "--admin-identity",
            metavar="<username:password>",
            default="admin:admin",
            help="admin access control identity for zookeeper ACLs"
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
        '--verbosity', '-v', action='count',
        help='increases output verbosity',
        default=0,
        )

    subparsers = parser.add_subparsers(
        title='command argument',
        metavar='<command>',
        )

    configuration = CommandConfiguration(subparsers)
    configuration()

    # Parse arguments
    return parser.parse_args(args)


def main(argv=sys.argv, quiet=False):
    args = parse(argv[1:])
    d = args.__dict__

    prog = os.path.basename(argv[0])
    title = "%s - %s" % (prog, DESCRIPTION.strip('.').lower())
    sys.stderr.write(title + "\n" + "-" * len(title) + "\n")

    # Set up logging
    levels = tuple(reversed(LEVELS))
    verbosity = d.pop('verbosity')
    log.setLevel(levels[min(verbosity, len(levels) - 1)])

    if verbosity:
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
    run(d.pop('func'), verbosity > 1, d)
