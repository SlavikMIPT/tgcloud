#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

from __future__ import print_function
from __future__ import unicode_literals
import os
import shutil
import time
import tempfile
from telethon.tl.types import DocumentAttributeFilename

from telegram_client_x import TelegramClientX
from tg_access import *
from io import StringIO
import sys


class Buffer:  # {{{1

    """
    This class wraps cStringIO.StringIO with two additions: The __len__
    method and a dirty flag to determine whether a buffer has changed.
    """

    def __init__(self):
        self.buf = StringIO()
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
client = TelegramClientX(entity, api_id, api_hash, update_workers=None, spawn_read_thread=True)
client.set_upload_threads_count(24)
client.set_download_threads_count(8)
last_call_time_sent = time.time()
last_call_time_receive = time.time()


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


def download_block(chat_id, hash_uid):
    try:
        os.chdir(path_home)
        if not client.is_connected():
            client.connect()
        if not client.is_user_authorized():
            client.send_code_request(phone)
            client.sign_in(phone, input('Enter code: '))
        chat_id = int(chat_id) if chat_id.isdigit() else str(chat_id)
        entity = client.get_entity(chat_id)
        messages = client.get_messages(entity, limit=20)
        for i in range(20):
            msg = messages[i]
            if msg.message == str(hash_uid):
                outbuf = tempfile.NamedTemporaryFile()
                client.download_media(msg, file=outbuf, progress_callback=on_upload_progress)

                outbuf.seek(0)
                sys.stdout.buffer.write(outbuf.read())
                outbuf.close()
                return 0
            return -1
    except Exception as e:
        # print(e)
        return -1
    finally:
        client.disconnect()


def upload_block(bytesin, chat_id, hash_uid):
    try:
        filename = str(hash_uid)
        os.chdir(path_home)
        if not client.is_connected():
            client.connect()
        if not client.is_user_authorized():
            client.send_code_request(phone)
            client.sign_in(phone, input('Enter code: '))
        chat_id = int(chat_id) if chat_id.isdigit() else str(chat_id)
        entity = client.get_entity(chat_id)
        document_attribute = [DocumentAttributeFilename(filename)]
        client.send_file(entity,
                         file=bytesin,
                         caption=str(hash_uid),
                         file_name=filename,
                         allow_cache=False,
                         part_size_kb=512,
                         attributes=document_attribute,
                         progress_callback=on_upload_progress)
        return 0
    except Exception as e:
        # print(e)
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

# upload_file(48012045,48012045,'test2.mp4','4801204577235b9d06db52e7209086ebbc8',is_gif=False)
# download_block(709766994,'012345678910abcdef')
