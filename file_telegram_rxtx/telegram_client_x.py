# TODO TEST TEST AND TEST THIS PROBABLY WON'T WORK/ HOWEVER WHY NOT
# NEWEST TELETHON 1.2

import asyncio
import hashlib
import io
import logging
import os
from io import BytesIO

import telethon.errors as errors
from telethon.crypto import CdnDecrypter
from telethon.tl import types, functions, custom

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

__log__ = logging.getLogger(__name__)
from telethon import TelegramClient
from threading import Thread
import random
import time
from datetime import timedelta


class TelegramClientX(TelegramClient):
    def __init__(self, session, api_id, api_hash,
                 use_ipv6=False,
                 proxy=None,
                 timeout=timedelta(seconds=10),
                 ):
        super().__init__(
            session, api_id, api_hash,
            use_ipv6=use_ipv6,
            proxy=proxy,
            timeout=timeout,
        )

        self._event_builders = []
        self._events_pending_resolve = []

        # Some fields to easy signing in. Let {phone: hash} be
        # a dictionary because the user may change their mind.
        self._phone_code_hash = {}
        self._phone = None
        self._session_name = session
        self._upload_threads_count = 8
        self._download_threads_count = 8
        # Sometimes we need to know who we are, cache the self peer
        self._self_input_peer = None

    class ProcessUpload:  # TODO fuck all threads
        name = None
        client = None
        q_request = None
        result = None

        async def init(self, name, client, q_request=None):
            self.name = name
            self.client = TelegramClient(client._session_name, client.api_id, client.api_hash)
            self.q_request = q_request
            self.result = None
        """
        def __init__(self, name, client, q_request=None):
            Thread.__init__()
            self.name = name
            self.client = TelegramClient(client._session_name, client.api_id, client.api_hash)
            self.q_request = q_request
            self.result = None
"""

        async def run(self):
            print('Async task %s started' % self.name)
            asyncio.sleep(random.choice([.001, 0.00001, .002]))
            if not self.client.is_connected():
                self.client.connect()
            while True:
                request = self.q_request.get()
                if request is None:
                    break
                self.result = None
                # time.sleep(random.randrange(20, 100, 1) * 0.001)
                self.result = await self.client(request)
                if self.result is False:
                    break
                self.q_request.task_done()
            self.client.disconnect()
            print('Task {0} stopped result {1}'.format(self.name, self.result))
            return

    def set_upload_threads_count(self, count: int):
        self._upload_threads_count = int(count)

    def set_download_threads_count(self, count: int):
        self._download_threads_count = int(count)

    async def upload_file(self,
                    file, *,
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
        if isinstance(file, (types.InputFile, types.InputFileBig)):
            return file  # Already uploaded

        if not file_name and getattr(file, 'name', None):
            file_name = file.name

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

        with open(file, 'rb') if isinstance(file, str) else BytesIO(file)\
                as stream:
            for part_index in range(part_count):
                # Read the file by in chunks of size part_size
                part = stream.read(part_size)

                # The SavePartRequest is different depending on whether
                # the file is too large or not (over or less than 10MB)
                if is_large:
                    request = functions.upload.SaveBigFilePartRequest(
                        file_id, part_index, part_count, part)
                else:
                    request = functions.upload.SaveFilePartRequest(
                        file_id, part_index, part)

                result = await self(request)
                if result:
                    __log__.debug('Uploaded %d/%d', part_index + 1,
                                  part_count)
                    if progress_callback:
                        progress_callback(stream.tell(), file_size)
                else:
                    raise RuntimeError(
                        'Failed to upload file part {}.'.format(part_index))

        if is_large:
            return types.InputFileBig(file_id, part_count, file_name)
        else:
            return custom.InputSizedFile(
                file_id, part_count, file_name, md5=hash_md5, size=file_size
            )

    class ProcessDownload(Thread):
        def __init__(self, name, client, q_request=None):
            Thread.__init__(self)
            self.name = name
            self.client = TelegramClient(client._session_name, client.api_id, client.api_hash)
            self.q_request = q_request
            self.result = None

        async def run(self):
            print('Task %s started' % self.name)
            time.sleep(random.randrange(200, 2000, 10) * 0.001)
            if not self.client.is_connected():
                self.client.connect()
            while True:
                request = self.q_request.get()
                if request is None:
                    break
                self.result = None
                # time.sleep(random.randrange(20, 100, 1) * 0.001)
                if isinstance(request, CdnDecrypter):
                    self.result = request.get_file()
                else:
                    self.result = self.client(request)
                if self.result is False:
                    break
                self.q_request.task_done()
            self.client.disconnect()
            print('Task {0} stopped result {1}'.format(self.name, self.result))
            return

    async def download_file(
            self, input_location, file=None, *, part_size_kb=None,
            file_size=None, progress_callback=None):
        """
        Downloads the given input location to a file.

        Args:
            input_location (:tl:`FileLocation` | :tl:`InputFileLocation`):
                The file location from which the file will be downloaded.
                See `telethon.utils.get_input_location` source for a complete
                list of supported types.

            file (`str` | `file`, optional):
                The output file path, directory, or stream-like object.
                If the path exists and is a file, it will be overwritten.

                If the file path is ``None``, then the result will be
                saved in memory and returned as `bytes`.

            part_size_kb (`int`, optional):
                Chunk size when downloading files. The larger, the less
                requests will be made (up to 512KB maximum).

            file_size (`int`, optional):
                The file size that is about to be downloaded, if known.
                Only used if ``progress_callback`` is specified.

            progress_callback (`callable`, optional):
                A callback function accepting two parameters:
                ``(downloaded bytes, total)``. Note that the
                ``total`` is the provided ``file_size``.
        """
        if not part_size_kb:
            if not file_size:
                part_size_kb = 64  # Reasonable default
            else:
                part_size_kb = utils.get_appropriated_part_size(file_size)

        part_size = int(part_size_kb * 1024)
        # https://core.telegram.org/api/files says:
        # > part_size % 1024 = 0 (divisible by 1KB)
        #
        # But https://core.telegram.org/cdn (more recent) says:
        # > limit must be divisible by 4096 bytes
        # So we just stick to the 4096 limit.
        if part_size % 4096 != 0:
            raise ValueError(
                'The part size must be evenly divisible by 4096.')

        in_memory = file is None
        if in_memory:
            f = io.BytesIO()
        elif isinstance(file, str):
            # Ensure that we'll be able to download the media
            helpers.ensure_parent_dir_exists(file)
            f = open(file, 'wb')
        else:
            f = file

        dc_id, input_location = utils.get_input_location(input_location)
        exported = dc_id and self.session.dc_id != dc_id
        if exported:
            try:
                sender = await self._borrow_exported_sender(dc_id)
            except errors.DcIdInvalidError:
                # Can't export a sender for the ID we are currently in
                config = await self(functions.help.GetConfigRequest())
                for option in config.dc_options:
                    if option.ip_address == self.session.server_address:
                        self.session.set_dc(
                            option.id, option.ip_address, option.port)
                        self.session.save()
                        break

                # TODO Figure out why the session may have the wrong DC ID
                sender = self._sender
                exported = False
        else:
            # The used sender will also change if ``FileMigrateError`` occurs
            sender = self._sender

        __log__.info('Downloading file in chunks of %d bytes', part_size)
        try:
            offset = 0
            while True:
                try:
                    result = await sender.send(functions.upload.GetFileRequest(
                        input_location, offset, part_size
                    ))
                    if isinstance(result, types.upload.FileCdnRedirect):
                        # TODO Implement
                        raise NotImplementedError
                except errors.FileMigrateError as e:
                    __log__.info('File lives in another DC')
                    sender = await self._borrow_exported_sender(e.new_dc)
                    exported = True
                    continue

                offset += part_size
                if not result.bytes:
                    if in_memory:
                        f.flush()
                        return f.getvalue()
                    else:
                        return getattr(result, 'type', '')

                __log__.debug('Saving %d more bytes', len(result.bytes))
                f.write(result.bytes)
                if progress_callback:
                    progress_callback(f.tell(), file_size)
        finally:
            if exported:
                await self._return_exported_sender(sender)
            elif sender != self._sender:
                await sender.disconnect()
            if isinstance(file, str) or in_memory:
                f.close()
