import cPickle
import functools


def memoize(obj):
    cache = obj.cache = {}

    @functools.wraps(obj)
    def memoizer(*args, **kwargs):
        key = Pickle.dumps((args, kwargs))
        if key not in cache:
            cache[key] = obj(*args, **kwargs)
        return cache[key]
    return memoizer
