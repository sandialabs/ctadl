import logging


def debug(fmt, arg_fun, varargs=False):
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        args = arg_fun()
        if varargs:
            logging.debug(fmt, *args)
        else:
            logging.debug(fmt, args)
