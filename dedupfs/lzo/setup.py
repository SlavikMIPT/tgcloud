from distutils.core import setup, Extension

setup(name = "LZO", version = "1.0",
      ext_modules = [Extension("lzo", ["lzomodule.c"], libraries=['lzo2'])])
