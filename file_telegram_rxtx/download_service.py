#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

from __future__ import print_function
from __future__ import unicode_literals
import mimetypes
import os
import re
import shutil
import socket
import time

# from PIL import Image
# from moviepy.editor import *
# from moviepy.config import change_settings
# change_settings({"FFMPEG_BINARY": "ffmpeg"})
from rq import get_current_job
from telethon.tl.types import DocumentAttributeAudio
from telethon.tl.types import DocumentAttributeFilename
from telethon.tl.types import DocumentAttributeVideo

from file_telegram_rxtx.telegram_client_x import TelegramClientX
# from hachoir.metadata import extractMetadata
# from hachoir.parser import createParser
from tg_access import *

path_home = './'#os.path.abspath('.')
path_shared = './shared'
path_local = './local'
last_call_time = time.time()
last_call_time2 = time.time()
client = TelegramClientX(entity, api_id, api_hash, update_workers=None, spawn_read_thread=True)
client.set_upload_threads_count(24)
client.set_download_threads_count(8)
if not client.is_connected():
    client.connect()

if not client.is_user_authorized():
    client.send_code_request(phone)
    client.sign_in(phone, input('Enter code: '))


# client.get_entity('AudioTubeBot')
# client.get_entity('VideoTubeBot')
# client.get_entity('SlavikMIPT')

def on_download_progress(recv_bytes, total_bytes):
    global last_call_time
    if time.time() - last_call_time < 0.5:
        return 0
    last_call_time = time.time()
    job = get_current_job()
    job.meta['recv_bytes'] = recv_bytes
    job.meta['total_bytes'] = total_bytes
    job.save_meta()
    return 0


def on_upload_progress(send_bytes, total_bytes):
    global last_call_time2
    if time.time() - last_call_time2 < 0.5:
        return 0
    last_call_time2 = time.time()
    # print(send_bytes/total_bytes)
    job = get_current_job()
    job.meta['send_bytes'] = send_bytes
    job.meta['total_bytes'] = total_bytes
    job.save_meta()
    return 0


def download_big_file(chat_id: int, uid: str):
    tmpdir = str(uid)
    os.chdir(path_home)
    try:
        client.start()
        job = get_current_job()
        job.meta['handled_by'] = socket.gethostname()
        job.save_meta()
        print('Current job: %s' % (job.id))
        agent_entity = client.get_entity(int(chat_id))
        messages = client.get_messages(agent_entity, limit=20)
        for i in range(20):
            msg = messages[i]
            if msg.message == str(uid):
                try:
                    is_voice = msg.media.document.attributes[0].voice
                except Exception:
                    is_voice = False
                if is_voice:
                    cleaned_filename = str(uid) + '.ogg'
                else:
                    filename = msg.media.document.attributes[1].file_name
                    file_ext = filename[len(filename) - 4:]
                    file_title = filename[:-4]
                    reg = re.compile(r'[^a-zA-Z0-9_]')
                    cleaned_title = reg.sub('', file_title)
                    cleaned_title = re.sub(r' ', '_', cleaned_title,flags=re.UNICODE)
                    cleaned_filename = str(uid) + cleaned_title + file_ext
                    print(cleaned_filename)
                tmpdir_shared = os.path.join(path_shared, str(uid))
                tmpdir = os.path.join(path_local,str(uid))
                output_file_path = os.path.join(tmpdir, cleaned_filename)
                output_file_path_shared = os.path.join(tmpdir_shared, cleaned_filename)
                os.chdir(path_home)
                if not os.path.exists(tmpdir):
                    os.mkdir(tmpdir)
                client.download_media(msg, output_file_path, progress_callback=on_download_progress)
                while not os.path.exists(output_file_path_shared):
                    time.sleep(0.1)
                return output_file_path_shared
        return False
    except Exception:
        if os.path.exists(tmpdir):
            shutil.rmtree(tmpdir)
        raise Exception
    finally:
        client.disconnect()


def upload_file(chat_id: int, user_id: int, file_path: str, uid, title=None, performer=None, duration=None, t_thumb=0,
                is_gif=False):
    try:
        job = get_current_job()
        job.meta['handled_by'] = socket.gethostname()
        job.save_meta()
        mimetypes.add_type('audio/aac', '.aac')
        mimetypes.add_type('audio/ogg', '.ogg')
        filename = str(os.path.basename(file_path))
        print(filename)
        client.start()
        entity = client.get_entity(int(chat_id))
        if filename.endswith('.mp4'):
            clip = VideoFileClip(str(file_path))
            thumbnail_path = str(file_path)[:-4] + '.jpg'
            frame_path = str(file_path)[:-4] + 'f.jpg'
            if (not os.path.exists(thumbnail_path)) or (t_thumb != 0):
                t_thumb = float(t_thumb)
                t_thumb = t_thumb if clip.duration > t_thumb else clip.duration
                clip.save_frame(frame_path, t=t_thumb)
            else:
                os.rename(thumbnail_path, frame_path)
            im = Image.open(frame_path)
            thumb_w = clip.w
            thumb_h = clip.h
            if thumb_w >= thumb_h:
                thumb_w = 180
                thumb_h = int(thumb_h * thumb_w / clip.w)
            else:
                thumb_w = 102
                thumb_h = int(thumb_h * thumb_w / clip.w)
            im = im.resize((thumb_w, thumb_h))
            im.save(thumbnail_path, "JPEG")
            if t_thumb == 1.0:
                thumbnail_path = 'thumb_one.jpg'
            if is_gif:
                if int(clip.duration) > 120:
                    raise Exception
                gif_filename = str(file_path)[:-4] + 'gif.mp4'
                file_path = gif_filename
                clip.write_videofile(str(file_path), audio=False)
            document_attribute = [DocumentAttributeVideo(duration=int(clip.duration), w=clip.w, h=clip.h,
                                                         supports_streaming=True),
                                  DocumentAttributeFilename(filename)]

            client.send_file(entity,
                             str(file_path),
                             caption=str(str(user_id) + ':' + str(uid) + ':' + str(int(clip.duration)) + ':v'),
                             file_name=str(filename),
                             allow_cache=False,
                             part_size_kb=512,
                             thumb=str(thumbnail_path),
                             attributes=document_attribute,
                             progress_callback=on_upload_progress)
            return 'SUCCESS'
        else:
            print(duration)
            if title is None:
                title = str(filename[:-4])
            if performer is None:
                performer = ''
            document_attribute = [DocumentAttributeAudio(int(duration),
                                                         voice=False,
                                                         title=str(title),
                                                         performer=performer)]
            print(file_path, user_id, uid, duration)
            client.send_file(entity,
                             str(file_path),
                             caption=str(str(user_id) + ':' + str(uid) + ':' + str(duration)),
                             file_name=str(filename),
                             allow_cache=False,
                             part_size_kb=512,
                             attributes=document_attribute,
                             progress_callback=on_upload_progress)

            return 'SUCCESS'
    except Exception as e:
        print(e)
        if os.path.exists(os.path.dirname(file_path)):
            shutil.rmtree(os.path.dirname(file_path))
        raise Exception
    finally:
        client.disconnect()
        if os.path.exists(os.path.dirname(file_path)):
            shutil.rmtree(os.path.dirname(file_path))
# upload_file(48012045,48012045,'test2.mp4','4801204577235b9d06db52e7209086ebbc8',is_gif=False)
# download_big_file(507379365,'480120454934975b0fd66213758b53ab5f2ab3')
