#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

from __future__ import print_function
from __future__ import unicode_literals

import os
import time
from telethon.tl.types import DocumentAttributeFilename

from telethon.telegram_client import TelegramClient
from telegram_client_x import TelegramClientX
from secret import *

path_home = './'  # os.path.abspath('.')
client = TelegramClientX(entity, api_id, api_hash, update_workers=None, spawn_read_thread=True)
# client = TelegramClient(entity, api_id, api_hash, update_workers=None, spawn_read_thread=True)
client.set_upload_threads_count(24)  # 24
client.set_download_threads_count(24)  # 8

last_call_time_sent = time.time()
last_call_time_receive = time.time()

client.connect()

if not client.is_user_authorized():
    raise Exception("Telegram session not found - run from the project folder: python3.6 telegram_create_session.py")


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
def download_block(hash_uid):
    try:
        hash_uid = str(hash_uid)
        os.chdir(path_home)

        entity = client.get_entity(client.get_me())
        messages = client.get_messages(entity, limit=1, search=hash_uid)
        for i in range(len(messages)):
            msg = messages[i]
            if msg.message == hash_uid:
                FIFO = f"pipe_{hash_uid}"
                import errno
                try:
                    os.mkfifo(FIFO)
                except OSError as oe:
                    if oe.errno != errno.EEXIST:
                        raise
                with open(FIFO, 'wb') as outbuf:
                    os.unlink(FIFO)
                    client.download_media(msg, file=outbuf, progress_callback=on_download_progress)
                return 0
    except Exception as e:
        return -1
    finally:
        client.disconnect()


def upload_block(hash_uid):
    try:
        hash_uid = str(hash_uid)
        os.chdir(path_home)
        entity = client.get_entity(client.get_me())
        FIFO = f"pipe_{hash_uid}"
        import errno
        try:
            os.mkfifo(FIFO)
        except OSError as oe:
            if oe.errno != errno.EEXIST:
                raise
        with open(FIFO, 'rb') as bytesin:
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
            uid = str(argv[2])
            download_block(hash_uid=uid)
            return 0
        elif service == 'upload':
            uid = str(argv[2])
            upload_block(hash_uid=uid)
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
