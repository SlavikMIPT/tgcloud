#!/usr/bin/python

"""
The function in this Python module determines the current memory usage of the
current process by reading the VmSize value from /proc/$pid/status. It's based
on the following entry in the Python cookbook:
http://code.activestate.com/recipes/286222/
"""

import os

_units = { 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3 }
_handle = _handle = open('/proc/%d/status' % os.getpid())

def get_memory_usage():
  global _proc_status, _units, _handle
  try:
    for line in _handle:
      if line.startswith('VmSize:'):
        label, count, unit = line.split()
        return int(count) * _units[unit.upper()]
  except:
    return 0
  finally:
    _handle.seek(0)

if __name__ == '__main__':
  from my_formats import format_size
  megabyte = 1024**2
  counter = megabyte
  limit = megabyte * 50
  memory = []
  old_memory_usage = get_memory_usage()
  assert old_memory_usage > 0
  while counter < limit:
    memory.append('a' * counter)
    msg = "I've just allocated %s and get_memory_usage() returns %s (%s more, deviation is %s)"
    new_memory_usage = get_memory_usage()
    difference = new_memory_usage - old_memory_usage
    deviation = max(difference, counter) - min(difference, counter)
    assert deviation < 1024*100
    print msg % (format_size(counter), format_size(new_memory_usage), format_size(difference), format_size(deviation))
    old_memory_usage = new_memory_usage
    counter += megabyte
  print "Stopped allocating new strings at %s" % format_size(limit)

# vim: ts=2 sw=2 et
