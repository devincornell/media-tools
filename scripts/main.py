
import sys
sys.path.append('../src')

import mypkg
from mypkg import separate_funcs

if __name__ == '__main__':
    
    # functions in root package namespace
    so = mypkg.SmallType(1, 2)
    bo = mypkg.BigType(1, 2, 3)

    # functions in submodule namespace
    mypkg.submodule.my_submodfunc()
    
    # functions in separate_funcs namespace, imported separately
    separate_funcs.separate_func1()

