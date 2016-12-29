#!/usr/bin/python3

#  Copyright (C) 2016  Daniele Parmeggiani <dani.parmeggiani@gmail.com>
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.


import sys
import argparse
import logging
import logging.config


logging.config.dictConfig({
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(levelname)s|%(asctime)s|%(name)s L%(lineno)d:   %(message)s'
        }
    },
    'handlers': {
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'default',
            'filename': '/tmp/SUS.log',
            'maxBytes': 10000,
            'backupCount': 1
        },
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default'
        }
    },
    'loggers': {
        '': {
            'handlers': ['file', 'console'],
            'level': 'DEBUG',
            'propagate': True
        }
    }
})


logger = logging.getLogger('main')


class SUS:
    def __init__(self):
        parser = argparse.ArgumentParser(prog='SUS',
            usage='''SUS [<command>] [<options>...]

Type `SUS` without a command to open the interactive client.

Common commands:
   send        Send a message
   reply       Reply to the last message received
   silence     Silence a conversation

Service commands:
   start       Start SUS    :)
   shutdown    Shutdown SUS :(

Type `SUS <command> --help` for information about specific commands.
''')
        logger.info('SUS started. Args: {}'.format(sys.argv))
        if len(sys.argv) == 1:
            self.interactive_mode()
            return
        parser.add_argument('command', help='Command to run')
        args = parser.parse_args(sys.argv[1:2])
        if not hasattr(self, args.command) or args.command.startswith('__'):
            print('Unknown command: {}.'.format(args.command))
            parser.print_help()
            sys.exit(1)
        else:
            getattr(self, args.command)()

    def start(self):
        import SUSd
        args = argparse.ArgumentParser(prog='SUS start')
        args.add_argument('-n', '--non-daemon', help='start SUS in non-daemon mode.',
                          action='store_true')
        args.add_argument('-i', '--ip', help='ip for SUS services.', default='',
                          action='store')
        args = args.parse_args(sys.argv[2:])
        print(dir(args))
        SUSd.start(args)

    def shutdown(self):
        import SUSd
        args = argparse.ArgumentParser(prog='SUS shutdown')
        args.add_argument('-k', '--kill', help='send SIGKILL instead of SIGTERM.',
                          action='store_true')
        args = args.parse_args(sys.argv[2:])
        SUSd.shutdown(args)

    def send(self):
        print('send')

    def interactive_mode(self):
        print('interactive mode')


if __name__ == '__main__':
    SUS()
