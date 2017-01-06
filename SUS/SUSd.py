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
import socket
import messaging


logger = logging.getLogger('SUSd')
logger.info('SUSd loaded.')


stop = threading.Event()


SUSD_SHELL_PORT = 7777


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
    import messaging
    stop.set()
    socket.socket(socket.AF_INET, socket.SOCK_STREAM) \
        .connect(('', messaging.SUS_MESSAGES_PORT))  # makes inboxsocket.accept return.
                                                     # See messaging.InboxServer.listen


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
    shell = Shell(ip=args.ip)
    shell.stop = stop
    shell_thread = threading.Thread(target=shell.listen, name='Shell')
    shell_thread.start()
    logger.info('done setting up services.')

    # threads only join when stopped by a SIGTERM -> shutdown
    inbox_thread.join()
    outbox_thread.join(timeout=0.5)
    newmessages_thread.join(timeout=0.5)
    shell_thread.join(timeout=0.5)
    logger.info('SUS is shutting down.')


def send(recipient, message):
    if message.find('##END') > -1:
        print('error>  cannot have "##END" inside of message.')
        return
    logger.info('sending "{}" to <{}>.'.format(message, recipient))
    susd_shell = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        susd_shell.connect(('', SUSD_SHELL_PORT))
    except socket.error:
        print('error>  SUS isn\'t running.')
        return
    susd_shell.sendall(b'send ')
    susd_shell.sendall(recipient.encode('utf-8'))
    susd_shell.sendall(b' ')
    susd_shell.sendall(message.encode('utf-8'))
    susd_shell.sendall(b'\n')
    received = ''
    while len(received) != 6:
        fragment = susd_shell.recv(100)
        if fragment == b'':
            break
        received = ''.join([received, fragment.decode('utf-8')])
    status = received.strip()
    susd_shell.close()
    if status == 'OK\n200':
        print('SUS>  ✓')
    else:
        print('SUS>  error on accepting message.')


def reply(message):
    if message.find('##END') > -1:
        print('error>  cannot have "##END" inside of message.')
        return
    logger.info('replying with "{}".'.format(message))
    susd_shell = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        susd_shell.connect(('', SUSD_SHELL_PORT))
    except socket.error:
        print('error>  SUS isn\'t running.')
        return
    susd_shell.sendall(b'reply ')
    susd_shell.sendall(message.encode('utf-8'))
    susd_shell.sendall(b'\n')
    received = ''
    while len(received) != 6:
        fragment = susd_shell.recv(100)
        if fragment == b'':
            break
        received = ''.join([received, fragment.decode('utf-8')])
    status = received.strip()
    susd_shell.close()
    if status == 'OK\n200':
        print('SUS>  ✓')
    elif status == 'OK\n400':
        print('error>  no message to reply to.')
    else:
        print('SUS>  error on accepting message.')


class Shell:
    """ Shell for receiving commands while the daemon is running. """
    def __init__(self, ip, inactivity_timeout=2, buffer_size=1024):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind((ip, SUSD_SHELL_PORT))
        self.inactivity_timeout = inactivity_timeout
        self.buffer_size = buffer_size
        self.threads = []
        self.stop = threading.Event()

    def listen(self):
        self.server.listen(5)
        logger.info('shell server listening at {}.'.format(self.server))
        while not self.stop.is_set():
            client, address = self.server.accept()
            client.settimeout(self.inactivity_timeout)
            thread = threading.Thread(target=self.serve_client, args=(client, address))
            thread.start()
            self.threads.append(thread)
        logger.info('stop set. Shell is shutting down.')
        for t in self.threads:
            t.join(timeout=0.1)

    def serve_client(self, client, address):
        logger.info('connected to {}:{}.'.format(address[0], address[1]))
        received = ''
        try:
            while not self.stop.is_set():
                fragment = client.recv(self.buffer_size)
                if fragment == b'':
                    break
                received = ''.join([received, fragment.decode('utf-8')])
                if received.endswith('\n'):
                    break
        except socket.error as exc:
            self.closed_connection(address, exc)
            return
        if not self.stop.is_set():
            client.sendall(b'OK\n')
            client.sendall(str(
                self.handle_command(received)
            ).encode('utf-8'))
        client.close()
        self.closed_connection(address)

    def handle_command(self, command):
        command = command.split(' ', maxsplit=2)
        if command[0] == 'send':
            messaging.outgoing_messages.append((command[1], command[2]))
            return 200
        if command[0] == 'reply':
            if messaging.last_received_sender is None:
                return 400
            message = ' '.join(command[1:])
            messaging.outgoing_messages.append((messaging.last_received_sender, message))
            return 200
        else:
            return 404

    @staticmethod
    def closed_connection(address, exception=None):
        if exception is None:
            logger.info('closed connection to {}:{}.'.format(address[0], address[1]))
        else:
            logger.info('closed connection to {}:{} due to error <{}>: {}.'.format(
                address[0], address[1], exception.__class__.__name__, exception))
