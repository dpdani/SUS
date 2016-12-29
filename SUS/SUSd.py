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


import daemon
import daemon.runner
import lockfile
import signal
import threading
import os
import logging
import sys


logger = logging.getLogger('SUSd')
logger.info('SUSd loaded.')


stop = threading.Event()


def start(args):
    """ Start the daemon, if not already running. """
    # args: as given from argparse
    logger.info('attempting start.')
    try:
        pidfile = daemon.runner.make_pidlockfile('/tmp/SUS.pid', acquire_timeout=1)
    except lockfile.LockTimeout:
        logger.info('start failed: lockfile timed out.')
        print('error>  SUS is already running!')
        return
    if not pidfile.is_locked():
        logger.info('start successful.')
        print('SUS>  :)')
        if args.non_daemon:
            run(args)
        else:
            with daemon.DaemonContext(
                pidfile=pidfile,
                signal_map={
                    signal.SIGTERM: close,
                    signal.SIGTSTP: close,
                },
                files_preserve=[
                    logging.root.handlers[0].stream.fileno(),
                    # sys.stderr.fileno(), sys.stdout.fileno(), sys.stdin.fileno()
                ],
                stdout=sys.stdout,
            ):
                run(args)
    else:
        logger.info('start failed: lockfile locked.')
        print('error>  SUS is already running!')
        return


def close(signum, frame):
    """ Catches SIGTERM and SIGTSTP. """
    stop.set()


def shutdown(args):
    """ Send SIGTERM to the running daemon. """
    # args: as given from argparse
    try:
        with open('/tmp/SUS.pid', 'r') as pidfile:
            pid = int(pidfile.read().strip())
    except:
        print("error>  SUS isn't running!")
        return
    try:
        if args.kill:
            os.kill(pid, signal.SIGKILL)
            os.remove('/tmp/SUS.pid')
            logger.info('sent SIGKILL to {}.'.format(pid))
        else:
            os.kill(pid, signal.SIGTERM)
            logger.info('sent SIGTERM to {}.'.format(pid))
    except ProcessLookupError:
        print("error>  SUS isn't running!")
        return
    print('SUS>  :(')


def run(args):
    global stop

    logger.info('setting up messaging services.')
    # Setting up messaging services
    import messaging
    inbox = messaging.InboxServer(ip=args.ip)
    inbox.stop = stop
    inbox_thread = threading.Thread(target=inbox.listen, name='Inbox')
    inbox_thread.start()
    outbox = messaging.OutboxSender()
    outbox.stop = stop
    outbox_thread = threading.Thread(target=outbox.start, name='Outbox')
    outbox_thread.start()
    newmessages = messaging.NewMessagesHandlerStdout()
    newmessages.stop = stop
    newmessages_thread = threading.Thread(target=newmessages.start, name='NewMessagesHdlr')
    newmessages_thread.start()
    logger.info('done setting up messaging services.')

    # threads only join when stopped by a SIGTERM -> shutdown
    inbox_thread.join()
    outbox_thread.join()
    newmessages_thread.join()
    for t in inbox.threads:
        t.join(timeout=0.5)
    for t in outbox.threads:
        t.join(timeout=0.5)
