"""
Utilities for configurable applications.
"""

from argparse import ArgumentParser
from argparse import Namespace
from inspect import Parameter
from inspect import signature
from textwrap import dedent
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Tuple
from typing import TypeVar

import yaml


class ConfigArgs:
    """
    Hold all the configuration command line arguments for a (hopefully small) program execution.
    """

    #: The global arguments currently in effect.
    #: This is typically set in the ``main`` function.
    current: 'ConfigArgs' = None  # type: ignore

    def __init__(self, arguments: Dict[str, Tuple[Any, Callable[[str], Any], str]]) -> None:
        """
        Create a collection of arguments.

        Each argument is a tuple containing its name, a function for parsing its value from a
        string, and a description for the help message.
        """

        #: The known arguments.
        self.arguments = arguments

        #: The value for each argument.
        self.values: Dict[str, Any] = {name: argument[0] for name, argument in arguments.items()}

    def get(self, name: str, function: Callable) -> Any:
        """
        Access the value of some argument.
        """
        if name not in self.values:
            raise RuntimeError('Unknown argument: %s used by the function: %s.%s'
                               % (name, function.__module__, function.__qualname__))
        return self.values[name]

    def add_to_parser(self, parser: ArgumentParser) -> None:
        """
        Add an argument for each argument to the parser to allow overriding argument
        values directly from the command line.
        """
        parser.add_argument('--config', metavar='FILE', action='append',
                            help='Load a arguments configuration YAML file.')

        configurable = parser.add_argument_group('configuration arguments', dedent("""
            The optional configuration arguments are used by internal functions. The
            defaults are overriden by any configuration files given to ``--config`` and
            by the following optional explicit command-line arguments. If the same
            argument is set in multiple locations, the last command line argument wins
            over the last loaded configuration file.
        """))
        for name, (default, _, description) in self.arguments.items():
            configurable.add_argument('--' + name, help=description + ' (default: %s)' % default)

    def parse(self, args: Namespace) -> None:
        """
        Update the values based on loaded configuration files and/or explicit command line
        arguments.
        """
        for path in (args.config or []):
            with open(path, 'r') as file:
                data = yaml.load(file.read())
                if data is None:
                    data = {}
                if not isinstance(data, dict):
                    raise RuntimeError('The configuration file: %s '
                                       'does not contain a top-level mapping' % path)
                for name, value in data.items():
                    if name not in self.values:
                        raise RuntimeError('Unknown argument: %s '
                                           'specified in the configuration file: %s'
                                           % (name, path))

                    if isinstance(value, str):
                        try:
                            value = self.arguments[name][1](value)
                        except BaseException:
                            raise RuntimeError('Invalid value: %s for the argument: %s'
                                               % (value, name))

                    self.values[name] = value

        for name, (_, parser, _) in self.arguments.items():
            value = vars(args)[name]
            if value is not None:
                try:
                    self.values[name] = parser(value)
                except BaseException:
                    raise RuntimeError('Invalid value: %s for the argument: %s'
                                       % (vars(args)[name], name))


ConfigArgs.current = ConfigArgs({})


#: The type of a wrapped function.
Wrapped = TypeVar('Wrapped', bound=Callable)


def config(wrapped: Wrapped) -> Wrapped:
    """
    Decorator for configurable functions.
    """
    function = _real_function(wrapped)
    parameter_names = _parameter_names(function)

    def _wrapped_function(*args: Any, **kwargs: Any) -> Any:
        for name in parameter_names:
            if name not in kwargs:
                kwargs[name] = ConfigArgs.current.get(name, function)
        return function(*args, **kwargs)

    return _wrapped_function  # type: ignore


def _real_function(wrapped: Wrapped) -> Callable:
    if isinstance(wrapped, staticmethod):
        return wrapped.__func__
    return wrapped


def _parameter_names(function: Callable) -> List[str]:
    parameter_names: List[str] = []
    for parameter in signature(function).parameters.values():
        if parameter.kind == Parameter.KEYWORD_ONLY:
            parameter_names.append(parameter.name)
    return parameter_names
