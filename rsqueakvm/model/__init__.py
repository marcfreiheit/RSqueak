"""
Squeak model.

    W_Object
        W_SmallInteger
            W_MutableSmallInteger
        W_AbstractObjectWithIdentityHash
            W_AbstractFloat
                W_Float
                W_MutableFloat
            W_Character
            W_PointersObject
            W_AbstractObjectWithClassReference
                W_LargeInteger
                    W_LargeIntegerWord
                    W_LargeIntegerBig
                W_BytesObject
                W_WordsObject
            W_CompiledMethod
                W_SpurCompiledMethod
                W_PreSpurCompiledMethod
"""

from rsqueakvm.model.base import *
from rsqueakvm.model.character import *
from rsqueakvm.model.compiled_methods import *
# from rsqueakvm.model.display import *
from rsqueakvm.model.numeric import *
from rsqueakvm.model.pointers import *
from rsqueakvm.model.variable import *
