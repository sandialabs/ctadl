import contextlib
import sys
from collections.abc import MutableSet
from dataclasses import dataclass
from itertools import filterfalse, islice, tee
from typing import Generic, Optional, TypeVar


def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = tee(iterable)
    next(b, None)
    return zip(a, b)


def delegate(to, *methods):
    """
    Decorate a class to create methods `methods` that delegate to the `to`
    instance variable
    """

    def dec(klass):
        def create_delegator(method):
            def delegator(self, *args, **kwargs):
                obj = getattr(self, to)
                m = getattr(obj, method)
                return m(*args, **kwargs)

            return delegator

        for m in methods:
            setattr(klass, m, create_delegator(m))
        return klass

    return dec


# Taken from the python impl of columnize
def columnize_list(list, displaywidth=80) -> list[str]:
    size = len(list)
    if size == 1:
        return list
    # Try every row count from 1 upwards
    for nrows in range(1, len(list)):
        ncols = (size + nrows - 1) // nrows
        colwidths = []
        totwidth = -2
        for col in range(ncols):
            colwidth = 0
            for row in range(nrows):
                i = row + nrows * col
                if i >= size:
                    break
                x = list[i]
                colwidth = max(colwidth, len(x))
            colwidths.append(colwidth)
            totwidth += colwidth + 2
            if totwidth > displaywidth:
                break
        if totwidth <= displaywidth:
            break
    else:
        nrows = len(list)
        ncols = 1
        colwidths = [0]
    output = []
    for row in range(nrows):
        texts = []
        for col in range(ncols):
            i = row + nrows * col
            if i >= size:
                x = ""
            else:
                x = list[i]
            texts.append(x)
        while texts and not texts[-1]:
            del texts[-1]
        for col in range(len(texts)):
            texts[col] = texts[col].ljust(colwidths[col])
        output.append("  ".join(texts))
    return output


@dataclass
class NounInfo:
    singular: str
    plural: Optional[str] = None
    article: str = "a"

    def __post_init__(self):
        if self.plural is None:
            self.plural = self.singular + "s"

    def print(self, n):
        if n == 1:
            return f"{self.article} {self.singular}"
        else:
            return f"{n} {self.plural}"


plurals = {}

for noun in [
    NounInfo("vertex", plural="vertexes"),
    NounInfo("error", article="an"),
]:
    plurals[noun.singular] = noun


def pluralize(n, singular):
    return plurals.get(singular, NounInfo(singular)).print(n)


OrderedSetT = TypeVar("OrderedSetT")


class OrderedSet(Generic[OrderedSetT], MutableSet[OrderedSetT]):
    """
    A set with ordered iteration order
    """

    def __init__(self, *args):
        self.data = set(*args)

    def __iter__(self):
        yield from sorted(self.data)

    def __contains__(self, x):
        return x in self.data

    def __len__(self):
        return len(self.data)

    def update(self, other):
        return self.data.update(other)

    def add(self, x):  # pyright: ignore[reportIncompatibleMethodOverride]
        return self.data.add(x)

    def __add__(self, x):
        res = OrderedSet(self)
        res.update(x)
        return res

    def discard(self, x):  # pyright: ignore[reportIncompatibleMethodOverride]
        return self.data.discard(x)


DictKey = TypeVar("DictKey")
DictValue = TypeVar("DictValue")


class Dict(Generic[DictKey, DictValue], dict[DictKey, DictValue]):
    """dict that errors if you try to overwrite an entry"""

    def __setitem__(self, k, v):
        try:
            self.__getitem__(k)
            raise ValueError(f"duplicate key '{k}'. value: '{self[k]}'")
        except KeyError:
            super(Dict, self).__setitem__(k, v)


def take(n, iterable):
    "Return first n items of the iterable as a list"
    return list(islice(iterable, n))


def takewhile(predicate, iterable):
    # takewhile(lambda x: x<5, [1,4,6,3,8]) → 1 4
    for x in iterable:
        if not predicate(x):
            break
        yield x


def partition(pred, iterable):
    "Use a predicate to partition entries into false entries and true entries"
    # partition(is_odd, range(10)) --> 0 2 4 6 8   and  1 3 5 7 9
    t1, t2 = tee(iterable)
    return filterfalse(pred, t1), filter(pred, t2)


def option_map(x, f, default=None):
    """Transforms a value if it is not None"""
    return f(x) if x is not None else default


def writer(filename, mode="w"):
    """
    An open()-style call that supports using '-' for stdout.

    with writer(filename) as fp:
        ...
    """

    @contextlib.contextmanager
    def stdout():
        yield sys.stdout

    return open(filename, mode) if filename != "-" else stdout()


class Gensym:
    def __init__(self):
        self._n = 0

    def next(self):
        ret = self._n
        self._n += 1
        return ret

    def __call__(self, seed: str = "sym"):
        return f"{seed}{self.next()}"


class CleanDict(dict):
    """A dictionary that removes entries whose value is None. This is useful
    when writing code that emits JSON. The code can be written by querying a
    database where some columns might be None and setting every supported key
    to values obtained from the database. Any None values will simply be
    removed from the resulting dictionary."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._remove_none_values()

    def __setitem__(self, key, value):
        if value is None:
            if key in self:
                super().__delitem__(key)
        else:
            super().__setitem__(key, value)

    def _remove_none_values(self):
        """Remove keys with None values from the dictionary"""
        for key in list(self.keys()):
            if self[key] is None:
                super().__delitem__(key)

    def __repr__(self):
        return f"{self.__class__.__name__}({super().__repr__()})"
