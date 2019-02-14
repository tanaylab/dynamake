"""
Cache stat calls for better performance.
"""

import os
from glob import glob as glob_files
from stat import S_ISDIR
from typing import List
from typing import Union

from prwlock import RWLock
from sortedcontainers import SortedDict

#: Internal cached stat result.
StatResult = Union[BaseException, os.stat_result]


class Stat:
    """
    Cache stat calls for better performance.
    """
    _lock = RWLock()
    _cache: SortedDict

    @staticmethod
    def reset() -> None:
        """
        Clear the cached data.
        """
        Stat._cache = SortedDict()

    @staticmethod
    def stat(path: str) -> os.stat_result:
        """
        Return the ``stat`` data for a file.
        """
        return Stat._result(path, throw=True)  # type: ignore

    @staticmethod
    def exists(path: str) -> bool:
        """
        Test whether a file exists on disk.
        """
        result = Stat._result(path, throw=False)
        return not isinstance(result, BaseException)

    @staticmethod
    def isfile(path: str) -> bool:
        """
        Whether a file exists and is not a directory.
        """
        result = Stat._result(path, throw=False)
        return not isinstance(result, BaseException) and not S_ISDIR(result.st_mode)

    @staticmethod
    def isdir(path: str) -> bool:
        """
        Whether a file exists and is a directory.
        """
        result = Stat._result(path, throw=False)
        return not isinstance(result, BaseException) and S_ISDIR(result.st_mode)

    @staticmethod
    def _result(path: str, *, throw: bool) -> StatResult:
        path = os.path.abspath(path)
        with Stat._lock.reader_lock():
            result = Stat._cache.get(path)

        if result is not None and (not throw or not isinstance(result, BaseException)):
            return result

        try:
            result = os.stat(path)
        except BaseException as exception:
            result = exception

        with Stat._lock.writer_lock():
            Stat._cache[path] = result

        if throw and isinstance(result, BaseException):
            raise result

        return result

    @staticmethod
    def glob(pattern: str) -> List[str]:
        """
        Fast glob through the cache.

        If the pattern is a file name we know about, we can just return the result without touching
        the file system.
        """

        path = os.path.abspath(pattern)
        with Stat._lock.reader_lock():
            result = Stat._cache.get(path)

        if result is None:
            return glob_files(pattern)

        if isinstance(result, BaseException):
            return []

        return [pattern]

    @staticmethod
    def forget(path: str) -> None:
        """
        Forget the cached ``stat`` data about a file. If it is a directory,
        also forget all the data about any files it contains.
        """
        path = os.path.abspath(path)
        index = Stat._cache.bisect_left(path)
        while index < len(Stat._cache):
            index_path = Stat._cache.iloc[index]
            if os.path.commonpath([path, index_path]) != path:
                return
            Stat._cache.popitem(index)


Stat.reset()
