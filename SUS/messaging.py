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


incoming_messages = collections.deque()
outgoing_messages = collections.deque()


class InboxServer:
    def __init__(self, ip, inactivity_timeout=2, buffer_size=1024):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind((ip, 6666))
        self.inactivity_timeout = inactivity_timeout
        self.buffer_size = buffer_size
        self.threads = []
        self.stop = threading.Event()

    def listen(self):
        self.server.listen(5)
        while not self.stop.is_set():
            client, address = self.server.accept()
            client.settimeout(self.inactivity_timeout)
            thread = threading.Thread(target=self.serve_client, args=(client, address))
            thread.start()
            self.threads.append(thread)

    def serve_client(self, client, address):
        # logging?
        received = []
        while not self.stop.is_set():
            fragment = client.recv(self.buffer_size)
            if fragment == b'':
                break
            received.append(fragment.decode('utf-8'))
        if not self.stop.is_set():
            received = ''.join(received)
            client.sendall(b'OK\n')
            client.sendall(str(
                self.handle_message(received, address[0])
            ).encode('utf-8'))
        client.close()

    def handle_message(self, message, sender):
        incoming_messages.append((sender, message))


class OutboxSender:
    def __init__(self, watch=outgoing_messages):
        self.watch = watch
        self.threads = []
        self.stop = threading.Event()

    def start(self):
        while not self.stop.is_set():
            for message in self.watch:
                t = threading.Thread(target=self.send_message, args=(message[0], message[1]))
                t.start()

    def send_message(self, recipient, message):
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.connect((recipient, 6666))
        if not self.stop.is_set():
            conn.sendall(message.encode('utf-8'))
        conn.close()
