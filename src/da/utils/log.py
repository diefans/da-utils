import os
import logging
import inspect
import time
from functools import wraps
from itertools import count
from traceback import format_exc

import blessings

callid = count()
pid = os.getpid()
trace_log = logging.getLogger('da.log.trace')

if trace_log.getEffectiveLevel() <= logging.DEBUG:
    logged_log_func = trace_log.debug
    logged_debug = True
else:
    logged_debug = False
    logged_log_func = trace_log.info


MAXLEN = 120

t = blessings.Terminal()


class MangleStr(object):
    __slots__ = ['f']

    def __init__(self, f):
        self.f = f

    def __repr__(self):
        s = repr(self.f).split('\n')[0]
        if len(s) > MAXLEN:
            s = s[:MAXLEN] + "..."
        return s


def optional_args_decorator(func):
    """
    Allow to use decorator either with arguments or not.

    @see http://wiki.python.org/moin/PythonDecoratorLibrary#Creating_decorator_with_optional_arguments
    """

    def isFuncArg(*args, **kw):
        return len(args) == 1 and len(kw) == 0 and (
            inspect.isfunction(args[0]) or isinstance(args[0], type))

    if isinstance(func, type):
        def class_wrapper(*args, **kw):
            if isFuncArg(*args, **kw):
                return func()(*args, **kw)      # create class before usage
            return func(*args, **kw)
        class_wrapper.__name__ = func.__name__
        class_wrapper.__module__ = func.__module__
        return class_wrapper

    @wraps(func)
    def func_wrapper(*args, **kw):
        if isFuncArg(*args, **kw):
            return func(*args, **kw)

        def functor(userFunc):
            return func(userFunc, *args, **kw)

        return functor

    return func_wrapper


@optional_args_decorator
def logged(func, ignore_exceptions=()):
    """
    :param func: the wrapped function - see optional_args_decorator
    :param ignore_exceptions: these exceptions are expected to be thrown and we omit logging them
    """
    @wraps(func)
    def decorated_function(*args, **kw):
        c = callid.next()

        threadname = pid
        if logged_debug:
            logged_log_func("{t.yellow}[%s-%s] Calling %s(%s,%s){t.normal}".format(t=t),
                            threadname, c, func.__name__, args, kw)
        else:
            logged_log_func("{t.yellow}[%s-%s] Calling %s(%s){t.normal}".format(t=t),
                            threadname, c, func.__name__, [MangleStr(a) for a in args])
        try:
            start = time.time()
            res = func(*args, **kw)
            stop = time.time()
            if logged_debug:
                logged_log_func("{t.yellow}[%s-%s] Call to %s done. Took %2.4fs. Returning: %s{t.normal}".format(t=t),
                                threadname, c, func.__name__, stop - start, res)
            else:
                logged_log_func("{t.yellow}[%s-%s] Call to %s done. Took %2.4fs.{t.normal}".format(t=t),
                                threadname, c, func.__name__, stop - start)
            return res
        except ignore_exceptions:
            # if we want to prevent logging exceptions, which are caught outside of logged
            raise
        except Exception:
            stop = time.time()
            logged_log_func("{t.yellow}[%s-%s] Call to %s FAILED. Took %2.4fs.{t.normal}".format(t=t),
                            threadname, c, func.__name__, stop - start)
            trace_log.error("{t.red}[%s-%s] %s failure: %s{t.normal}".format(t=t),
                            threadname, c, func.__name__, format_exc())
            raise
    return decorated_function
