import typing


Constant = str | int | bool | float

import functools




#def get_or_None_factory(data: typing.Dict) -> typing.Callable[[str, type], typing.Optional[Constant]]:
#    return functools.partial(get_or_None, data)

#def get_or_None_int(data: typing.Dict, key: str) -> typing.Optional[int]:
#    return int(data[key]) if key in data else None

#def get_or_None_str(data: typing.Dict, key: str) -> typing.Optional[str]:
#    return str(data[key]) if key in data else None



########################### Old factories for type hints ###########################
T = typing.TypeVar("T")

def get_or_None_factory(data: typing.Dict) -> typing.Callable[[str, type[T]], typing.Optional[T]]:
    return functools.partial(get_or_None, data)

def get_or_None(data: typing.Dict, key: str, convert_type: type[T] = str) -> typing.Optional[T]:
    return convert_type(data[key]) if key in data else None


class VideoTime(str):
    '''Represents a time value in video. Retain as string for perfect storage.'''
    
    def as_float(self) -> float:
        return float(self)



