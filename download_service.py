#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

from __future__ import print_function
from __future__ import unicode_literals
import os
import shutil
import time
import tempfile
import mimetypes
from telethon.tl.types import DocumentAttributeFilename
from telethon.tl.types import Document
from telethon.utils import get_input_media
from telethon.errors.rpc_error_list import LocationInvalidError
# from telegram_client_x import TelegramClientX
from telethon.telegram_client import TelegramClient
from telethon.tl.types import Message
from tg_access import *
from io import BytesIO
import sys


class Buffer:  # {{{1

    """
    This class wraps cStringIO.StringIO with two additions: The __len__
    method and a dirty flag to determine whether a buffer has changed.
    """

    def __init__(self):
        self.buf = BytesIO()
        self.dirty = False

    def __getattr__(self, attr, default=None):
        """ Delegate to the StringIO object. """
        return getattr(self.buf, attr, default)

    def __len__(self):
        """ Get the total size of the buffer in bytes. """
        position = self.buf.tell()
        self.buf.seek(0, os.SEEK_END)
        length = self.buf.tell()
        self.buf.seek(position, os.SEEK_SET)
        return length

    def truncate(self, *args):
        """ Truncate the file at the current position and set the dirty flag. """
        if len(self) > self.buf.tell():
            self.dirty = True
        return self.buf.truncate(*args)

    def write(self, *args):
        """ Write a string to the file and set the dirty flag. """
        self.dirty = True
        return self.buf.write(*args)


path_home = './'  # os.path.abspath('.')
path_local = './local'
# client = TelegramClientX(entity, api_id, api_hash, update_workers=None, spawn_read_thread=True)
client = TelegramClient(entity, api_id, api_hash, update_workers=None, spawn_read_thread=True)

# client.set_upload_threads_count(24)#24
# client.set_download_threads_count(8)#8
last_call_time_sent = time.time()
last_call_time_receive = time.time()
if not client.is_connected():
    client.start()

def on_download_progress(recv_bytes, total_bytes):
    global last_call_time_receive
    if time.time() - last_call_time_receive < 1:
        return 0
    last_call_time_receive = time.time()
    # print(f"receive {recv_bytes}/{total_bytes}", end="\r")
    return 0

def on_upload_progress(send_bytes, total_bytes):
    global last_call_time_sent
    if time.time() - last_call_time_sent < 1:
        return 0
    last_call_time_sent = time.time()
    # print(f"sent {send_bytes}/{total_bytes}", end="\r")
    return 0

#
def download_block(chat_id, hash_uid):
    try:
        hash_uid = str(hash_uid)
        chat_id = str(chat_id)
        os.chdir(path_home)
        if not client.is_connected():
            client.start()
        chat_id = int(chat_id) if chat_id.isdigit() else chat_id
        entity = client.get_entity(chat_id)
        messages = client.get_messages(entity, limit=40,search=hash_uid)
        for i in range(len(messages)):
            msg = messages[i]
            if msg.message == hash_uid:
                outbuf = tempfile.NamedTemporaryFile()
                client.download_media(msg, file=outbuf, progress_callback=on_download_progress)
                outbuf.seek(0)
                sys.stdout.buffer.write(outbuf.read())
                outbuf.close()
                return 0
    except Exception:
        return -1
    finally:
        client.disconnect()


def upload_block(bytesin, chat_id, hash_uid):
    try:
        hash_uid = str(hash_uid)
        chat_id = str(chat_id)
        os.chdir(path_home)
        if not client.is_connected():
            client.start()
        chat_id = int(chat_id) if chat_id.isdigit() else chat_id
        entity = client.get_entity(chat_id)
        message = client.send_file(entity,
                                     file=bytesin,
                                     caption=f'{hash_uid}',
                                     attributes=[DocumentAttributeFilename(f'{hash_uid}')],
                                     allow_cache=False,
                                     part_size_kb=512,
                                     force_document=True,
                                     progress_callback=on_upload_progress)
        # message.id
        return 0
    except Exception:
        return -1
    finally:
        client.disconnect()


def main(argv):
    try:
        service = str(argv[1])
        if service == 'download':
            chat_id = str(argv[2])
            uid = str(argv[3])
            download_block(chat_id=chat_id, hash_uid=uid)
            return 0
        elif service == 'upload':
            data = sys.stdin.buffer.read()
            chat_id = str(argv[2])
            uid = str(argv[3])
            upload_block(bytesin=data, chat_id=chat_id, hash_uid=uid)
            return 0

    except Exception as e:
        # print(e)
        return -1
    finally:
        client.disconnect()
    return 0


if __name__ == '__main__':
    import sys

    main(sys.argv[0:])

# download_block("slavikmr","d46610254a0afb93228832bdb6122d27e4bcb6c8")