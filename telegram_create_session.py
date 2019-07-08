#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

from __future__ import print_function
from __future__ import unicode_literals

from telethon.telegram_client import TelegramClient
from telegram_client_x import TelegramClientX
from secret import *

path_home = './'  # os.path.abspath('.')
client = TelegramClientX(entity, api_id, api_hash, update_workers=None, spawn_read_thread=True)
# client = TelegramClient(entity, api_id, api_hash, update_workers=None, spawn_read_thread=True)
client.set_upload_threads_count(24)  # 24
client.set_download_threads_count(24)  # 8

client.connect()

if not client.is_user_authorized():
    client.start()

client.disconnect()