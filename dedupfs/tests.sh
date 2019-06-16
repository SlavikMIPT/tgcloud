#!/bin/bash

TIMESTAMP="`date +%s`"
ROOTDIR="/tmp/dedupfs-tests-$TIMESTAMP"
MOUNTPOINT="$ROOTDIR/mountpoint"
METASTORE="$ROOTDIR/metastore.sqlite3"
DATASTORE="$ROOTDIR/datastore.db"
WAITTIME=1
TESTNO=1

# Initialization. {{{1

FAIL () {
  FAIL_INTERNAL "$@"
  exit 1
}

MESSAGE () {
  tput bold
  echo "$@" >&2
  tput sgr0
}

FAIL_INTERNAL () {
  echo -ne '\033[31m' >&2
  MESSAGE "$@"
  echo -ne '\033[0m' >&2
}

CLEANUP () {
  DO_UNMOUNT
  if ! rm -R "$ROOTDIR"; then
    FAIL_INTERNAL "$0:$LINENO: Failed to delete temporary directory!"
  fi
}

# Create the root and mount directories.
mkdir -p "$MOUNTPOINT"
if [ ! -d "$MOUNTPOINT" ]; then
  FAIL "$0:$LINENO: Failed to create mount directory $MOUNTPOINT!"
  exit 1
fi

DO_MOUNT () {
  # Mount the file system using the two temporary databases.
  python dedupfs.py -fv "$@" "--metastore=$METASTORE" "--datastore=$DATASTORE" "$MOUNTPOINT" &
  # Wait a while before accessing the mount point, to
  # make sure the file system has been fully initialized.
  while true; do
    sleep $WAITTIME
    if mount | grep -q "$MOUNTPOINT"; then break; fi
  done
}

DO_UNMOUNT () {
  if mount | grep -q "$MOUNTPOINT"; then
    sleep $WAITTIME
    if ! fusermount -u "$MOUNTPOINT"; then
      FAIL_INTERNAL "$0:$LINENO: Failed to unmount the mount point?!"
    fi
    while true; do
      sleep $WAITTIME
      if ! mount | grep -q "$MOUNTPOINT"; then break; fi
    done
  fi
}

DO_MOUNT --verify-writes --compress=lzo

# Tests 1-8: Test hard link counts with mkdir(), rmdir() and rename(). {{{1

CHECK_NLINK () {
  NLINK=`ls -ld "$1" | awk '{print $2}'`
  [ $NLINK -eq $2 ] || FAIL "$0:$3: Expected link count of $1 to be $2, got $NLINK!"
}

FEEDBACK () {
  MESSAGE "Running test $1"
}

# Test 1: Check link count of file system root. {{{2

FEEDBACK $TESTNO
TESTNO=$[$TESTNO + 1]
CHECK_NLINK "$MOUNTPOINT" 2 $LINENO

# Test 2: Check link count of newly created file. {{{2

FEEDBACK $TESTNO
TESTNO=$[$TESTNO + 1]
FILE="$MOUNTPOINT/file_nlink_test"
touch "$FILE"
CHECK_NLINK "$FILE" 1 $LINENO
CHECK_NLINK "$MOUNTPOINT" 2 $LINENO

# Test 3: Check link count of hard link to existing file. {{{2

FEEDBACK $TESTNO
TESTNO=$[$TESTNO + 1]

LINK="$MOUNTPOINT/link_to_file"
link "$FILE" "$LINK"
CHECK_NLINK "$FILE" 2 $LINENO
CHECK_NLINK "$LINK" 2 $LINENO
CHECK_NLINK "$MOUNTPOINT" 2 $LINENO
unlink "$LINK"
CHECK_NLINK "$FILE" 2 $LINENO
CHECK_NLINK "$MOUNTPOINT" 2 $LINENO

# Test 4: Check link count of newly created subdirectory. {{{2

FEEDBACK $TESTNO
TESTNO=$[$TESTNO + 1]

SUBDIR="$MOUNTPOINT/dir1"
mkdir "$SUBDIR"
if [ ! -d "$SUBDIR" ]; then
  FAIL "$0:$LINENO: Failed to create subdirectory $SUBDIR!"
fi

CHECK_NLINK "$SUBDIR" 2 $LINENO

# Test 5: Check that nlink of root is incremented by one (because of subdirectory created above). {{{2

FEEDBACK $TESTNO
TESTNO=$[$TESTNO + 1]

CHECK_NLINK "$MOUNTPOINT" 3 $LINENO

# Test 6: Check that non-empty directories cannot be removed with rmdir(). {{{2

FEEDBACK $TESTNO
TESTNO=$[$TESTNO + 1]

SUBFILE="$SUBDIR/file"
touch "$SUBFILE"
if rmdir "$SUBDIR" 2>/dev/null; then
  FAIL "$0:$LINENO: rmdir() didn't fail when deleting a non-empty directory!"
elif ! rm -R "$SUBDIR"; then
  FAIL "$0:$LINENO: Failed to recursively delete directory?!"
fi

# Test 7: Check that link count of root is decremented by one (because of subdirectory deleted above). {{{2

FEEDBACK $TESTNO
TESTNO=$[$TESTNO + 1]

CHECK_NLINK "$MOUNTPOINT" 2 $LINENO

# Test 8: Check that link counts are updated when directories are renamed. {{{2

FEEDBACK $TESTNO
TESTNO=$[$TESTNO + 1]

ORIGDIR="$MOUNTPOINT/original-directory"
REPLDIR="$MOUNTPOINT/replacement-directory"
mkdir  -p "$ORIGDIR/subdir" "$REPLDIR/subdir"
for DIRNAME in "$ORIGDIR" "$REPLDIR"; do CHECK_NLINK "$DIRNAME" 3 $LINENO; done
mv -T "$ORIGDIR/subdir" "$REPLDIR/subdir"
CHECK_NLINK "$ORIGDIR" 2 $LINENO
CHECK_NLINK "$REPLDIR" 3 $LINENO

# Tests 9-14: Write random binary data to file system and verify that it reads back unchanged. {{{1

TESTDATA="$ROOTDIR/testdata"

WRITE_TESTNO=0
while [ $WRITE_TESTNO -le 5 ]; do
  FEEDBACK $TESTNO
  TESTNO=$[$TESTNO + 1]
  NBYTES=$[$RANDOM % (1024 * 257)]
  head -c $NBYTES /dev/urandom > "$TESTDATA"
  WRITE_FILE="$MOUNTPOINT/$RANDOM"
  cp -a "$TESTDATA" "$WRITE_FILE"
  sleep $WAITTIME
  if ! cmp -s "$TESTDATA" "$WRITE_FILE"; then
    (sleep 1
     echo "Differences:"
     ls -l "$TESTDATA" "$WRITE_FILE"
     cmp -lb "$TESTDATA" "$WRITE_FILE") &
    FAIL "$0:$LINENO: Failed to verify $WRITE_FILE of $NBYTES bytes!"
  fi
  WRITE_TESTNO=$[$WRITE_TESTNO + 1]
done

# Test 15: Verify that written data persists when remounted. {{{1

FEEDBACK $TESTNO
TESTNO=$[$TESTNO + 1]

DO_UNMOUNT
DO_MOUNT --nogc # <- important for the following tests.
if ! cmp -s "$TESTDATA" "$WRITE_FILE"; then
  (sleep 1
   echo "Differences:"
   ls -l "$TESTDATA" "$WRITE_FILE"
   cmp -lb "$TESTDATA" "$WRITE_FILE") &
  FAIL "$0:$LINENO: Failed to verify $WRITE_FILE of $NBYTES bytes!"
fi

# Test 16: Verify that garbage collection of unused data blocks works. {{{1

FEEDBACK $TESTNO
TESTNO=$[$TESTNO + 1]

DO_UNMOUNT
FULL_SIZE=`ls -l "$DATASTORE" | awk '{print $5}'`
HALF_SIZE=$[$FULL_SIZE / 2]
DO_MOUNT
rm $MOUNTPOINT/* 2>/dev/null
DO_UNMOUNT
REDUCED_SIZE=`ls -l "$DATASTORE" | awk '{print $5}'`
[ $REDUCED_SIZE -lt $HALF_SIZE ] || FAIL "$0:$LINENO: Failed to verify effectiveness of data block garbage collection! (Full size of data store: $FULL_SIZE, reduced size: $REDUCED_SIZE)"

# Test 17: Verify that garbage collection of interned path segments works. {{{1

DO_MOUNT --nosync
SEGMENTGCDIR="$MOUNTPOINT/gc-of-segments-test"
mkdir "$SEGMENTGCDIR"
for ((i=0;i<=512;i+=1)); do
  echo -ne "\rCreating segment $i"
  touch "$SEGMENTGCDIR/$i"
done
echo -ne "\rSyncing to disk using unmount"
DO_UNMOUNT
FULL_SIZE=`ls -l "$METASTORE" | awk '{print $5}'`
HALF_SIZE=$[$FULL_SIZE / 2]
echo -ne "\rDeleting segments"
DO_MOUNT --nosync
rm -R "$SEGMENTGCDIR"
echo -ne "\rSyncing to disk using unmount"
DO_UNMOUNT
REDUCED_SIZE=`ls -l "$METASTORE" | awk '{print $5}'`
[ $REDUCED_SIZE -lt $HALF_SIZE ] || FAIL "$0:$LINENO: Failed to verify effectiveness of interned string garbage collection! (Full size of metadata store: $FULL_SIZE, reduced size: $REDUCED_SIZE)"
echo -ne "\r"

# Finalization. {{{1

CLEANUP
MESSAGE "All tests passed!"

# vim: ts=2 sw=2 et
