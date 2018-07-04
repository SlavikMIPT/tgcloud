import hashlib
import logging
import os
from io import BytesIO

from telethon.tl.custom import InputSizedFile
from telethon.tl.functions.upload import (
    SaveBigFilePartRequest, SaveFilePartRequest
)

try:
    import socks
except ImportError:
    socks = None

try:
    import hachoir
    import hachoir.metadata
    import hachoir.parser
except ImportError:
    hachoir = None
from telethon import helpers, utils
from telethon.tl.types import (InputFile, InputFileBig)

__log__ = logging.getLogger(__name__)
from telethon import TelegramClient
from threading import Thread
import random
import time
from queue import Queue
from telethon.network import ConnectionMode
from datetime import timedelta


class TelegramClientX(TelegramClient):
    def __init__(self, session, api_id, api_hash,
                 connection_mode=ConnectionMode.TCP_FULL,
                 use_ipv6=False,
                 proxy=None,
                 update_workers=None,
                 timeout=timedelta(seconds=10),
                 spawn_read_thread=True,
                 report_errors=True,
                 **kwargs):
        super().__init__(
            session, api_id, api_hash,
            connection_mode=connection_mode,
            use_ipv6=use_ipv6,
            proxy=proxy,
            update_workers=update_workers,
            spawn_read_thread=spawn_read_thread,
            timeout=timeout,
            report_errors=report_errors,
            **kwargs
        )

        self._event_builders = []
        self._events_pending_resolve = []

        # Some fields to easy signing in. Let {phone: hash} be
        # a dictionary because the user may change their mind.
        self._phone_code_hash = {}
        self._phone = None
        self._session_name = session
        self._upload_threads_count = 8
        # Sometimes we need to know who we are, cache the self peer
        self._self_input_peer = None

    class ProcessUpload(Thread):
        def __init__(self, name, client, q_request=None):
            Thread.__init__(self)
            self.name = name
            self.client = TelegramClient(client._session_name, client.api_id, client.api_hash, update_workers=None,
                                         spawn_read_thread=False)
            self.q_request = q_request
            self.result = None

        def run(self):
            print('Thread %s started' % self.name)
            time.sleep(random.randrange(200, 2000, 10) * 0.001)
            if not self.client.is_connected():
                self.client.connect()
            while True:
                request = self.q_request.get()
                if request is None:
                    break
                self.result = None
                # time.sleep(random.randrange(20, 100, 1) * 0.001)
                self.result = self.client.invoke(request)
                if self.result is False:
                    break
                self.q_request.task_done()
            self.client.disconnect()
            print('Thread {0} stopped result {1}'.format(self.name, self.result))
            return

    def set_upload_threads_count(self, count: int):
        self._upload_threads_count = int(count)

    def upload_file(self,
                    file,
                    part_size_kb=None,
                    file_name=None,
                    use_cache=None,
                    progress_callback=None):
        """
        Uploads the specified file and returns a handle (an instance of
        InputFile or InputFileBig, as required) which can be later used
        before it expires (they are usable during less than a day).

        Uploading a file will simply return a "handle" to the file stored
        remotely in the Telegram servers, which can be later used on. This
        will **not** upload the file to your own chat or any chat at all.

        Args:
            file (`str` | `bytes` | `file`):
                The path of the file, byte array, or stream that will be sent.
                Note that if a byte array or a stream is given, a filename
                or its type won't be inferred, and it will be sent as an
                "unnamed application/octet-stream".

                Subsequent calls with the very same file will result in
                immediate uploads, unless ``.clear_file_cache()`` is called.

            part_size_kb (`int`, optional):
                Chunk size when uploading files. The larger, the less
                requests will be made (up to 512KB maximum).

            file_name (`str`, optional):
                The file name which will be used on the resulting InputFile.
                If not specified, the name will be taken from the ``file``
                and if this is not a ``str``, it will be ``"unnamed"``.

            use_cache (`type`, optional):
                The type of cache to use (currently either ``InputDocument``
                or ``InputPhoto``). If present and the file is small enough
                to need the MD5, it will be checked against the database,
                and if a match is found, the upload won't be made. Instead,
                an instance of type ``use_cache`` will be returned.

            progress_callback (`callable`, optional):
                A callback function accepting two parameters:
                ``(sent bytes, total)``.

        Returns:
            :tl:`InputFileBig` if the file size is larger than 10MB,
            ``InputSizedFile`` (subclass of :tl:`InputFile`) otherwise.
        """
        if isinstance(file, (InputFile, InputFileBig)):
            return file  # Already uploaded

        if isinstance(file, str):
            file_size = os.path.getsize(file)
        elif isinstance(file, bytes):
            file_size = len(file)
        else:
            file = file.read()
            file_size = len(file)

        # File will now either be a string or bytes
        if not part_size_kb:
            part_size_kb = utils.get_appropriated_part_size(file_size)

        if part_size_kb > 512:
            raise ValueError('The part size must be less or equal to 512KB')

        part_size = int(part_size_kb * 1024)
        if part_size % 1024 != 0:
            raise ValueError(
                'The part size must be evenly divisible by 1024')

        # Set a default file name if None was specified
        file_id = helpers.generate_random_long()
        if not file_name:
            if isinstance(file, str):
                file_name = os.path.basename(file)
            else:
                file_name = str(file_id)

        # Determine whether the file is too big (over 10MB) or not
        # Telegram does make a distinction between smaller or larger files
        is_large = file_size > 10 * 1024 * 1024
        hash_md5 = hashlib.md5()
        if not is_large:
            # Calculate the MD5 hash before anything else.
            # As this needs to be done always for small files,
            # might as well do it before anything else and
            # check the cache.
            if isinstance(file, str):
                with open(file, 'rb') as stream:
                    file = stream.read()
            hash_md5.update(file)
            if use_cache:
                cached = self.session.get_file(
                    hash_md5.digest(), file_size, cls=use_cache
                )
                if cached:
                    return cached

        part_count = (file_size + part_size - 1) // part_size
        __log__.info('Uploading file of %d bytes in %d chunks of %d',
                     file_size, part_count, part_size)

        with open(file, 'rb') if isinstance(file, str) else BytesIO(file) as stream:
            threads_count = 2 + int((self._upload_threads_count - 2) * float(file_size) / 1024 * 1024 * 768)
            threads_count = min(threads_count, self._upload_threads_count)
            threads_count = min(part_count, threads_count)
            upload_thread = []
            q_request = Queue()
            # spawn threads
            for i in range(threads_count):
                thread_dl = self.ProcessUpload('thread {0}'.format(i), self, q_request)
                thread_dl.start()
                upload_thread.append(thread_dl)
            for part_index in range(0, part_count, threads_count):
                # Read the file by in chunks of size part_size
                for part_thread_index in range(threads_count):
                    if part_index + part_thread_index >= part_count:
                        break
                    part = stream.read(part_size)
                    # The SavePartRequest is different depending on whether
                    # the file is too large or not (over or less than 10MB)
                    if is_large:
                        request = SaveBigFilePartRequest(file_id, part_index + part_thread_index, part_count, part)
                    else:
                        request = SaveFilePartRequest(file_id, part_index + part_thread_index, part)
                    q_request.put(request)
                # q_request.join()
                job_completed = False
                while not job_completed:
                    for th in upload_thread:
                        if th:
                            if th.result is True:
                                job_completed = True
                                __log__.debug('Uploaded %d/%d', part_index + 1, part_count)
                                if progress_callback:
                                    progress_callback(stream.tell(), file_size)
                            elif th.result is False:
                                raise RuntimeError('Failed to upload file part {}.'.format(part_index))
            q_request.join()
            for i in range(threads_count):
                q_request.put(None)
            for th in upload_thread:
                th.join()
        if is_large:
            return InputFileBig(file_id, part_count, file_name)
        else:
            return InputSizedFile(
                file_id, part_count, file_name, md5=hash_md5, size=file_size
            )
