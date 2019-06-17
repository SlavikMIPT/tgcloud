#!/usr/bin/python

# Documentation. {{{1

"""
This Python script implements a file system in user space using FUSE. It's
called DedupFS because the file system's primary feature is deduplication,
which enables it to store virtually unlimited copies of files because data
is only stored once.

In addition to deduplication the file system also supports transparent
compression using any of the compression methods lzo, zlib and bz2.

These two properties make the file system ideal for backups: I'm currently
storing 250 GB worth of backups using only 8 GB of disk space.

The latest version is available at http://peterodding.com/code/dedupfs/

DedupFS is licensed under the MIT license.
Copyright 2010 Peter Odding <peter@peterodding.com>.
"""

# Imports. {{{1

# Check the Python version, warn the user if untested.
import sys
import subprocess
import os

flagone = True
if sys.version_info[:2] != (2, 6):
    msg = "Warning: DedupFS has only been tested on Python 2.6, while you're running Python %d.%d!\n"
    sys.stderr.write(msg % (sys.version_info[0], sys.version_info[1]))

# Try to load the required modules from Python's standard library.
try:
    from io import BytesIO
    import cStringIO
    import errno
    import hashlib
    import tempfile
    import logging
    import math
    import os
    import sqlite3
    import stat
    import time
    import traceback
except ImportError, e:
    msg = "Error: Failed to load one of the required Python modules! (%s)\n"
    sys.stderr.write(msg % str(e))
    sys.exit(1)

# Try to load the Python FUSE binding.
try:
    import fuse
except ImportError:
    sys.stderr.write("Error: The Python FUSE binding isn't installed!\n" + \
                     "If you're on Ubuntu try running `sudo apt-get install python-fuse'.\n")
    sys.exit(1)

# Local modules that are mostly useful for debugging.
from my_formats import format_size, format_timespan
from get_memory_usage import get_memory_usage

from subprocess import Popen, PIPE

# chat_id = 709766994
def main():  # {{{1
    """
    This function enables using dedupfs.py as a shell script that creates FUSE
    mount points. Execute "dedupfs -h" for a list of valid command line options.
    """

    dfs = DedupFS()

    # A short usage message with the command line options defined by dedupfs
    # itself (see the __init__() method of the DedupFS class) is automatically
    # printed by the following call when sys.argv contains -h or --help.
    fuse_opts = dfs.parse(['-o', 'use_ino,default_permissions,fsname=dedupfs'] + sys.argv[1:])

    dfs_opts = dfs.cmdline[0]
    if dfs_opts.print_stats:
        dfs.read_only = True
        dfs.fsinit(silent=True)
        dfs.report_disk_usage()
        dfs.fsdestroy(silent=True)

    # If the user didn't pass -h or --help and also didn't supply a mount point
    # as a positional argument, print the short usage message and exit (I don't
    # agree with the Python FUSE binding's default behavior, which is something
    # nonsensical like using the working directory as a mount point).
    elif dfs.fuse_args.mount_expected() and not fuse_opts.mountpoint:
        dfs.parse(['-h'])
    elif fuse_opts.mountpoint or not dfs.fuse_args.mount_expected():
        # Don't print all options unless the user passed -h or --help explicitly
        # because this listing includes the 20+ options defined by the Python FUSE
        # binding (which is kind of intimidating at first).
        dfs.main()


class DedupFS(fuse.Fuse):  # {{{1

    def __init__(self, *args, **kw):  # {{{2

        try:

            # Set the Python FUSE API version.
            fuse.fuse_python_api = (0, 2)

            # Initialize the FUSE binding's internal state.
            fuse.Fuse.__init__(self, *args, **kw)

            # Set some options required by the Python FUSE binding.
            self.flags = 0
            self.multithreaded = 0

            # Initialize instance attributes.
            self.block_size = 1024 * 1024 * 5
            self.buffers = {}
            self.bytes_read = 0
            self.bytes_written = 0
            self.cache_gc_last_run = time.time()
            self.cache_requests = 0
            self.cache_timeout = 60  # TODO Make this a command line option!
            self.cached_nodes = {}
            self.calls_log_filter = []
            self.datastore_file = '~/.dedupfs-datastore.db'
            self.fs_mounted_at = time.time()
            self.gc_enabled = True
            self.gc_hook_last_run = time.time()
            self.gc_interval = 60
            self.link_mode = stat.S_IFLNK | 0777
            self.memory_usage = 0
            self.metastore_file = '~/.dedupfs-metastore.sqlite3'
            self.opcount = 0
            self.read_only = False
            self.root_mode = stat.S_IFDIR | 0755
            self.time_spent_caching_nodes = 0
            self.time_spent_hashing = 0
            self.time_spent_interning = 0
            self.time_spent_querying_tree = 0
            self.time_spent_reading = 0
            self.time_spent_traversing_tree = 0
            self.time_spent_writing = 0
            self.time_spent_writing_blocks = 0
            self.__NODE_KEY_VALUE = 0
            self.__NODE_KEY_LAST_USED = 1

            # Initialize a Logger() object to handle logging.
            self.logger = logging.getLogger('dedupfs')
            self.logger.setLevel(logging.INFO)
            self.logger.addHandler(logging.StreamHandler(sys.stderr))

            # Register some custom command line options with the option parser.
            option_stored_in_db = " (this option is only useful when creating a new database, because your choice is stored in the database and can't be changed after that)"
            self.parser.set_conflict_handler('resolve')  # enable overriding the --help message.
            self.parser.add_option('-h', '--help', action='help',
                                   help="show this help message followed by the command line options defined by the Python FUSE binding and exit")
            self.parser.add_option('-v', '--verbose', action='count', dest='verbosity', default=0,
                                   help="increase verbosity")
            self.parser.add_option('--print-stats', dest='print_stats', action='store_true', default=False,
                                   help="print the total apparent size and the actual disk usage of the file system and exit")
            self.parser.add_option('--log-file', dest='log_file', help="specify log file location")
            self.parser.add_option('--metastore', dest='metastore', metavar='FILE', default=self.metastore_file,
                                   help="specify the location of the file in which metadata is stored")
            self.parser.add_option('--datastore', dest='datastore', metavar='FILE', default=self.datastore_file,
                                   help="specify the location of the file in which data blocks are stored")
            self.parser.add_option('--block-size', dest='block_size', metavar='BYTES', default=self.block_size,
                                   type='int', help="specify the maximum block size in bytes" + option_stored_in_db)
            self.parser.add_option('--no-transactions', dest='use_transactions', action='store_false', default=True,
                                   help="don't use transactions when making multiple related changes, this might make the file system faster or slower (?)")
            self.parser.add_option('--nosync', dest='synchronous', action='store_false', default=True,
                                   help="disable SQLite's normal synchronous behavior which guarantees that data is written to disk immediately, because it slows down the file system too much (this means you might lose data when the mount point isn't cleanly unmounted)")
            self.parser.add_option('--nogc', dest='gc_enabled', action='store_false', default=True,
                                   help="disable the periodic garbage collection because it degrades performance (only do this when you've got disk space to waste or you know that nothing will be be deleted from the file system, which means little to no garbage will be produced)")
            self.parser.add_option('--verify-writes', dest='verify_writes', action='store_true', default=False,
                                   help="after writing a new data block to the database, check that the block was written correctly by reading it back again and checking for differences")

            # Dynamically check for supported hashing algorithms.
            msg = "specify the hashing algorithm that will be used to recognize duplicate data blocks: one of %s" + option_stored_in_db
            hash_functions = filter(lambda m: m[0] != '_' and m != 'new', dir(hashlib))
            msg %= ', '.join('%r' % fun for fun in hash_functions)
            self.parser.add_option('--hash', dest='hash_function', metavar='FUNCTION', type='choice',
                                   choices=hash_functions, default='sha1', help=msg)

            # Dynamically check for supported compression methods.
            def noop(s):
                return s

            self.compressors = {'none': (noop, noop)}
            compression_methods = ['none']
            for modname in 'lzo', 'zlib', 'bz2':
                try:
                    module = __import__(modname)
                    if hasattr(module, 'compress') and hasattr(module, 'decompress'):
                        self.compressors[modname] = (module.compress, module.decompress)
                        compression_methods.append(modname)
                except ImportError:
                    pass
            msg = "enable compression of data blocks using one of the supported compression methods: one of %s" + option_stored_in_db
            msg %= ', '.join('%r' % mth for mth in compression_methods[1:])
            self.parser.add_option('--compress', dest='compression_method', metavar='METHOD', type='choice',
                                   choices=compression_methods, default='none', help=msg)

            # Dynamically check for profiling support.
            try:
                # Using __import__() here because of pyflakes.
                for p in 'cProfile', 'pstats': __import__(p)
                self.parser.add_option('--profile', action='store_true', default=False,
                                       help="use the Python modules cProfile and pstats to create a profile of time spent in various function calls and print out a table of the slowest functions at exit (of course this slows everything down but it can nevertheless give a good indication of the hot spots)")
            except ImportError:
                self.logger.warning("No profiling support available, --profile option disabled.")
                self.logger.warning("If you're on Ubuntu try `sudo apt-get install python-profiler'.")

        except Exception, e:
            self.__except_to_status('__init__', e)
            sys.exit(1)

    # FUSE API implementation: {{{2

    def access(self, path, flags):  # {{{3
        try:
            self.__log_call('access', 'access(%r, %o)', path, flags)
            inode = self.__path2keys(path)[1]
            if flags != os.F_OK and not self.__access(inode, flags):
                return -errno.EACCES
            return 0
        except Exception, e:
            return self.__except_to_status('access', e, errno.ENOENT)

    def chmod(self, path, mode):  # {{{3
        try:
            self.__log_call('chmod', 'chmod(%r, %o)', path, mode)
            if self.read_only: return -errno.EROFS
            inode = self.__path2keys(path)[1]
            self.conn.execute('UPDATE inodes SET mode = ? WHERE inode = ?', (mode, inode))
            self.__gc_hook()
            return 0
        except Exception, e:
            return self.__except_to_status('chmod', e, errno.EIO)

    def chown(self, path, uid, gid):  # {{{3
        try:
            self.__log_call('chown', 'chown(%r, %i, %i)', path, uid, gid)
            if self.read_only: return -errno.EROFS
            inode = self.__path2keys(path)[1]
            self.conn.execute('UPDATE inodes SET uid = ?, gid = ? WHERE inode = ?', (uid, gid, inode))
            self.__gc_hook()
            return 0
        except Exception, e:
            return self.__except_to_status('chown', e, errno.EIO)

    def create(self, path, flags, mode):  # {{{3
        try:
            self.__log_call('create', 'create(%r, %o, %o)', path, flags, mode)
            if self.read_only: return -errno.EROFS
            try:
                # If the file already exists, just open it.
                status = self.open(path, flags, nested=True)
            except OSError, e:
                if e.errno != errno.ENOENT: raise
                # Otherwise create a new file and open that.
                inode, parent_ino = self.__insert(path, mode, 0)
                status = self.open(path, flags, nested=True, inode=inode)
            self.__commit_changes()
            self.__gc_hook()
            return status
        except Exception, e:
            self.__rollback_changes()
            return self.__except_to_status('create', e, errno.EIO)

    def fsdestroy(self, silent=False):  # {{{3
        try:
            self.__log_call('fsdestroy', 'fsdestroy()')
            self.__collect_garbage()
            if not silent:
                self.__print_stats()
            if not self.read_only:
                self.logger.info("Committing outstanding changes to `%s'.", self.metastore_file)
                self.__dbmcall('sync')
                self.conn.commit()
            self.conn.close()
            self.__dbmcall('close')
            return 0
        except Exception, e:
            return self.__except_to_status('fsdestroy', e, errno.EIO)

    def fsinit(self, silent=False):  # {{{3
        try:
            # Process the custom command line options defined in __init__().
            options = self.cmdline[0]
            self.block_size = options.block_size
            self.compression_method = options.compression_method
            self.datastore_file = self.__check_data_file(options.datastore, silent)
            self.gc_enabled = options.gc_enabled
            self.hash_function = options.hash_function
            self.metastore_file = self.__check_data_file(options.metastore, silent)
            self.synchronous = options.synchronous
            self.use_transactions = options.use_transactions
            self.verify_writes = options.verify_writes
            # Initialize the logging and database subsystems.
            self.__init_logging(options)
            self.__log_call('fsinit', 'fsinit()')
            self.__setup_database_connections(silent)
            if not self.read_only:
                self.__init_metastore()
            self.__get_opts_from_db(options)
            # Make sure the hash function is (still) valid (since the database was created).
            if not hasattr(hashlib, self.hash_function):
                self.logger.critical("Error: The selected hash function %r doesn't exist!", self.hash_function)
                sys.exit(1)
            # Get a reference to the hash function.
            self.hash_function_impl = getattr(hashlib, self.hash_function)
            # Disable synchronous operation. This is supposed to make SQLite perform
            # MUCH better but it has to be enabled wit --nosync because you might
            # lose data when the file system isn't cleanly unmounted...
            if not self.synchronous and not self.read_only:
                self.logger.warning("Warning: Disabling synchronous operation, you might lose data..")
                self.conn.execute('PRAGMA synchronous = OFF')
            # Select the compression method (if any) after potentially reading the
            # configured block size that was used to create the database (see the
            # set_block_size() call).
            self.__select_compress_method(options, silent)
            return 0
        except Exception, e:
            self.__except_to_status('fsinit', e, errno.EIO)
            # Bug fix: Break the mount point when initialization failed with an
            # exception, because self.conn might not be valid, which results in
            # an internal error message for every FUSE API call...
            os._exit(1)

    def getattr(self, path):  # {{{3
        try:
            self.__log_call('getattr', 'getattr(%r)', path)
            inode = self.__path2keys(path)[1]
            query = 'SELECT inode, nlinks, mode, uid, gid, rdev, size, atime, mtime, ctime FROM inodes WHERE inode = ?'
            attrs = self.conn.execute(query, (inode,)).fetchone()
            result = Stat(st_ino=attrs[0],
                          st_nlink=attrs[1],
                          st_mode=attrs[2],
                          st_uid=attrs[3],
                          st_gid=attrs[4],
                          st_rdev=attrs[5],
                          st_size=attrs[6],
                          st_atime=attrs[7],
                          st_mtime=attrs[8],
                          st_ctime=attrs[9],
                          st_blksize=self.block_size,
                          st_blocks=attrs[6] / 512,
                          st_dev=0)
            self.logger.debug("getattr(%r) returning %s", path, result)
            return result
        except Exception, e:
            self.logger.debug("getattr(%r) returning ENOENT", path)
            return self.__except_to_status('getattr', e, errno.ENOENT)

    def link(self, target_path, link_path, nested=False):  # {{{3
        # From the link(2) manual page: "If link_path names a directory, link()
        # shall fail unless the process has appropriate privileges and the
        # implementation supports using link() on directories." ... :-)
        # However I've read that FUSE doesn't like multiple directory pathnames
        # with the same inode number (maybe because of internal caching based on
        # inode numbers?).
        try:
            self.__log_call('link', '%slink(%r -> %r)', nested and ' ' or '', target_path, link_path)
            if self.read_only: return -errno.EROFS
            target_ino = self.__path2keys(target_path)[1]
            link_parent, link_name = os.path.split(link_path)
            link_parent_id, link_parent_ino = self.__path2keys(link_parent)
            string_id = self.__intern(link_name)
            self.conn.execute('INSERT INTO tree (parent_id, name, inode) VALUES (?, ?, ?)',
                              (link_parent_id, string_id, target_ino))
            node_id = self.__fetchval('SELECT last_insert_rowid()')
            self.conn.execute('UPDATE inodes SET nlinks = nlinks + 1 WHERE inode = ?', (target_ino,))
            if self.__fetchval('SELECT mode FROM inodes WHERE inode = ?', target_ino) & stat.S_IFDIR:
                self.conn.execute('UPDATE inodes SET nlinks = nlinks + 1 WHERE inode = ?', (link_parent_ino,))
            self.__cache_set(link_path, (node_id, target_ino))
            self.__commit_changes(nested)
            self.__gc_hook(nested)
            return 0
        except Exception, e:
            self.__rollback_changes(nested)
            if nested: raise
            return self.__except_to_status('link', e, errno.EIO)

    def mkdir(self, path, mode):  # {{{3
        try:
            self.__log_call('mkdir', 'mkdir(%r, %o)', path, mode)
            if self.read_only: return -errno.EROFS
            inode, parent_ino = self.__insert(path, mode | stat.S_IFDIR, 1024 * 4)
            self.conn.execute('UPDATE inodes SET nlinks = nlinks + 1 WHERE inode = ?', (parent_ino,))
            self.__commit_changes()
            self.__gc_hook()
            return 0
        except Exception, e:
            self.__rollback_changes()
            return self.__except_to_status('mkdir', e, errno.EIO)

    def mknod(self, path, mode, rdev):  # {{{3
        try:
            self.__log_call('mknod', 'mknod(%r, %o)', path, mode)
            if self.read_only: return -errno.EROFS
            self.__insert(path, mode, 0, rdev)
            self.__commit_changes()
            self.__gc_hook()
            return 0
        except Exception, e:
            self.__rollback_changes()
            return self.__except_to_status('mknod', e, errno.EIO)

    def open(self, path, flags, nested=None, inode=None):  # {{{3
        try:
            self.__log_call('open', 'open(%r, %o)', path, flags)
            # Make sure the file exists?
            inode = inode or self.__path2keys(path)[1]
            # Make sure the file is readable and/or writable.
            access_flags = 0
            if flags & (os.O_RDONLY | os.O_RDWR): access_flags |= os.R_OK
            if flags & (os.O_WRONLY | os.O_RDWR): access_flags |= os.W_OK
            if not self.__access(inode, access_flags):
                return -errno.EACCES
            return 0
        except Exception, e:
            if nested: raise
            return self.__except_to_status('open', e, errno.ENOENT)

    def read(self, path, length, offset):  # {{{3
        try:
            self.__log_call('read', 'read(%r, %i, %i)', path, length, offset)
            start_time = time.time()
            buf = self.__get_file_buffer(path)
            buf.seek(offset)
            data = buf.read(length)
            self.time_spent_reading += time.time() - start_time
            self.bytes_read += len(data)
            return data
        except Exception, e:
            return self.__except_to_status('read', e, code=errno.EIO)

    def readdir(self, path, offset):  # {{{3
        # Bug fix: When you use the -o use_ino option, directory entries must have
        # an "ino" field, otherwise not a single directory entry will be listed!
        try:
            self.__log_call('readdir', 'readdir(%r, %i)', path, offset)
            node_id, inode = self.__path2keys(path)
            yield fuse.Direntry('.', ino=inode)
            yield fuse.Direntry('..')
            query = "SELECT t.inode, s.value FROM tree t, strings s WHERE t.parent_id = ? AND t.name = s.id"
            for inode, name in self.conn.execute(query, (node_id,)).fetchall():
                yield fuse.Direntry(str(name), ino=inode)
        except Exception, e:
            self.__except_to_status('readdir', e)

    def readlink(self, path):  # {{{3
        try:
            self.__log_call('readlink', 'readlink(%r)', path)
            inode = self.__path2keys(path)[1]
            query = 'SELECT target FROM links WHERE inode = ?'
            return str(self.__fetchval(query, inode))
        except Exception, e:
            return self.__except_to_status('readlink', e, errno.ENOENT)

    def release(self, path, flags):  # {{{3
        try:
            self.__log_call('release', 'release(%r, %o)', path, flags)
            # Flush the write buffer?!
            if path in self.buffers:
                buf = self.buffers[path]
                # Flush the write buffer?
                if buf.dirty:
                    # Record start time so we can calculate average write speed.
                    start_time = time.time()
                    # Make sure the file exists and get its inode number.
                    inode = self.__path2keys(path)[1]
                    # Save apparent file size before possibly compressing data.
                    apparent_size = len(buf)
                    # Split up that string in the configured block size, hash the
                    # resulting blocks and store any new blocks.
                    try:
                        self.__write_blocks(inode, buf, apparent_size)
                        self.__commit_changes()
                    except Exception, e:
                        self.__rollback_changes()
                        raise
                    # Record the number of bytes written and the elapsed time.
                    self.bytes_written += apparent_size
                    self.time_spent_writing += time.time() - start_time
                    self.__gc_hook()
                # Delete the buffer.
                buf.close()
                del self.buffers[path]
            return 0
        except Exception, e:
            return self.__except_to_status('release', e, errno.EIO)

    def rename(self, old_path, new_path):  # {{{3
        try:
            self.__log_call('rename', 'rename(%r -> %r)', old_path, new_path)
            if self.read_only: return -errno.EROFS
            # Try to remove the existing target path (if if exists).
            # NB: This also makes sure target directories are empty.
            try:
                self.__remove(new_path, check_empty=True)
            except OSError, e:
                # Ignore errno.ENOENT, re raise other exceptions.
                if e.errno != errno.ENOENT: raise
            # Link the new path to the same inode as the old path.
            self.link(old_path, new_path, nested=True)
            # Finally unlink the old path.
            self.unlink(old_path, nested=True)
            self.__commit_changes()
            self.__gc_hook()
            return 0
        except Exception, e:
            self.__rollback_changes()
            return self.__except_to_status('rename', e, errno.ENOENT)

    def rmdir(self, path):  # {{{3
        try:
            self.__log_call('rmdir', 'rmdir(%r)', path)
            if self.read_only: return -errno.EROFS
            self.__remove(path, check_empty=True)
            self.__commit_changes()
            return 0
        except Exception, e:
            self.__rollback_changes()
            return self.__except_to_status('rmdir', e, errno.ENOENT)

    def statfs(self):  # {{{3
        try:
            self.__log_call('statfs', 'statfs()')
            # Use os.statvfs() to report the host file system's storage capacity.
            host_fs = os.statvfs(self.metastore_file)
            return StatVFS(f_bavail=(host_fs.f_bsize * host_fs.f_bavail) / self.block_size,
                           # The total number of free blocks available to a non privileged process.
                           f_bfree=(host_fs.f_frsize * host_fs.f_bfree) / self.block_size,
                           # The total number of free blocks in the file system.
                           f_blocks=(host_fs.f_frsize * host_fs.f_blocks) / self.block_size,
                           # The total number of blocks in the file system in terms of f_frsize.
                           f_bsize=self.block_size,  # The file system block size in bytes.
                           f_favail=0,  # The number of free file serial numbers available to a non privileged process.
                           f_ffree=0,  # The total number of free file serial numbers.
                           f_files=0,  # The total number of file serial numbers.
                           f_flag=0,
                           # File system flags. Symbols are defined in the <sys/statvfs.h> header file to refer to bits in this field (see The f_flags field).
                           f_frsize=self.block_size,  # The fundamental file system block size in bytes.
                           f_namemax=4294967295)  # The maximum file name length in the file system. Some file systems may return the maximum value that can be stored in an unsigned long to indicate the file system has no maximum file name length. The maximum value that can be stored in an unsigned long is defined in <limits.h> as ULONG_MAX.
        except Exception, e:
            return self.__except_to_status('statfs', e, errno.EIO)

    def symlink(self, target_path, link_path):  # {{{3
        try:
            self.__log_call('symlink', 'symlink(%r -> %r)', link_path, target_path)
            if self.read_only: return -errno.EROFS
            # Create an inode to hold the symbolic link.
            inode, parent_ino = self.__insert(link_path, self.link_mode, len(target_path))
            # Save the symbolic link's target.
            self.conn.execute('INSERT INTO links (inode, target) VALUES (?, ?)', (inode, sqlite3.Binary(target_path)))
            self.__commit_changes()
            self.__gc_hook()
            return 0
        except Exception, e:
            self.__rollback_changes()
            return self.__except_to_status('symlink', e, errno.EIO)

    def truncate(self, path, size):  # {{{3
        try:
            self.__log_call('truncate', 'truncate(%r, %i)', path, size)
            if self.read_only: return -errno.EROFS
            inode = self.__path2keys(path)[1]
            last_block = size / self.block_size
            self.conn.execute('DELETE FROM "index" WHERE inode = ? AND block_nr > ?', (inode, last_block))
            self.conn.execute('UPDATE inodes SET size = ? WHERE inode = ?', (size, inode))
            self.__gc_hook()
            self.__commit_changes()
            return 0
        except Exception, e:
            self.__rollback_changes()
            return self.__except_to_status('truncate', e, errno.ENOENT)

    def unlink(self, path, nested=False):  # {{{3
        try:
            self.__log_call('unlink', '%sunlink(%r)', nested and ' ' or '', path)
            if self.read_only: return -errno.EROFS
            self.__remove(path)
            self.__commit_changes(nested)
        except Exception, e:
            self.__rollback_changes(nested)
            if nested: raise
            return self.__except_to_status('unlink', e, errno.ENOENT)

    def utime(self, path, times):  # {{{3
        try:
            self.__log_call('utime', 'utime(%r, %i, %i)', path, *times)
            if self.read_only: return -errno.EROFS
            inode = self.__path2keys(path)[1]
            atime, mtime = times
            self.conn.execute('UPDATE inodes SET atime = ?, mtime = ? WHERE inode = ?', (atime, mtime, inode))
            self.__gc_hook()
            return 0
        except Exception, e:
            return self.__except_to_status('utime', e, errno.ENOENT)

    def utimens(self, path, ts_acc, ts_mod):  # {{{3
        try:
            self.__log_call('utimens', 'utimens(%r, %i.%i, %i.%i)', path, ts_acc.tv_sec, ts_acc.tv_nsec, ts_mod.tv_sec,
                            ts_mod.tv_nsec)
            if self.read_only: return -errno.EROFS
            inode = self.__path2keys(path)[1]
            atime = ts_acc.tv_sec + (ts_acc.tv_nsec / 1000000.0)
            mtime = ts_mod.tv_sec + (ts_mod.tv_nsec / 1000000.0)
            self.conn.execute('UPDATE inodes SET atime = ?, mtime = ? WHERE inode = ?', (atime, mtime, inode))
            self.__gc_hook()
            return 0
        except Exception, e:
            return self.__except_to_status('utimens', e, errno.ENOENT)

    def write(self, path, data, offset):  # {{{3
        try:
            length = len(data)
            self.__log_call('write', 'write(%r, %i, %i)', path, offset, length)
            start_time = time.time()
            buf = self.__get_file_buffer(path)
            buf.seek(offset)
            buf.write(data)
            self.time_spent_writing += time.time() - start_time
            # self.bytes_written is incremented from release().
            return length
        except Exception, e:
            return self.__except_to_status('write', e, errno.EIO)

    # Miscellaneous methods: {{{2

    def __init_logging(self, options):  # {{{3
        # Configure logging of messages to a file.
        if options.log_file:
            handler = logging.StreamHandler(open(options.log_file, 'w'))
            self.logger.addHandler(handler)
        # Convert verbosity argument to logging level?
        if options.verbosity > 0:
            if options.verbosity <= 1:
                self.logger.setLevel(logging.INFO)
            elif options.verbosity <= 2:
                self.logger.setLevel(logging.DEBUG)
            else:
                self.logger.setLevel(logging.NOTSET)

    def __init_metastore(self):  # {{{3
        # Bug fix: At this point fuse.FuseGetContext() returns uid = 0 and gid = 0
        # which differs from the info returned in later calls. The simple fix is to
        # use Python's os.getuid() and os.getgid() library functions instead of
        # fuse.FuseGetContext().
        uid, gid = os.getuid(), os.getgid()
        t = self.__newctime()
        self.conn.executescript("""

      -- Create the required tables?
      CREATE TABLE IF NOT EXISTS tree (id INTEGER PRIMARY KEY, parent_id INTEGER, name INTEGER NOT NULL, inode INTEGER NOT NULL, UNIQUE (parent_id, name));
      CREATE TABLE IF NOT EXISTS strings (id INTEGER PRIMARY KEY, value BLOB NOT NULL UNIQUE);
      CREATE TABLE IF NOT EXISTS inodes (inode INTEGER PRIMARY KEY, nlinks INTEGER NOT NULL, mode INTEGER NOT NULL, uid INTEGER, gid INTEGER, rdev INTEGER, size INTEGER, atime INTEGER, mtime INTEGER, ctime INTEGER);
      CREATE TABLE IF NOT EXISTS links (inode INTEGER UNIQUE, target BLOB NOT NULL);
      CREATE TABLE IF NOT EXISTS hashes (id INTEGER PRIMARY KEY, hash BLOB NOT NULL UNIQUE);
      CREATE TABLE IF NOT EXISTS "index" (inode INTEGER, hash_id INTEGER, block_nr INTEGER, PRIMARY KEY (inode, hash_id, block_nr));
      CREATE TABLE IF NOT EXISTS options (name TEXT PRIMARY KEY, value TEXT NOT NULL);

      -- Create the root node of the file system?
      INSERT OR IGNORE INTO strings (id, value) VALUES (1, '');
      INSERT OR IGNORE INTO tree (id, parent_id, name, inode) VALUES (1, NULL, 1, 1);
      INSERT OR IGNORE INTO inodes (nlinks, mode, uid, gid, rdev, size, atime, mtime, ctime) VALUES (2, %i, %i, %i, 0, 1024*4, %f, %f, %f);

      -- Save the command line options used to initialize the database?
      INSERT OR IGNORE INTO options (name, value) VALUES ('synchronous', %i);
      INSERT OR IGNORE INTO options (name, value) VALUES ('block_size', %i);
      INSERT OR IGNORE INTO options (name, value) VALUES ('compression_method', %r);
      INSERT OR IGNORE INTO options (name, value) VALUES ('hash_function', %r);

    """ % (self.root_mode, uid, gid, t, t, t, self.synchronous and 1 or 0,
           self.block_size, self.compression_method, self.hash_function))

    def __setup_database_connections(self, silent):  # {{{3
        if not silent:
            self.logger.info("Using data files %r and %r.", self.metastore_file, self.datastore_file)
        # Open the key/value store containing the data blocks.
        if not os.path.exists(self.metastore_file):
            self.blocks = self.__open_datastore(True)
        else:
            from whichdb import whichdb
            created_by_gdbm = whichdb(self.metastore_file) == 'gdbm'
            self.blocks = self.__open_datastore(created_by_gdbm)
        # Open an SQLite database connection with manual transaction management.
        self.conn = sqlite3.connect(self.metastore_file, isolation_level=None)
        # Use the built in row factory to enable named attributes.
        self.conn.row_factory = sqlite3.Row
        # Return regular strings instead of Unicode objects.
        self.conn.text_factory = str
        # Don't bother releasing any locks since there's currently no point in
        # having concurrent reading/writing of the file system database.
        self.conn.execute('PRAGMA locking_mode = EXCLUSIVE')

    def __open_datastore(self, use_gdbm):
        # gdbm is preferred over other dbm implementations because it supports fast
        # vs. synchronous modes, however any other dedicated key/value store should
        # work just fine (albeit not as fast). Note though that existing key/value
        # stores are always accessed through the library that created them.
        mode = self.read_only and 'r' or 'c'
        if use_gdbm:
            try:
                import gdbm
                mode += self.synchronous and 's' or 'f'
                return gdbm.open(self.datastore_file, mode)
            except ImportError:
                pass
        import anydbm
        return anydbm.open(self.datastore_file, mode)

    def __dbmcall(self, fun):  # {{{3
        # I simply cannot find any freakin' documentation on the type of objects
        # returned by anydbm and gdbm, so cannot verify that any single method will
        # always be there, although most seem to...
        # if hasattr(self.blocks, fun):
        #     getattr(self.blocks, fun)()
        pass

    def __check_data_file(self, pathname, silent):  # {{{3
        pathname = os.path.expanduser(pathname)
        if os.access(pathname, os.F_OK):
            # If the datafile already exists make sure it's readable,
            # otherwise the file system would be completely unusable.
            if not os.access(pathname, os.R_OK):
                self.logger.critical("Error: Datafile %r exists but isn't readable!", pathname)
                os._exit(1)
            # Check and respect whether the datafile is writable (e.g. when it was
            # created by root but is currently being accessed by another user).
            if not os.access(pathname, os.W_OK):
                if not silent:
                    self.logger.warning("File %r exists but isn't writable! Switching to read only mode.", pathname)
                self.read_only = True
        return pathname

    def __log_call(self, fun, msg, *args):  # {{{3
        # To disable all __log_call() invocations:
        #  :%s/^\(\s\+\)\(self\.__log_call\)/\1#\2
        # To re enable them:
        #  :%s/^\(\s\+\)#\(self\.__log_call\)/\1\2
        if self.calls_log_filter == [] or fun in self.calls_log_filter:
            self.logger.debug(msg, *args)

    def __get_opts_from_db(self, options):  # {{{3
        for name, value in self.conn.execute('SELECT name, value FROM options'):
            if name == 'synchronous':
                self.synchronous = int(value) != 0
                # If the user passed --nosync, override the value stored in the database.
                if not options.synchronous:
                    self.synchronous = False
            elif name == 'block_size' and int(value) != self.block_size:
                self.logger.warning("Ignoring --block-size=%i argument, using previously chosen block size %i instead",
                                    self.block_size, int(value))
                self.block_size = int(value)
            elif name == 'compression_method' and value != self.compression_method:
                if self.compression_method != 'none':
                    self.logger.warning(
                        "Ignoring --compress=%s argument, using previously chosen compression method %r instead",
                        self.compression_method, value)
                self.compression_method = value
            elif name == 'hash_function' and value != self.hash_function:
                self.logger.warning("Ignoring --hash=%s argument, using previously chosen hash function %r instead",
                                    self.hash_function, value)
                self.hash_function = value

    def __select_compress_method(self, options, silent):  # {{{3
        valid_formats = self.compressors.keys()
        selected_format = self.compression_method.lower()
        if selected_format not in valid_formats:
            self.logger.warning("Invalid compression format `%s' selected!", selected_format)
            selected_format = 'none'
        if selected_format != 'none':
            if not silent:
                self.logger.debug("Using the %s compression method.", selected_format)
            # My custom LZO binding defines set_block_size() which enables
            # optimizations like preallocating a buffer that can be reused for
            # every call to compress() and decompress().
            if selected_format == 'lzo':
                module = __import__('lzo')
                if hasattr(module, 'set_block_size'):
                    module.set_block_size(self.block_size)
        self.compress, self.decompress = self.compressors[selected_format]

    def __write_blocks(self, inode, buf, apparent_size):  # {{{3
        start_time = time.time()
        # Delete existing index entries for file.
        self.conn.execute('DELETE FROM "index" WHERE inode = ?', (inode,))
        # Store any changed blocks and rebuild the file index.
        storage_size = len(buf)
        for block_nr in xrange(int(math.ceil(storage_size / float(self.block_size)))):
            buf.seek(self.block_size * block_nr, os.SEEK_SET)
            new_block = buf.read(self.block_size)
            digest = self.__hash(new_block)
            encoded_digest = digest.encode('hex')#sqlite3.Binary(digest)
            row = self.conn.execute('SELECT id FROM hashes WHERE hash = ?', (encoded_digest,)).fetchone()
            if row:
                hash_id = row[0]
                existing_block = self.decompress(self.__get_block_from_telegram(digest.encode('hex')))
                # Check for hash collisions.
                if new_block != existing_block:
                    # Found a hash collision: dump debugging info and exit.
                    dumpfile_collision = '/tmp/dedupfs-collision-%i' % time.time()
                    handle = open(dumpfile_collision, 'w')
                    handle.write('Content of existing block is %r.\n' % existing_block)
                    handle.write('Content of new block is %r.\n' % new_block)
                    handle.close()
                    self.logger.critical(
                        "Found a hash collision on block number %i of inode %i!\n" + \
                        "The existing block is %i bytes and hashes to %s.\n" + \
                        "The new block is %i bytes and hashes to %s.\n" + \
                        "Saved existing and conflicting data blocks to %r.",
                        block_nr, inode, len(existing_block), digest,
                        len(new_block), digest, dumpfile_collision)
                    os._exit(1)
                self.conn.execute('INSERT INTO "index" (inode, hash_id, block_nr) VALUES (?, ?, ?)',
                                  (inode, hash_id, block_nr))
            else:
                process = Popen(["python3.6", "download_service.py", "upload", digest.encode('hex')], stdin=PIPE,
                                bufsize=-1)
                process.stdin.write(self.compress(new_block))
                process.stdin.close()
                process.wait()

                # self.blocks[digest] = self.compress(new_block)
                self.conn.execute('INSERT INTO hashes (id, hash) VALUES (NULL, ?)', (encoded_digest,))
                self.conn.execute('INSERT INTO "index" (inode, hash_id, block_nr) VALUES (?, last_insert_rowid(), ?)',
                                  (inode, block_nr))
                # Check that the data was properly stored in the database?
                self.__verify_write(new_block, digest, block_nr, inode)
            block_nr += 1
        # Update file size and last modified time.
        self.conn.execute('UPDATE inodes SET size = ?, mtime = ? WHERE inode = ?',
                          (apparent_size, self.__newctime(), inode))
        self.time_spent_writing_blocks += time.time() - start_time

    def __insert(self, path, mode, size, rdev=0):  # {{{3
        parent, name = os.path.split(path)
        parent_id, parent_ino = self.__path2keys(parent)
        nlinks = mode & stat.S_IFDIR and 2 or 1
        t = self.__newctime()
        uid, gid = self.__getctx()
        self.conn.execute(
            'INSERT INTO inodes (nlinks, mode, uid, gid, rdev, size, atime, mtime, ctime) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (nlinks, mode, uid, gid, rdev, size, t, t, t))
        inode = self.__fetchval('SELECT last_insert_rowid()')
        string_id = self.__intern(name)
        self.conn.execute('INSERT INTO tree (parent_id, name, inode) VALUES (?, ?, ?)', (parent_id, string_id, inode))
        node_id = self.__fetchval('SELECT last_insert_rowid()')
        self.__cache_set(path, (node_id, inode))
        return inode, parent_ino

    def __intern(self, string):  # {{{3
        start_time = time.time()
        args = (sqlite3.Binary(string),)
        result = self.conn.execute('SELECT id FROM strings WHERE value = ?', args).fetchone()
        if not result:
            self.conn.execute('INSERT INTO strings (id, value) VALUES (NULL, ?)', args)
            result = self.conn.execute('SELECT last_insert_rowid()').fetchone()
        self.time_spent_interning += time.time() - start_time
        return int(result[0])

    def __remove(self, path, check_empty=False):  # {{{3
        node_id, inode = self.__path2keys(path)
        # Make sure directories are empty before deleting them to avoid orphaned inodes.
        query = """ SELECT COUNT(t.id) FROM tree t, inodes i WHERE
                t.parent_id = ? AND i.inode = t.inode AND i.nlinks > 0 """
        if check_empty and self.__fetchval(query, node_id) > 0:
            raise OSError, (errno.ENOTEMPTY, os.strerror(errno.ENOTEMPTY), path)
        self.__cache_set(path, None)
        self.conn.execute('DELETE FROM tree WHERE id = ?', (node_id,))
        self.conn.execute('UPDATE inodes SET nlinks = nlinks - 1 WHERE inode = ?', (inode,))
        # Inodes with nlinks = 0 are purged periodically from __collect_garbage() so
        # we don't have to do that here.
        if self.__fetchval('SELECT mode FROM inodes where inode = ?', inode) & stat.S_IFDIR:
            parent_id, parent_ino = self.__path2keys(os.path.split(path)[0])
            self.conn.execute('UPDATE inodes SET nlinks = nlinks - 1 WHERE inode = ?', (parent_ino,))

    def __verify_write(self, block, digest, block_nr, inode):  # {{{3
        if self.verify_writes:
            saved_value = self.decompress(self.__get_block_from_telegram(digest.encode('hex')))
            if saved_value != block:
                # The data block was corrupted when it was written or read.
                dumpfile_corruption = '/tmp/dedupfs-corruption-%i' % time.time()
                handle = open(dumpfile_corruption, 'w')
                handle.write('The content that should have been stored is %r.\n' % block)
                handle.write('The content that was retrieved from the database is %r.\n' % saved_value)
                handle.close()
                self.logger.critical(
                    "Failed to verify data with block number %i of inode %i!\n" + \
                    "Saved original and corrupted data blocks to %i.",
                    block_nr, inode, dumpfile_corruption)
                os._exit(1)

    def __access(self, inode, flags):  # {{{3
        # Check if the flags include writing while the database is read only.
        if self.read_only and flags & os.W_OK:
            return False
        # Get the path's mode, owner and group through the inode.
        query = 'SELECT mode, uid, gid FROM inodes WHERE inode = ?'
        attrs = self.conn.execute(query, (inode,)).fetchone()
        # Determine by whom the request is being made.
        uid, gid = self.__getctx()
        o = uid == attrs['uid']  # access by same user id?
        g = gid == attrs['gid'] and not o  # access by same group id?
        # Note: "and not o" added after experimenting with EXT4.
        w = not (o or g)  # anything else
        m = attrs['mode']
        # The essence of UNIX file permissions. Did I miss anything?! (Probably...)
        return (not (flags & os.R_OK) or ((o and (m & 0400)) or (g and (m & 0040)) or (w and (m & 0004)))) \
               and (not (flags & os.W_OK) or ((o and (m & 0200)) or (g and (m & 0020)) or (w and (m & 0002)))) \
               and (not (flags & os.X_OK) or ((o and (m & 0100)) or (g and (m & 0010)) or (w and (m & 0001))))

    def __path2keys(self, path):  # {{{3
        node_id, inode = 1, 1
        if path == '/':
            return node_id, inode
        start_time = time.time()
        node = self.cached_nodes
        parent_id = node_id
        for segment in self.__split_segments(path):
            if segment in node:
                node = node[segment]
                node[self.__NODE_KEY_LAST_USED] = start_time
                node_id, inode = node[self.__NODE_KEY_VALUE]
            else:
                query_start_time = time.time()
                query = 'SELECT t.id, t.inode FROM tree t, strings s WHERE t.parent_id = ? AND t.name = s.id AND s.value = ? LIMIT 1'
                result = self.conn.execute(query, (parent_id, sqlite3.Binary(segment))).fetchone()
                self.time_spent_querying_tree += time.time() - query_start_time
                if result == None:
                    self.__cache_check_gc()
                    self.time_spent_traversing_tree += time.time() - start_time
                    raise OSError, (errno.ENOENT, os.strerror(errno.ENOENT), path)
                node_id, inode = result
                new_node = {self.__NODE_KEY_VALUE: (node_id, inode), self.__NODE_KEY_LAST_USED: start_time}
                node[segment] = new_node
                node = new_node
            parent_id = node_id
        self.__cache_check_gc()
        self.time_spent_traversing_tree += time.time() - start_time
        return node_id, inode

    def __cache_set(self, key, value):  # {{{3
        segments = self.__split_segments(key)
        last_segment = segments.pop(-1)
        node = self.cached_nodes
        time_now = time.time()
        for segment in segments:
            # Check that the keys of the sub path have been cached.
            if segment not in node:
                self.time_spent_caching_nodes += time.time() - time_now
                return False
            # Resolve the next path segment.
            node = node[segment]
            # Update the last used time of the sub path.
            node[self.__NODE_KEY_LAST_USED] = time_now
        if not value:
            # Delete the path's keys.
            if last_segment in node:
                del node[last_segment]
        elif last_segment not in node:
            # Create the path's keys.
            node[last_segment] = {self.__NODE_KEY_VALUE: value, self.__NODE_KEY_LAST_USED: time_now}
        else:
            # Update the path's keys.
            node = node[last_segment]
            node[self.__NODE_KEY_VALUE] = value
            node[self.__NODE_KEY_LAST_USED] = time_now
        self.__cache_check_gc()
        self.time_spent_caching_nodes += time.time() - time_now
        return True

    def __cache_check_gc(self):  # {{{3
        self.cache_requests += 1
        if self.cache_requests >= 2500:
            time_now = time.time()
            if time_now - self.cache_gc_last_run >= self.cache_timeout:
                self.__cache_do_gc(self.cached_nodes, time_now)
                self.cache_gc_last_run = time_now
            self.cache_requests = 0

    def __cache_do_gc(self, node, time_now):  # {{{3
        for key in node.keys():
            child = node[key]
            if isinstance(child, dict):
                last_used = time_now - child[self.__NODE_KEY_LAST_USED]
                if last_used > self.cache_timeout:
                    del node[key]
                else:
                    self.__cache_do_gc(child, time_now)

    def __split_segments(self, key):  # {{{3
        return filter(None, key.split('/'))

    def __newctime(self):  # {{{3
        return time.time()

    def __getctx(self):  # {{{3
        c = fuse.FuseGetContext()
        return (c['uid'], c['gid'])

    def __hash(self, data):  # {{{3
        start_time = time.time()
        context = self.hash_function_impl()
        context.update(data)
        digest = context.digest()
        self.time_spent_hashing += time.time() - start_time
        return digest

    def __print_stats(self):  # {{{3
        self.logger.info('-' * 79)
        self.__report_memory_usage()
        self.__report_throughput()
        self.__report_timings()

    def __report_timings(self):  # {{{3
        if self.logger.isEnabledFor(logging.DEBUG):
            timings = [(self.time_spent_traversing_tree, 'Traversing the tree'),
                       (self.time_spent_caching_nodes, 'Caching tree nodes'),
                       (self.time_spent_interning, 'Interning path components'),
                       (self.time_spent_writing_blocks, 'Writing data blocks'),
                       (self.time_spent_hashing, 'Hashing data blocks'),
                       (self.time_spent_querying_tree, 'Querying the tree')]
            maxdescwidth = max([len(l) for t, l in timings]) + 3
            timings.sort(reverse=True)
            uptime = time.time() - self.fs_mounted_at
            printed_heading = False
            for timespan, description in timings:
                percentage = timespan / (uptime / 100)
                if percentage >= 1:
                    if not printed_heading:
                        self.logger.debug("Cumulative timings of slowest operations:")
                        printed_heading = True
                    self.logger.debug(
                        " - %-*s%s (%i%%)" % (maxdescwidth, description + ':', format_timespan(timespan), percentage))

    def report_disk_usage(self):  # {{{3
        disk_usage = self.__fetchval('PRAGMA page_size') * self.__fetchval('PRAGMA page_count')
        disk_usage += os.stat(self.datastore_file).st_size
        apparent_size = self.__fetchval('SELECT SUM(inodes.size) FROM tree, inodes WHERE tree.inode = inodes.inode')
        self.logger.info("The total apparent size is %s while the databases take up %s (that's %.2f%%).",
                         format_size(apparent_size), format_size(disk_usage), float(disk_usage) / (apparent_size / 100))

    def __report_memory_usage(self):  # {{{3
        memory_usage = get_memory_usage()
        msg = "Current memory usage is " + format_size(memory_usage)
        difference = abs(memory_usage - self.memory_usage)
        if self.memory_usage != 0 and difference:
            direction = self.memory_usage < memory_usage and 'up' or 'down'
            msg += " (%s by %s)" % (direction, format_size(difference))
        self.logger.info(msg + '.')
        self.memory_usage = memory_usage

    def __report_throughput(self, nbytes=None, nseconds=None, label=None):  # {{{3
        if nbytes == None:
            self.bytes_read, self.time_spent_reading = \
                self.__report_throughput(self.bytes_read, self.time_spent_reading, "read")
            self.bytes_written, self.time_spent_writing = \
                self.__report_throughput(self.bytes_written, self.time_spent_writing, "write")
        else:
            if nbytes > 0:
                average = format_size(nbytes / max(1, nseconds))
                self.logger.info("Average %s speed is %s/s.", label, average)
                # Decrease the influence of previous measurements over time?
                if nseconds > 60 and nbytes > 1024 ** 2:
                    return nbytes / 2, nseconds / 2
            return nbytes, nseconds

    def __report_top_blocks(self):  # {{{3
        query = """
      SELECT * FROM (
        SELECT *, COUNT(*) AS "count" FROM "index"
        GROUP BY hash_id ORDER BY "count" DESC
      ), hashes WHERE
        "count" > 1 AND
        hash_id = hashes.id
        LIMIT 10 """
        if self.logger.isEnabledFor(logging.DEBUG):
            printed_header = False
            for row in self.conn.execute(query):
                if not printed_header:
                    self.logger.debug("A listing of the most used blocks follows:")
                    printed_header = True
                msg = "Block #%s of %s has been used %i times: %r"
                preview = row['value']
                max_length = 60
                if len(preview) < max_length:
                    preview = str(preview)
                else:
                    preview = preview[0: max_length] + '...'
                nbytes = format_size(len(row['value']))
                self.logger.debug(msg, row['hash_id'], nbytes, row['count'], preview)

    def __gc_hook(self, nested=False):  # {{{3
        # Don't collect any garbage for nested calls.
        if not nested:
            # Don't call time.time() more than once every 500th FUSE call.
            self.opcount += 1
            if self.opcount % 500 == 0:
                # Every minute the other statistics are reported and garbage
                # collection is performed when it isn't disabled.
                if time.time() - self.gc_hook_last_run >= self.gc_interval:
                    self.__collect_garbage()
                    self.__print_stats()
                    self.gc_hook_last_run = time.time()

    def __collect_garbage(self):  # {{{3
        if self.gc_enabled and not self.read_only:
            start_time = time.time()
            self.logger.info("Performing garbage collection (this might take a while) ..")
            self.should_vacuum = False
            for method in self.__collect_strings, self.__collect_inodes, \
                          self.__collect_indices, self.__collect_blocks, self.__vacuum_metastore:
                sub_start_time = time.time()
                msg = method()
                if msg:
                    elapsed_time = time.time() - sub_start_time
                    self.logger.info(msg, format_timespan(elapsed_time))
            elapsed_time = time.time() - start_time
            self.logger.info("Finished garbage collection in %s.", format_timespan(elapsed_time))

    def __collect_strings(self):  # {{{4
        count = self.conn.execute('DELETE FROM strings WHERE id NOT IN (SELECT name FROM tree)').rowcount
        if count > 0:
            self.should_vacuum = True
            return "Cleaned up %i unused path segment%s in %%s." % (count, count != 1 and 's' or '')

    def __collect_inodes(self):  # {{{4
        count = self.conn.execute('DELETE FROM inodes WHERE nlinks = 0').rowcount
        if count > 0:
            self.should_vacuum = True
            return "Cleaned up %i unused inode%s in %%s." % (count, count != 1 and 's' or '')

    def __collect_indices(self):  # {{{4
        count = self.conn.execute('DELETE FROM "index" WHERE inode NOT IN (SELECT inode FROM inodes)').rowcount
        if count > 0:
            self.should_vacuum = True
            return "Cleaned up %i unused index entr%s in %%s." % (count, count != 1 and 'ies' or 'y')

    def __collect_blocks(self):  # {{{4
        should_reorganize = False
        for row in self.conn.execute('SELECT hash FROM hashes WHERE id NOT IN (SELECT hash_id FROM "index")'):
            # del self.blocks[str(row[0])]
            should_reorganize = True
        if should_reorganize:
            self.__dbmcall('reorganize')
        count = self.conn.execute('DELETE FROM hashes WHERE id NOT IN (SELECT hash_id FROM "index")').rowcount
        if count > 0:
            self.should_vacuum = True
            return "Cleaned up %i unused data block%s in %%s." % (count, count != 1 and 's' or '')

    def __vacuum_metastore(self):  # {{{4
        if self.should_vacuum:
            self.conn.execute('VACUUM')
            return "Vacuumed SQLite metadata store in %s."

    def __commit_changes(self, nested=False):  # {{{3
        if self.use_transactions and not nested:
            self.conn.commit()

    def __rollback_changes(self, nested=False):  # {{{3
        if self.use_transactions and not nested:
            self.logger.info('Rolling back changes')
            self.conn.rollback()

    def __get_block_from_telegram(self, digest):
        buf = tempfile.NamedTemporaryFile()
        process = Popen(["python3.6", "download_service.py", "download", str(digest)], stdout=buf,
                        bufsize=-1, shell=False)
        process.wait()
        buf.seek(0)
        block = buf.read()
        buf.close()
        return block

    def __get_file_buffer(self, path):  # {{{3
        if path in self.buffers:
            return self.buffers[path]
        else:
            buf = Buffer()
            inode = self.__path2keys(path)[1]

            query = """ SELECT h.hash FROM hashes h, "index" i
                  WHERE i.inode = ? AND h.id = i.hash_id
                  ORDER BY i.block_nr ASC """
            for row in self.conn.execute(query, (inode,)).fetchall():
                # TODO Make the file system more robust against failure by doing
                # something sensible when self.blocks.has_key(digest) is false.
                buf.write(self.decompress(self.__get_block_from_telegram(str(row[0]))))
            self.buffers[path] = buf
            return buf

    def __fetchval(self, query, *values):  # {{{3
        return self.conn.execute(query, values).fetchone()[0]

    def __except_to_status(self, method, exception, code=errno.ENOENT):  # {{{3
        # Don't report ENOENT raised from getattr().
        if method != 'getattr' or code != errno.ENOENT:
            sys.stderr.write('%s\n' % ('-' * 50))
            sys.stderr.write("Caught exception in %s(): %s\n" % (method, exception))
            traceback.print_exc(file=sys.stderr)
            sys.stderr.write('%s\n' % ('-' * 50))
            sys.stderr.write("Returning %i\n" % -code)
            sys.stderr.flush()
        # Convert the exception to a FUSE error code.
        if isinstance(exception, OSError):
            return -exception.errno
        else:
            return -code


class Buffer:  # {{{1

    """
    This class wraps cStringIO.StringIO with two additions: The __len__
    method and a dirty flag to determine whether a buffer has changed.
    """

    def __init__(self):
        self.buf = cStringIO.StringIO()
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


# Named tuples used to return complex objects to FUSE. {{{1

try:
    import collections

    Stat = collections.namedtuple('Stat', 'st_atime st_blksize st_blocks \
      st_ctime st_dev st_gid st_ino st_mode st_mtime st_nlink st_rdev \
      st_size st_uid')
    StatVFS = collections.namedtuple('StatVFS', 'f_bavail f_bfree f_blocks \
      f_bsize f_favail f_ffree f_files f_flag f_frsize f_namemax')
except ImportError:
    # Fall back to regular Python classes instead of named tuples.
    class __Struct:
        def __init__(self, **kw):
            for k, v in kw.iteritems():
                setattr(self, k, v)


    class Stat(__Struct):
        pass


    class StatVFS(__Struct):
        pass

# }}}1

if __name__ == '__main__':

    if '--profile' in sys.argv:
        sys.stderr.write("Enabling profiling..\n")
        import cProfile, pstats

        profile = '.dedupfs.cprofile-%i' % time.time()
        cProfile.run('main()', profile)
        sys.stderr.write("\n Profiling statistics:\n\n")
        s = pstats.Stats(profile)
        s.sort_stats('time')
        s.print_stats(0.1)
        os.unlink(profile)
    else:
        main()

# vim: ts=2 sw=2 et
