#!/usr/bin/python3
import shelve
import os
from subprocess import Popen, PIPE

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO
from io import BytesIO
from download_service import download_block, upload_block

import subprocess
import tempfile

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


def get_block_from_telegram(chat_id, digest):
    buf = tempfile.NamedTemporaryFile()
    process = Popen(["python3.6", "download_service.py", "download", str(chat_id), str(digest)], stdout=buf,shell=False)
    process.wait()
    buf.seek(0)
    block = buf.read()
    buf.close()
    return block

chat_id = 123
user_id = 123

file_id = 'a4ddb160d8a42a9379d6fbbd0cb72ff11efe9cb5'
# #upload
# buf = Buffer()
# with open('test.mp4','rb') as fp:
#     buf = fp.read()
# import hashlib
#
# hexdigest = hashlib.sha1(buf).hexdigest()
# process = Popen(["python3.6", "download_service.py", "upload", str(chat_id), str(hexdigest)], stdin=PIPE, bufsize=-1)
# process.stdin.write(buf)
# process.stdin.close()
# process.wait()
# #download
block = get_block_from_telegram(chat_id, file_id)
outfile = open('tempfile_read2.mp3','wb')
outfile.write(block)
outfile.close()


