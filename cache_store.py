import os
import diskcache

_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
dc = diskcache.Cache(_CACHE_DIR)
