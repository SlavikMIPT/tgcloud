#define BLOCK_SIZE (1024 * 128)

#include <python2.6/Python.h>
#include <lzo/lzo1x.h>
#include <stdio.h>

/* The following formula gives the worst possible compressed size. */
#define lzo1x_worst_compress(x) ((x) + ((x) / 16) + 64 + 3)

/* The size of and pointer to the shared buffer. */
static int block_size, buffer_size = 0;
static unsigned char *shared_buffer = NULL;

/* Don't store the size of compressed blocks in headers and trust the user to
 * configure the correct block size? */
static int omit_headers = 0;

/* Working memory required by LZO library, allocated on first use. */
static char *working_memory = NULL;

#define ADD_SIZE(p) (omit_headers ? (p) : ((p) + sizeof(int)))
#define SUB_SIZE(p) (omit_headers ? (p) : ((p) - sizeof(int)))

static unsigned char *
get_buffer(int length)
{
  if (omit_headers) {
    if (!shared_buffer)
      shared_buffer = malloc(buffer_size);
  } else if (!shared_buffer || buffer_size < length) {
    free(shared_buffer);
    shared_buffer = malloc(length);
    buffer_size = length;
  }
  return shared_buffer;
}

static PyObject *
set_block_size(PyObject *self, PyObject *args)
{
  int new_block_size;

  if (PyArg_ParseTuple(args, "i", &new_block_size)) {
    if (shared_buffer)
      free(shared_buffer);
    block_size = new_block_size;
    buffer_size = lzo1x_worst_compress(block_size);
    shared_buffer = malloc(buffer_size);
    omit_headers = 1;
  }

  Py_INCREF(Py_True);
  return Py_True;
}

static PyObject *
lzo_compress(PyObject *self, PyObject *args)
{
  const unsigned char *input;
  unsigned char *output;
  unsigned int inlen, status;
  lzo_uint outlen;

  /* Get the uncompressed string and its length. */
  if (!PyArg_ParseTuple(args, "s#", &input, &inlen))
    return NULL;

  /* Make sure never to touch unallocated memory. */
  if (omit_headers && inlen > block_size)
    return PyErr_Format(PyExc_ValueError, "The given input of %i bytes is larger than the configured block size of %i bytes!", block_size, inlen);

  /* Allocate the working memory on first use? */
  if (!working_memory && !(working_memory = malloc(LZO1X_999_MEM_COMPRESS)))
    return PyErr_NoMemory();

  /* Allocate the output buffer. */
  outlen = lzo1x_worst_compress(inlen);
  output = get_buffer(ADD_SIZE(outlen));
  if (!output)
    return PyErr_NoMemory();

  /* Store the input size in the header of the compressed block? */
  if (!omit_headers)
    *((int*)output) = inlen;

  /* Compress the input string. The default LZO compression function is
   * lzo1x_1_compress(). There's also variants like lzo1x_1_15_compress() which
   * is faster and lzo1x_999_compress() which achieves higher compression. */
  status = lzo1x_1_15_compress(input, inlen, ADD_SIZE(output), &outlen, working_memory);
  if (status != LZO_E_OK)
    return PyErr_Format(PyExc_Exception, "lzo_compress() failed with error code %i!", status);

  /* Return the compressed string. */
  return Py_BuildValue("s#", output, ADD_SIZE(outlen));
}

static PyObject *
lzo_decompress(PyObject *self, PyObject *args)
{
  const unsigned char *input;
  unsigned char *output;
  int inlen, outlen_expected = 0, status;
  lzo_uint outlen_actual;

  /* Get the compressed string and its length. */
  if (!PyArg_ParseTuple(args, "s#", &input, &inlen))
    return NULL;

  /* Get the length of the uncompressed string? */
  if (!omit_headers)
    outlen_expected = *((int*)input);

  /* Allocate the output buffer. */
  output = get_buffer(outlen_expected);
  if (!output)
    return PyErr_NoMemory();

  /* Decompress the compressed string. */
  status = lzo1x_decompress(ADD_SIZE(input), SUB_SIZE(inlen), output, &outlen_actual, NULL);
  if (status != LZO_E_OK)
    return PyErr_Format(PyExc_Exception, "lzo_decompress() failed with error code %i!", status);

  /* Verify the length of the uncompressed data? */
  if (!omit_headers && outlen_expected != outlen_actual)
    return PyErr_Format(PyExc_Exception, "The expected length (%i) doesn't match the actual uncompressed length (%i)!", outlen_expected, (int)outlen_actual);

  /* Return the decompressed string. */
  return Py_BuildValue("s#", output, (int)outlen_actual);
}

static PyMethodDef functions[] = {
  { "compress", lzo_compress, METH_VARARGS, "Compress a string using the LZO algorithm." },
  { "decompress", lzo_decompress, METH_VARARGS, "Decompress a string that was previously compressed using the compress() function of this same module." },
  { "set_block_size", set_block_size, METH_VARARGS, "Set the max. length of the strings you will be compressing and/or decompressing so that the LZO module can allocate a single buffer shared by all lzo.compress() and lzo.decompress() calls." },
  { NULL, NULL, 0, NULL }
};

PyMODINIT_FUNC
initlzo(void)
{
  int status;

  if ((status = lzo_init()) != LZO_E_OK)
    PyErr_Format(PyExc_Exception, "Failed to initialize the LZO library! (lzo_init() failed with error code %i)", status);
  else if (!Py_InitModule("lzo", functions))
    PyErr_Format(PyExc_Exception, "Failed to register module functions!");
}

/* vim: set ts=2 sw=2 et : */
