#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

from __future__ import print_function
from __future__ import unicode_literals

import os
import time

from telethon.tl.types import DocumentAttributeFilename

from secret import *
from telegram_client_x import TelegramClientX

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
def download_block(hash_uid, filename):
    try:
        hash_uid = str(hash_uid)
        os.chdir(path_home)

        entity = client.get_entity(client.get_me())
        messages = client.get_messages(entity, limit=1, search=hash_uid)
        for i in range(len(messages)):
            msg = messages[i]
            if msg.message == hash_uid:
                # FIFO = f"dpipe_{hash_uid}"
                # import errno
                # try:
                #     os.mkfifo(FIFO)
                # except OSError as oe:
                #     if oe.errno != errno.EEXIST:
                #         raise
                # outbuf = open(FIFO, "wb"):
                # os.unlink(FIFO)
                client.download_media(msg, file=filename, progress_callback=on_download_progress)
                # outbuf.flush()
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
        FIFO = f"upipe_{hash_uid}"
        import errno
        try:
            os.mkfifo(FIFO)
        except OSError as oe:
            if oe.errno != errno.EEXIST:
                raise
        messages = client.get_messages(entity, limit=1, search=hash_uid)
        with open(FIFO, 'rb') as bytesin:
            if messages:
                return 0
            message = client.send_file(entity,
                                       file=bytesin,
                                       caption=f'{hash_uid}',
                                       attributes=[DocumentAttributeFilename(f'{hash_uid}')],
                                       allow_cache=False,
                                       part_size_kb=512,
                                       force_document=True,
                                       progress_callback=on_upload_progress)
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
            filename = str(argv[3])
            download_block(hash_uid=uid, filename=filename)
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
