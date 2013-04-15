"""
Squeak model.

    W_Object
        W_SmallInteger
        W_AbstractObjectWithIdentityHash
            W_Float
            W_AbstractObjectWithClassReference
                W_PointersObject
                W_BytesObject
                W_WordsObject
            W_CompiledMethod

W_BlockContext and W_MethodContext classes have been replaced by functions
that create W_PointersObjects of correct size with attached shadows.
"""
import sys
from spyvm import constants, error

from rpython.rlib import rrandom, objectmodel, jit, signature
from rpython.rlib.rarithmetic import intmask, r_uint
from rpython.tool.pairtype import extendabletype
from rpython.rlib.objectmodel import instantiate, compute_hash
from rpython.rtyper.lltypesystem import lltype, rffi
from rsdl import RSDL, RSDL_helper

class W_Object(object):
    """Root of Squeak model, abstract."""
    _attrs_ = []    # no RPython-level instance variables allowed in W_Object
    _settled_ = True

    def size(self):
        """Return bytesize that conforms to Blue Book.

        The reported size may differ from the actual size in Spy's object
        space, as memory representation varies depending on PyPy translation."""
        return 0

    def varsize(self, space):
        """Return bytesize of variable-sized part.

        Variable sized objects are those created with #new:."""
        return self.size(space)

    def primsize(self, space):
        # TODO remove this method
        return self.size()

    def getclass(self, space):
        """Return Squeak class."""
        raise NotImplementedError()

    def gethash(self):
        """Return 31-bit hash value."""
        raise NotImplementedError()

    def at0(self, space, index0):
        """Access variable-sized part, as by Object>>at:.

        Return value depends on layout of instance. Byte objects return bytes,
        word objects return words, pointer objects return pointers. Compiled method are
        treated special, if index0 within the literalsize returns pointer to literal,
        otherwise returns byte (ie byte code indexing starts at literalsize)."""
        raise NotImplementedError()

    def atput0(self, space, index0, w_value):
        """Access variable-sized part, as by Object>>at:put:.

        Semantics depend on layout of instance. Byte objects set bytes,
        word objects set words, pointer objects set pointers. Compiled method are
        treated special, if index0 within the literalsize sets pointer to literal,
        otherwise patches bytecode (ie byte code indexing starts at literalsize)."""
        raise NotImplementedError()

    def fetch(self, space, n0):
        """Access fixed-size part, maybe also variable-sized part (we have to
        consult the Blue Book)."""
        # TODO check the Blue Book
        raise NotImplementedError()

    def store(self, space, n0, w_value):
        """Access fixed-size part, maybe also variable-sized part (we have to
        consult the Blue Book)."""
        raise NotImplementedError()

    def fillin(self, space, g_self):
        raise NotImplementedError()

    def invariant(self):
        return True

    def shadow_of_my_class(self, space):
        """Return internal representation of Squeak class."""
        return self.getclass(space).as_class_get_shadow(space)

    def is_same_object(self, other):
        """Compare object identity. This should be used instead of directly
        using is everywhere in the interpreter, in case we ever want to
        implement it differently (which is useful e.g. for proxies). Also,
        SmallIntegers and Floats need a different implementation."""
        return self is other

    def become(self, other):
        """Become swaps two objects.
           False means swapping failed"""
        return False

    def clone(self, space):
        raise NotImplementedError

    def has_class(self):
        """All Smalltalk objects should have classes. Unfortuantely for
        bootstrapping the metaclass-cycle and during testing, that is not
        true for some W_PointersObjects"""
        return True

    def __repr__(self):
        return self.as_repr_string()

    @jit.elidable
    def as_repr_string(self):
        return "%r" % self

    def lshift(self, space, shift):
        raise error.PrimitiveFailedError()

    def rshift(self, space, shift):
        raise error.PrimitiveFailedError()

    def unwrap_uint(self, space):
        raise error.UnwrappingError("Got unexpected class in unwrap_uint")

    def fieldtype(self):
        from spyvm.fieldtypes import obj
        return obj

class W_SmallInteger(W_Object):
    """Boxed integer value"""
    # TODO can we tell pypy that its never larger then 31-bit?
    _attrs_ = ['value']
    __slots__ = ('value',)     # the only allowed slot here
    _immutable_fields_ = ["value"]

    def __init__(self, value):
        self.value = value

    def getclass(self, space):
        return space.w_SmallInteger

    def gethash(self):
        return self.value

    def invariant(self):
        return isinstance(self.value, int) and self.value < 0x8000

    def lshift(self, space, shift):
        from rpython.rlib.rarithmetic import ovfcheck, intmask, r_uint
        # shift > 0, therefore the highest bit of upperbound is not set,
        # i.e. upperbound is positive
        upperbound = intmask(r_uint(-1) >> shift)
        if 0 <= self.value <= upperbound:
            shifted = intmask(self.value << shift)
            return space.wrap_positive_32bit_int(shifted)
        else:
            try:
                shifted = ovfcheck(self.value << shift)
            except OverflowError:
                raise error.PrimitiveFailedError()
            return space.wrap_int(shifted)
        raise PrimitiveFailedError

    def rshift(self, space, shift):
        return space.wrap_int(self.value >> shift)

    def unwrap_uint(self, space):
        from rpython.rlib.rarithmetic import r_uint
        val = self.value
        if val < 0:
            raise error.UnwrappingError("got negative integer")
        return r_uint(val)


    @jit.elidable
    def as_repr_string(self):
        return "W_SmallInteger(%d)" % self.value

    def is_same_object(self, other):
        # TODO what is correct terminology to say that identity is by value?
        if not isinstance(other, W_SmallInteger):
            return False
        return self.value == other.value

    def __eq__(self, other):
        if not isinstance(other, W_SmallInteger):
            return False
        return self.value == other.value

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return self.value

    def clone(self, space):
        return self

    def fieldtype(self):
        from spyvm.fieldtypes import SInt
        return SInt

class W_AbstractObjectWithIdentityHash(W_Object):
    """Object with explicit hash (ie all except small
    ints and floats)."""
    _attrs_ = ['hash']

    #XXX maybe this is too extreme, but it's very random
    hash_generator = rrandom.Random()
    UNASSIGNED_HASH = sys.maxint

    hash = UNASSIGNED_HASH # default value

    def setchar(self, n0, character):
        raise NotImplementedError()

    def gethash(self):
        if self.hash == self.UNASSIGNED_HASH:
            self.hash = hash = intmask(self.hash_generator.genrand32()) // 2
            return hash
        return self.hash

    def invariant(self):
        return isinstance(self.hash, int)

    def _become(self, w_other):
        self.hash, w_other.hash = w_other.hash, self.hash

class W_LargePositiveInteger1Word(W_AbstractObjectWithIdentityHash):
    """Large positive integer for exactly 1 word"""
    _attrs_ = ["value", "_exposed_size"]

    def __init__(self, value, size=4):
        self.value = value
        self._exposed_size = size

    def fillin(self, space, g_self):
        self.hash = g_self.get_hash()
        word = 0
        bytes = g_self.get_bytes()
        for idx, byte in enumerate(bytes):
            assert idx < 4
            word |= ord(byte) << (idx * 8)
        self.value = intmask(word)
        self._exposed_size = len(bytes)

    def getclass(self, space):
        return space.w_LargePositiveInteger

    def invariant(self):
        return isinstance(self.value, int)

    def __repr__(self):
        return "W_LargePositiveInteger1Word(%d)" % r_uint(self.value)

    def lshift(self, space, shift):
        from rpython.rlib.rarithmetic import ovfcheck, intmask, r_uint
        # shift > 0, therefore the highest bit of upperbound is not set,
        # i.e. upperbound is positive
        upperbound = intmask(r_uint(-1) >> shift)
        if 0 <= self.value <= upperbound:
            try:
                shifted = intmask(ovfcheck(self.value << shift))
            except OverflowError:
                raise error.PrimitiveFailedError()
            return space.wrap_positive_32bit_int(shifted)
        else:
            raise error.PrimitiveFailedError()

    def rshift(self, space, shift):
        if shift == 0:
            return self
        # a problem might arrise, because we may shift in ones from left
        mask = (1 << (32 - shift))- 1
        # the mask is only valid if the highest bit of self.value is set
        # and only in this case we do need such a mask
        return space.wrap_int((self.value >> shift) & mask)

    def unwrap_uint(self, space):
        from rpython.rlib.rarithmetic import r_uint
        return r_uint(self.value)

    def clone(self, space):
        return W_LargePositiveInteger1Word(self.value)

    def at0(self, space, index0):
        if index0 >= self.size():
            raise IndexError()
        shift = index0 * 8
        result = (self.value >> shift) & 0xff
        return space.wrap_int(intmask(result))

    def atput0(self, space, index0, w_byte):
        if index0 >= self.size():
            raise IndexError()
        skew = index0 * 8
        byte = space.unwrap_int(w_byte)
        assert byte <= 0xff
        new_value = self.value & r_uint(~(0xff << skew))
        new_value |= r_uint(byte << skew)
        self.value = intmask(new_value)

    def size(self):
        return self._exposed_size

    def invariant(self):
        return isinstance(self.value, int)

    def fieldtype(self):
        from spyvm.fieldtypes import LPI
        return LPI

class W_Float(W_AbstractObjectWithIdentityHash):
    """Boxed float value."""
    _attrs_ = ['value']

    def fillin_fromwords(self, space, high, low):
        from rpython.rlib.rstruct.ieee import float_unpack
        from rpython.rlib.rarithmetic import r_ulonglong
        r = (r_ulonglong(high) << 32) | low
        self.value = float_unpack(r, 8)

    def __init__(self, value):
        self.value = value

    def fillin(self, space, g_self):
        high, low = g_self.get_ruints(required_len=2)
        self.fillin_fromwords(space, high, low)

    def getclass(self, space):
        """Return Float from special objects array."""
        return space.w_Float

    def gethash(self):
        return compute_hash(self.value)

    def invariant(self):
        return isinstance(self.value, float)

    def _become(self, w_other):
        self.value, w_other.value = w_other.value, self.value
        W_AbstractObjectWithIdentityHash._become(self, w_other)

    def __repr__(self):
        return "W_Float(%f)" % self.value

    def is_same_object(self, other):
        if not isinstance(other, W_Float):
            return False
        # TODO is that correct in Squeak?
        return self.value == other.value

    def __eq__(self, other):
        if not isinstance(other, W_Float):
            return False
        return self.value == other.value

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash(self.value)

    def clone(self, space):
        return self

    def at0(self, space, index0):
        return self.fetch(space, index0)

    def atput0(self, space, index0, w_value):
        self.store(space, index0, w_value)

    def fetch(self, space, n0):
        from rpython.rlib.rstruct.ieee import float_pack
        r = float_pack(self.value, 8) # C double
        if n0 == 0:
            return space.wrap_uint(r_uint(intmask(r >> 32)))
        else:
            assert n0 == 1
            return space.wrap_uint(r_uint(intmask(r)))

    def store(self, space, n0, w_obj):
        from rpython.rlib.rstruct.ieee import float_unpack, float_pack
        from rpython.rlib.rarithmetic import r_ulonglong

        uint = r_ulonglong(space.unwrap_uint(w_obj))
        r = float_pack(self.value, 8)
        if n0 == 0:
            r = ((r << 32) >> 32) | (uint << 32)
        else:
            assert n0 == 1
            r = ((r >> 32) << 32) | uint
        self.value = float_unpack(r, 8)

    def size(self):
        return 2

    def fieldtype(self):
        from spyvm.fieldtypes import flt
        return flt

@signature.finishsigs
class W_AbstractObjectWithClassReference(W_AbstractObjectWithIdentityHash):
    """Objects with arbitrary class (ie not CompiledMethod, SmallInteger or
    Float)."""
    _attrs_ = ['s_class', 'space']

    def __init__(self, space, w_class):
        if w_class is not None:     # it's None only for testing and space generation
            assert isinstance(w_class, W_PointersObject)
            self.s_class = w_class.as_class_get_penumbra(space)
        else:
            self.s_class = None
        self.space = space

    def getclass(self, space):
        return self.shadow_of_my_class(space).w_self()

    def __str__(self):
        if isinstance(self, W_PointersObject) and self.has_shadow():
            return self._shadow.getname()
        else:
            name = None
            if self.has_class():
                name = self.s_class.name
            return "a %s" % (name or '?',)

    @jit.elidable
    def as_repr_string(self):
        return self.as_embellished_string("W_O /w Class", "")

    def as_embellished_string(self, className, additionalInformation):
        from rpython.rlib.objectmodel import current_object_addr_as_int
        name = self.shadow_of_my_class(self.space).name or "?"
        return "<%s (a %s) %s>" % (className, name, 
                #hex(current_object_addr_as_int(self)), 
                additionalInformation)

    def invariant(self):
        from spyvm import shadow
        return (W_AbstractObjectWithIdentityHash.invariant(self) and
                isinstance(self.s_class, shadow.ClassShadow))

    def _become(self, w_other):
        self.s_class, w_other.s_class = w_other.s_class, self.s_class
        W_AbstractObjectWithIdentityHash._become(self, w_other)

    def has_class(self):
        return self.s_class is not None

    # we would like the following, but that leads to a recursive import
    #@signature(signature.types.self(), signature.type.any(),
    #           returns=signature.types.instance(ClassShadow))
    def shadow_of_my_class(self, space):
        s_class = self.s_class
        assert s_class is not None
        return s_class

class W_PointersObject(W_AbstractObjectWithClassReference):
    """Common object."""
    _attrs_ = ['_shadow', '_vars', 'fieldtypes']

    _shadow = None # Default value

    @jit.unroll_safe
    def __init__(self, space, w_class, size):
        from spyvm.fieldtypes import fieldtypes_of_length
        """Create new object with size = fixed + variable size."""
        W_AbstractObjectWithClassReference.__init__(self, space, w_class)

        vars = self._vars = [None] * size
        self.fieldtypes = fieldtypes_of_length(self.s_class, size)

        for i in range(size): # do it by hand for the JIT's sake
            vars[i] = w_nil
        self._shadow = None # Default value

    def fillin(self, space, g_self):
        from spyvm.fieldtypes import fieldtypes_of
        self._vars = g_self.get_pointers()
        self.s_class = g_self.get_class().as_class_get_penumbra(space)
        self.hash = g_self.get_hash()
        self.space = space
        self.fieldtypes = fieldtypes_of(self)

    def at0(self, space, index0):
        # To test, at0 = in varsize part
        return self.fetch(space, index0+self.instsize(space))

    def atput0(self, space, index0, w_value):
        # To test, at0 = in varsize part
        self.store(space, index0 + self.instsize(space), w_value)

    def fetch(self, space, n0):
        if self.has_shadow():
            return self._shadow.fetch(n0)
        return self._fetch(n0)

    def _fetch(self, n0):
        # return self._vars[n0]
        fieldtypes = jit.promote(self.fieldtypes)
        return fieldtypes.fetch(self, n0)

    def store(self, space, n0, w_value):
        if self.has_shadow():
            return self._shadow.store(n0, w_value)
        return self._store(n0, w_value)

    def _store(self, n0, w_value):
        # self._vars[n0] = w_value
        fieldtypes = jit.promote(self.fieldtypes)
        return fieldtypes.store(self, n0, w_value)

    def varsize(self, space):
        return self.size() - self.instsize(space)

    def instsize(self, space):
        return self.shadow_of_my_class(space).instsize()

    def primsize(self, space):
        return self.varsize(space)

    def size(self):
        if self.has_shadow():
            return self._shadow.size()
        return self._size()

    def _size(self):
        return len(self._vars)

    def invariant(self):
        return (W_AbstractObjectWithClassReference.invariant(self) and
                isinstance(self._vars, list))

    def store_shadow(self, shadow):
        assert self._shadow is None or self._shadow is shadow
        self._shadow = shadow

    @objectmodel.specialize.arg(2)
    def attach_shadow_of_class(self, space, TheClass):
        shadow = TheClass(space, self)
        self.store_shadow(shadow)
        shadow.attach_shadow()
        return shadow

    @objectmodel.specialize.arg(2)
    def as_special_get_shadow(self, space, TheClass):
        shadow = self._shadow
        if not isinstance(shadow, TheClass):
            if shadow is not None:
                raise DetachingShadowError(shadow, TheClass)
            shadow = self.attach_shadow_of_class(space, TheClass)
            shadow.update()
        return shadow

    def get_shadow(self, space):
        from spyvm.shadow import AbstractShadow
        return self.as_special_get_shadow(space, AbstractShadow)

    def as_class_get_shadow(self, space):
        from spyvm.shadow import ClassShadow
        return jit.promote(self.as_special_get_shadow(space, ClassShadow))

    # Should only be used during squeak-image loading.
    def as_class_get_penumbra(self, space):
        from spyvm.shadow import ClassShadow
        s_class = self._shadow
        if s_class is None:
            s_class = ClassShadow(space, self)
            self.store_shadow(s_class)
        else:
            assert isinstance(s_class, ClassShadow)
        return s_class

    def as_blockcontext_get_shadow(self, space):
        from spyvm.shadow import BlockContextShadow
        return self.as_special_get_shadow(space, BlockContextShadow)

    def as_methodcontext_get_shadow(self, space):
        from spyvm.shadow import MethodContextShadow
        return self.as_special_get_shadow(space, MethodContextShadow)

    def as_context_get_shadow(self, space):
        from spyvm.shadow import ContextPartShadow
        # XXX TODO should figure out itself if its method or block context
        if self._shadow is None:
            if ContextPartShadow.is_block_context(self, space):
                return self.as_blockcontext_get_shadow(space)
            return self.as_methodcontext_get_shadow(space)
        return self.as_special_get_shadow(space, ContextPartShadow)

    def as_methoddict_get_shadow(self, space):
        from spyvm.shadow import MethodDictionaryShadow
        return self.as_special_get_shadow(space, MethodDictionaryShadow)

    def as_cached_object_get_shadow(self, space):
        from spyvm.shadow import CachedObjectShadow
        return self.as_special_get_shadow(space, CachedObjectShadow)

    def as_observed_get_shadow(self, space):
        from spyvm.shadow import ObserveeShadow
        return self.as_special_get_shadow(space, ObserveeShadow)

    def has_shadow(self):
        return self._shadow is not None

    def become(self, w_other):
        if not isinstance(w_other, W_PointersObject):
            return False
        self._vars, w_other._vars = w_other._vars, self._vars
        # switching means also switching shadows
        self._shadow, w_other._shadow = w_other._shadow, self._shadow
        # shadow links are in both directions -> also update shadows
        if    self.has_shadow():    self._shadow._w_self = self
        if w_other.has_shadow(): w_other._shadow._w_self = w_other
        W_AbstractObjectWithClassReference._become(self, w_other)
        return True

    def clone(self, space):
        w_result = W_PointersObject(self.space, self.getclass(space),
                                    len(self._vars))
        w_result._vars = [self.fetch(space, i) for i in range(len(self._vars))]
        return w_result

    @jit.elidable
    def as_repr_string(self):
        return W_AbstractObjectWithClassReference.as_embellished_string(self, 
                                className='W_PointersObject', 
                                additionalInformation='len=%d' % self.size())

    def fieldtype(self):
        from spyvm.fieldtypes import obj
        return obj

class W_BytesObject(W_AbstractObjectWithClassReference):
    _attrs_ = ['bytes']

    def __init__(self, space, w_class, size):
        W_AbstractObjectWithClassReference.__init__(self, space, w_class)
        assert isinstance(size, int)
        self.bytes = ['\x00'] * size

    def fillin(self, space, g_self):
        self.s_class = g_self.get_class().as_class_get_penumbra(space)
        self.bytes = g_self.get_bytes()
        self.hash = g_self.get_hash()
        self.space = space

    def at0(self, space, index0):
        return space.wrap_int(ord(self.getchar(index0)))

    def atput0(self, space, index0, w_value):
        self.setchar(index0, chr(space.unwrap_int(w_value)))

    def getchar(self, n0):
        return self.bytes[n0]

    def setchar(self, n0, character):
        assert len(character) == 1
        self.bytes[n0] = character

    def size(self):
        return len(self.bytes)

    def __str__(self):
        return self.as_string()

    def as_repr_string(self):
        return W_AbstractObjectWithClassReference.as_embellished_string(self, 
            className='W_BytesObject', additionalInformation=self.as_string())

    def as_string(self):
        return "".join(self.bytes)

    def invariant(self):
        if not W_AbstractObjectWithClassReference.invariant(self):
            return False
        for c in self.bytes:
            if not isinstance(c, str) or len(c) != 1:
                return False
        return True

    def is_same_object(self, other):
        # XXX this sounds very wrong to me
        if not isinstance(other, W_BytesObject):
            return False
        return self.bytes == other.bytes

    def clone(self, space):
        w_result = W_BytesObject(self.space, self.getclass(space), len(self.bytes))
        w_result.bytes = list(self.bytes)
        return w_result

    def unwrap_uint(self, space):
        # TODO: Completely untested! This failed translation bigtime...
        # XXX Probably we want to allow all subclasses
        if not self.getclass(space).is_same_object(space.w_LargePositiveInteger):
            raise error.UnwrappingError("Failed to convert bytes to word")
        word = 0 
        for i in range(self.size()):
            word += r_uint(ord(self.getchar(i))) << 8*i
        return word

class W_WordsObject(W_AbstractObjectWithClassReference):
    _attrs_ = ['words']

    def __init__(self, space, w_class, size):
        W_AbstractObjectWithClassReference.__init__(self, space, w_class)
        self.words = [r_uint(0)] * size

    def fillin(self, space, g_self):
        self.words = g_self.get_ruints()
        self.s_class = g_self.get_class().as_class_get_penumbra(space)
        self.hash = g_self.get_hash()
        self.space = space

    def at0(self, space, index0):
        val = self.getword(index0)
        return space.wrap_uint(val)

    def atput0(self, space, index0, w_value):
        word = space.unwrap_uint(w_value)
        self.setword(index0, word)

    def getword(self, n):
        return self.words[n]

    def setword(self, n, word):
        self.words[n] = r_uint(word)

    def size(self):
        return len(self.words)

    def invariant(self):
        return (W_AbstractObjectWithClassReference.invariant(self) and
                isinstance(self.words, list))

    def clone(self, space):
        w_result = W_WordsObject(self.space, self.getclass(space), len(self.words))
        w_result.words = list(self.words)
        return w_result

NATIVE_DEPTH = 32

class W_DisplayBitmap(W_AbstractObjectWithClassReference):
    _attrs_ = ['pixelbuffer', '_realsize', 'display']
    _immutable_fields_ = ['_realsize', 'display']

    @staticmethod
    def create(space, w_class, size, depth, display):
        if depth == 1:
            return W_DisplayBitmap1Bit(space, w_class, size, depth, display)
        else:
            raise NotImplementedError("non B/W squeak")

    def __init__(self, space, w_class, size, depth, display):
        W_AbstractObjectWithClassReference.__init__(self, space, w_class)
        self._real_depth_buffer = [0] * size
        self.pixelbuffer = display.get_pixelbuffer()
        self._realsize = size
        self.display = display

    def at0(self, space, index0):
        val = self.getword(index0)
        return space.wrap_uint(val)

    def atput0(self, space, index0, w_value):
        word = space.unwrap_uint(w_value)
        self.setword(index0, word)

    def flush_to_screen(self):
        self.display.flip()

    def size(self):
        return self._realsize

    def invariant(self):
        return False

    def clone(self, space):
        w_result = W_WordsObject(self.space, self.getclass(space), self._realsize)
        n = 0
        while n < self._realsize:
            w_result.words[n] = self.getword(n)
            n += 1
        return w_result

    def getword(self, n):
        raise NotImplementedError("subclass responsibility")

    def setword(self, n, word):
        raise NotImplementedError("subclass responsibility")


class W_DisplayBitmap1Bit(W_DisplayBitmap):
    def getword(self, n):
        return self._real_depth_buffer[n]

    @jit.unroll_safe
    def setword(self, n, word):
        self._real_depth_buffer[n] = word
        pos = n * NATIVE_DEPTH
        mask = r_uint(1)
        mask <<= 31
        for i in xrange(32):
            bit = mask & word
            pixel = r_uint((0x00ffffff * (bit == 0)) | r_uint(0xff000000))
            self.pixelbuffer[pos] = pixel
            mask >>= 1
            pos += 1


# XXX Shouldn't compiledmethod have class reference for subclassed compiled
# methods?
class W_CompiledMethod(W_AbstractObjectWithIdentityHash):
    """My instances are methods suitable for interpretation by the virtual machine.  This is the only class in the system whose instances intermix both indexable pointer fields and indexable integer fields.

    The current format of a CompiledMethod is as follows:

        header (4 bytes)
        literals (4 bytes each)
        bytecodes  (variable)
    """

    _immutable_fields_ = ["_shadow?"]
### Extension from Squeak 3.9 doc, which we do not implement:
###        trailer (variable)
###    The trailer has two variant formats.  In the first variant, the last
###    byte is at least 252 and the last four bytes represent a source pointer
###    into one of the sources files (see #sourcePointer).  In the second
###    variant, the last byte is less than 252, and the last several bytes
###    are a compressed version of the names of the method's temporary
###    variables.  The number of bytes used for this purpose is the value of
###    the last byte in the method.

    _shadow = None # Default value
    _likely_methodname = "<unknown>"

    def __init__(self, bytecount=0, header=0):
        self._shadow = None
        self.setheader(header)
        self.bytes = ["\x00"] * bytecount

    def fillin(self, space, g_self):
        # Implicitely sets the header, including self.literalsize
        for i, w_object in enumerate(g_self.get_pointers()):
            self.literalatput0(space, i, w_object)
        self.setbytes(g_self.get_bytes()[(self.literalsize + 1) * 4:])

    def become(self, w_other):
        if not isinstance(w_other, W_CompiledMethod):
            return False
        self.argsize, w_other.argsize = w_other.argsize, self.argsize
        self.primitive, w_other.primitive = w_other.primitive, self.primitive
        self.literals, w_other.literals = w_other.literals, self.literals
        self.tempsize, w_other.tempsize = w_other.tempsize, self.tempsize
        self.bytes, w_other.bytes = w_other.bytes, self.bytes
        self.header, w_other.header = w_other.header, self.header
        self.literalsize, w_other.literalsize = w_other.literalsize, self.literalsize
        self.islarge, w_other.islarge = w_other.islarge, self.islarge
        self._shadow, w_other._shadow = w_other._shadow, self._shadow
        W_AbstractObjectWithIdentityHash._become(self, w_other)
        return True

    def getclass(self, space):
        return space.w_CompiledMethod

    def __str__(self):
        return self.as_string()

    def as_repr_string(self):
        return "<CompiledMethod %s>" % self.get_identifier_string()

    def as_string(self, markBytecode=0):
        from spyvm.interpreter import BYTECODE_TABLE
        j = 1
        retval  = "\nMethodname: " + self.get_identifier_string()
        retval += "\nBytecode:------------\n"
        for i in self.bytes:
            retval += '->' if j is markBytecode else '  '
            retval += ('%0.2i: 0x%0.2x(%0.3i) ' % (j ,ord(i), ord(i))) + BYTECODE_TABLE[ord(i)].__name__ + "\n"
            j += 1
        return retval + "---------------------\n"

    def get_identifier_string(self):
        from spyvm import shadow
        classname = '<unknown>'
        if len(self.literals) > 0:
            w_candidate = self.literals[-1]
            if isinstance(w_candidate, W_PointersObject):
                c_shadow = w_candidate._shadow
                if c_shadow is None and w_candidate.size() >= 2:
                    w_class = w_candidate._fetch(1)
                    if isinstance(w_class, W_PointersObject):
                        d_shadow = w_class._shadow
                        if isinstance(d_shadow, shadow.ClassShadow):
                            classname = d_shadow.getname()
                elif isinstance(shadow, shadow.ClassShadow):
                    classname = c_shadow.getname()
        return "%s>>#%s" % (classname, self._likely_methodname)


    def invariant(self):
        return (W_Object.invariant(self) and
                hasattr(self, 'literals') and
                self.literals is not None and
                hasattr(self, 'bytes') and
                self.bytes is not None and
                hasattr(self, 'argsize') and
                self.argsize is not None and
                hasattr(self, 'tempsize') and
                self.tempsize is not None and
                hasattr(self, 'primitive') and
                self.primitive is not None)

    def size(self):
        return self.headersize() + self.getliteralsize() + len(self.bytes)

    def gettempsize(self):
        return self.tempsize

    def getliteralsize(self):
        return self.literalsize * constants.BYTES_PER_WORD

    def bytecodeoffset(self):
        return self.getliteralsize() + self.headersize()

    def headersize(self):
        return constants.BYTES_PER_WORD

    def getheader(self):
        return self.header

    def setheader(self, header):
        primitive, literalsize, islarge, tempsize, argsize = constants.decode_compiled_method_header(header)
        self.literalsize = literalsize
        self.literals = [w_nil] * self.literalsize
        self.header = header
        self.argsize = argsize
        self.tempsize = tempsize
        self.primitive = primitive
        self.islarge = islarge

    def setliterals(self, literals):
        """NOT RPYTHON
           Only for testing"""
        self.literals = literals
        if self.has_shadow():
            self._shadow.update()

    def setbytes(self, bytes):
        self.bytes = bytes

    def as_compiledmethod_get_shadow(self, space=None):
        from shadow import CompiledMethodShadow
        if self._shadow is None:
            self._shadow = CompiledMethodShadow(self)
        return self._shadow

    def literalat0(self, space, index0):
        if index0 == 0:
            return space.wrap_int(self.getheader())
        else:
            return self.literals[index0-1]

    def literalatput0(self, space, index0, w_value):
        if index0 == 0:
            header = space.unwrap_int(w_value)
            self.setheader(header)
        else:
            self.literals[index0-1] = w_value
        if self.has_shadow():
            self._shadow.update()

    def store(self, space, index0, w_v):
        self.atput0(space, index0, w_v)

    def at0(self, space, index0):
        if index0 < self.bytecodeoffset():
            # XXX: find out what happens if unaligned
            return self.literalat0(space, index0 / constants.BYTES_PER_WORD)
        else:
            # From blue book:
            # The literal count indicates the size of the
            # CompiledMethod's literal frame.
            # This, in turn, indicates where the
            # CompiledMethod's bytecodes start.
            index0 = index0 - self.bytecodeoffset()
            assert index0 < len(self.bytes)
            return space.wrap_int(ord(self.bytes[index0]))

    def atput0(self, space, index0, w_value):
        if index0 < self.bytecodeoffset():
            if index0 % constants.BYTES_PER_WORD != 0:
                raise error.PrimitiveFailedError("improper store")
            self.literalatput0(space, index0 / constants.BYTES_PER_WORD, w_value)
        else:
            # XXX use to-be-written unwrap_char
            index0 = index0 - self.bytecodeoffset()
            assert index0 < len(self.bytes)
            self.setchar(index0, chr(space.unwrap_int(w_value)))

    def setchar(self, index0, character):
        assert index0 >= 0
        self.bytes[index0] = character
        if self.has_shadow():
            self._shadow.update()

    def has_shadow(self):
        return self._shadow is not None

class DetachingShadowError(Exception):
    def __init__(self, old_shadow, new_shadow_class):
        self.old_shadow = old_shadow
        self.new_shadow_class = new_shadow_class

# Use black magic to create w_nil without running the constructor,
# thus allowing it to be used even in the constructor of its own
# class.  Note that we patch its class in the space
# YYY there should be no global w_nil
w_nil = instantiate(W_PointersObject)
w_nil._vars = []
