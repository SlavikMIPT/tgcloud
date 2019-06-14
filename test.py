#!/usr/bin/python3
import shelve
import os
from subprocess import Popen, PIPE

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

import subprocess
import tempfile

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


chat_id = 709766994
user_id = 709766994

file_id = '012345678910abcdef'


def get_block_from_telegram(chat_id, digest):
    # path = download_block(chat_id=chat_id, uid=digest)
    # buf = open('tempfile2', 'wb')
    buf = tempfile.TemporaryFile()
    process = Popen(["python3.6", "download_service.py", "download", str(chat_id), str(digest)], stdout=buf, bufsize=-1,shell=False)
    process.wait()
    # buf.close()
    # buf = open('tempfile2', 'rb')
    buf.seek(0)
    block = buf.read()
    buf.close()
    return block

block = get_block_from_telegram(chat_id, file_id)
outfile = open('tempfile.mp3','wb')
outfile.write(block)
outfile.close()
buf = Buffer()
buf = b'12345678'
# with open('testfile.mp3','rb') as fp:
#     buf = fp.read()
#
process = Popen(["python3.6", "download_service.py", "upload", str(chat_id), str(file_id)], stdin=PIPE, bufsize=-1)
process.stdin.write(buf)
process.stdin.close()
process.wait()


# upload_block(string_to_upload=buf.buf.getvalue(), chat_id=chat_id, hash_uid=str(file_id))
# storage = shelve.open('./storage.db')
# object = get_block_from_telegram(chat_id, file_id)
#
# storage[file_id] = object
# print(storage[file_id])
