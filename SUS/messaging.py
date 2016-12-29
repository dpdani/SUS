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


import socket
import threading
import collections
import logging


logger = logging.getLogger('messaging')


incoming_messages = collections.deque()
outgoing_messages = collections.deque()


SUS_MESSAGES_PORT = 6666


class InboxServer:
    def __init__(self, ip, inactivity_timeout=2, buffer_size=1024):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind((ip, SUS_MESSAGES_PORT))
        self.inactivity_timeout = inactivity_timeout
        self.buffer_size = buffer_size
        self.threads = []
        self.stop = threading.Event()

    def listen(self):
        self.server.listen(5)
        logger.info('inbox server listening at {}.'.format(self.server))
        while not self.stop.is_set():
            client, address = self.server.accept()
            client.settimeout(self.inactivity_timeout)
            thread = threading.Thread(target=self.serve_client, args=(client, address))
            thread.start()
            self.threads.append(thread)
        logger.info('stop set. Inbox is shutting down.')

    def serve_client(self, client, address):
        # logging?
        logger.info('connected to {}:{}.'.format(address[0], address[1]))
        received = ''
        try:
            while not self.stop.is_set():
                fragment = client.recv(self.buffer_size)
                if fragment == b'':
                    break
                received = ''.join([received, fragment.decode('utf-8')])
                if received.rstrip().endswith('##END'):
                    break
        except socket.error as exc:
            self.closed_connection(address, exc)
            return
        if not self.stop.is_set():
            client.sendall(b'OK\n')
            client.sendall(str(
                self.handle_message(received, address[0])
            ).encode('utf-8'))
        client.close()
        self.closed_connection(address)

    def handle_message(self, message, sender):
        logger.info('new message from <{}>: "{}"'.format(sender, message))
        incoming_messages.append((sender, message))
        return 200

    @staticmethod
    def closed_connection(address, exception=None):
        if exception is None:
            logger.info('closed connection to {}:{}.'.format(address[0], address[1]))
        else:
            logger.info('closed connection to {}:{} due to error <{}>: {}.'.format(
                address[0], address[1], exception.__class__.__name__, exception))


class OutboxSender:
    def __init__(self, watch=outgoing_messages):
        self.watch = watch
        self.threads = []
        self.stop = threading.Event()

    def start(self):
        logger.info('outbox started. Watching {}.'.format(self.watch))
        while not self.stop.is_set():
            if len(self.watch) <= 0:
                continue
            message = self.watch.popleft()
            t = threading.Thread(target=self.send_message, args=(message,))
            t.start()
        logger.info('stop set. Outbox is shutting down.')

    def send_message(self, message):
        recipient = message[0]
        message = message[1]
        logger.info('sending message "{}" to <{}>.'.format(message, recipient))
        try:
            conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            conn.connect((recipient, SUS_MESSAGES_PORT))
        except:
            self.handle_not_sent((recipient, message))
            return
        if not self.stop.is_set():
            conn.sendall(message.encode('utf-8'))
            conn.sendall(b'##END')
            received = conn.recv(100).decode('utf-8')
            if 'OK\n200' not in received:
                self.handle_not_sent((recipient, message))
                logger.info('correctly sent message.')
        else:
            self.handle_not_sent((recipient, message))
        conn.close()

    def handle_not_sent(self, message):
        logger.info('message not sent.')
        self.watch.appendleft(message)
