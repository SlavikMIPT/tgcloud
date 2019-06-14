# DedupFS: A deduplicating FUSE file system written in Python

The Python program [dedupfs.py](http://github.com/xolox/dedupfs/blob/master/dedupfs.py) implements a file system in user space using [FUSE](http://en.wikipedia.org/wiki/Filesystem_in_Userspace). It's called DedupFS because the file system's primary feature is [data deduplication](http://en.wikipedia.org/wiki/Data_deduplication), which enables it to store virtually unlimited copies of files because unchanged data is only stored once. In addition to deduplication the file system also supports transparent compression using the compression methods [lzo](http://en.wikipedia.org/wiki/LZO), [zlib](http://en.wikipedia.org/wiki/zlib) and [bz2](http://en.wikipedia.org/wiki/bz2). These properties make the file system ideal for backups: I'm currently storing 250 GB worth of backups using only 8 GB of disk space.

Several aspects of the design of DedupFS were inspired by [Venti](http://en.wikipedia.org/wiki/Venti) (ignoring the distributed aspect, for now…) and [ZFS](http://en.wikipedia.org/wiki/ZFS), though I've never personally used either. The [ArchiveFS](http://code.google.com/p/archivefs/) and [lessfs](http://www.lessfs.com/) projects share similar goals but have very different implementations.

## Usage

The following shell commands show how to install and use the DedupFS file system on [Ubuntu](http://www.ubuntu.com/) (where it was developed):

    $ sudo apt-get install python-fuse
    $ git clone git://github.com/xolox/dedupfs.git
    $ mkdir mount_point
    $ python dedupfs/dedupfs.py mount_point
    # Now copy some files to mount_point/ and observe that the size of the two
    # databases doesn't grow much when you copy duplicate files again :-)
    # The two databases are by default stored in the following locations:
    #  - ~/.dedupfs-metastore.sqlite3 contains the tree and meta data
    #  - ~/.dedupfs-datastore.db contains the (compressed) data blocks

## Status

Development on DedupFS began as a proof of concept to find out how much disk space the author could free by employing deduplication to store his daily backups. Since then it's become more or less usable as a way to archive old backups, i.e. for secondary storage deduplication. It's not recommended to use the file system for primary storage though, simply because the file system is too slow. I also wouldn't recommend depending on DedupFS just yet, at least until a proper set of automated tests has been written and successfully run to prove the correctness of the code (the tests are being worked on).

The file system initially stored everything in a single [SQLite](http://www.sqlite.org/) database, but it turned out that after the database grew beyond 8 GB the write speed would drop from 8-12 MB/s to 2-3 MB/s. Therefor the file system now stores its data blocks in a separate database, which is a persistent key/value store managed by a [dbm](http://en.wikipedia.org/wiki/dbm) implementation like [gdbm](http://www.gnu.org/software/gdbm/gdbm.html) or [Berkeley DB](http://en.wikipedia.org/wiki/Berkeley_DB).

### Limitations

In the current implementation a file's content needs to fit in a [cStringIO](http://docs.python.org/library/stringio.html#module-cStringIO) instance, which limits the maximum file size to your free RAM. Initially I implemented it this way because I was focusing on backups of web/mail servers, which don't contain files larger than 250 MB. Then I started copying virtual disk images and my file system blew up :-(. I know how to fix this but haven't implemented the change yet.

## Dependencies

DedupFS was developed using Python 2.6, though it might also work on earlier versions. It definitely doesn't work with Python 3 yet though. It requires the [Python FUSE binding](http://sourceforge.net/apps/mediawiki/fuse/index.php?title=FUSE_Python_tutorial) in addition to several Python standard libraries like [anydbm](http://docs.python.org/library/anydbm.html), [sqlite3](http://docs.python.org/library/sqlite3.html), [hashlib](http://docs.python.org/library/hashlib.html) and [cStringIO](http://docs.python.org/library/stringio.html#module-cStringIO).

## Contact

If you have questions, bug reports, suggestions, etc. the author can be contacted at <peter@peterodding.com>. The latest version of DedupFS is available at <http://peterodding.com/code/dedupfs/> and <http://github.com/xolox/dedupfs>.

## License

This software is licensed under the MIT license.  
© 2010 Peter Odding &lt;<peter@peterodding.com>&gt;.
