

# all accessed with mypkg.BigType or mypkg.SmallType
from .big_type import BigType
from .small_type import SmallType

# accessed as a submodule mypkg.submodule.etc
from . import submodule


# ways of importing the module separate_import:
# import mypkg.separate_import
# import mypkg.separate_import as sepimp
# from mypkg import separate_import

# if we wanted to import these into the main namespace, this is how we would do it
# from .separate_funcs import separate_func1, separate_func2
