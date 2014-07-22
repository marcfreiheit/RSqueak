
from spyvm import model, constants, display
from rpython.rlib import jit
from rpython.rtyper.lltypesystem import lltype, rffi
from rpython.rlib.rarithmetic import r_uint

def from_words_object(w_obj, form):
    depth = form.depth()
    space = form.space
    size = w_obj.size()
    w_class = w_obj.getclass(space)
    
    if depth < 8:
        w_display_bitmap = W_MappingDisplayBitmap(space, w_class, size, depth, form.width())
    elif depth == 8:
        w_display_bitmap = W_8BitDisplayBitmap(space, w_class, size, depth)
    elif depth == 16:
        w_display_bitmap = W_16BitDisplayBitmap(space, w_class, size, depth)
    else:
        w_display_bitmap = W_DisplayBitmap(space, w_class, size, depth)
    
    for idx in range(size):
        w_display_bitmap.setword(idx, w_obj.getword(idx))
    
    return w_display_bitmap

invert_byte_order = [False]

def invert():
    inv = invert_byte_order[0]
    return jit.promote(inv)

class W_DisplayBitmap(model.W_AbstractObjectWithClassReference):
    _attrs_ = ['pixelbuffer_words', '_real_depth_buffer', '_realsize', 'display', '_depth']
    _immutable_fields_ = ['pixelbuffer_words?', '_real_depth_buffer', '_realsize', 'display', '_depth']
    repr_classname = "W_DisplayBitmap"
    
    def __init__(self, space, w_class, size, depth):
        model.W_AbstractObjectWithClassReference.__init__(self, space, w_class)
        self._real_depth_buffer = lltype.malloc(rffi.CArray(rffi.UINT), size, flavor='raw')
        self._realsize = size
        self._depth = depth
        self.display = space.display()
        self.relinquish_display()
    
    # === Object access
    
    def at0(self, space, index0):
        val = self.getword(index0)
        return space.wrap_uint(val)
    
    def atput0(self, space, index0, w_value):
        word = space.unwrap_uint(w_value)
        self.setword(index0, word)
    
    def getword(self, n):
        assert self.size() > n >= 0
        return self._real_depth_buffer[n]
    
    def setword(self, n, word):
        self._real_depth_buffer[n] = word
        if self.pixelbuffer_words > 0:
            self.set_pixelbuffer_word(n, word)
    
    def size(self):
        return self._realsize
    
    # === Graphics
    
    def pixelbuffer_UINT(self):
        return self.display.get_pixelbuffer_UINT()
    
    def pixelbuffer_UCHAR(self):
        return self.display.get_pixelbuffer_UCHAR()
    
    def set_pixelbuffer_word(self, n, word):
        self.pixelbuffer_UINT()[n] = word
    
    def take_over_display(self):
        # Make sure FrameWrapper.take_over_display() is called first for the correct Frame object.
        pixel_per_word = constants.BYTES_PER_WORD / (self.display.depth / 8)
        self.pixelbuffer_words = self.display.width * self.display.height / pixel_per_word
        self.update_from_buffer()
    
    def relinquish_display(self):
        self.pixelbuffer_words = 0
    
    def flush_to_screen(self):
        self.display.flip()
    
    def update_from_buffer(self):
        if self.pixelbuffer_words > 0:
            for i in range(self.size()):
                self.set_pixelbuffer_word(i, self.getword(i))
    
    # === Misc
    
    def invariant(self):
        return False

    def clone(self, space):
        w_result = model.W_WordsObject(space, self.getclass(space), self.size())
        for n in range(self.size()):
            w_result.setword(n, self.getword(n))
        return w_result
    
    def is_array_object(self):
        return True

    def convert_to_c_layout(self):
        return self._real_depth_buffer

    def can_become(self, w_other):
        # TODO - implement _become() for this class. Impossible due to _immutable_fields_?
        return False
    
    def __del__(self):
        lltype.free(self._real_depth_buffer, flavor='raw')
    
    def repr_content(self):
        return "len=%d depth=%d %s" % (self.size(), self._depth, self.str_content())

class W_16BitDisplayBitmap(W_DisplayBitmap):
    
    repr_classname = "W_16BitDisplayBitmap"
    
    def set_pixelbuffer_word(self, n, word):
        mask = 0b11111
        lsb = (r_uint(word) & r_uint(0xffff0000)) >> 16
        msb = (r_uint(word) & r_uint(0x0000ffff))
        
        # Invert order of rgb-components
        lsb = (
            ((lsb >> 10) & mask) |
            (((lsb >> 5) & mask) << 6) |
            ((lsb & mask) << 11)
        )
        msb = (
            ((msb >> 10) & mask) |
            (((msb >> 5) & mask) << 6) |
            ((msb & mask) << 11)
        )
        
        self.pixelbuffer_UINT()[n] = r_uint(lsb | (msb << 16))

class W_8BitDisplayBitmap(W_DisplayBitmap):
    
    repr_classname = "W_8BitDisplayBitmap"
    
    def set_pixelbuffer_word(self, n, word):
        if invert():
            # Invert the byte-order.
            self.pixelbuffer_UINT()[n] = r_uint(
                (word >> 24) |
                ((word >> 8) & 0x0000ff00) |
                ((word << 8) & 0x00ff0000) |
                (word << 24)
            )
        else:
            self.pixelbuffer_UINT()[n] = r_uint(word)

class W_MappingDisplayBitmap(W_DisplayBitmap):
    
    repr_classname = "W_MappingDisplayBitmap"
    _attrs_ = ['mapping_factor', 'words_per_line', 'bits_in_last_word', 'width']
    _immutable_fields_ = ['mapping_factor', 'words_per_line', 'bits_in_last_word', 'width']
    
    pixel_per_word = constants.BYTES_PER_WORD
    
    def __init__(self, space, w_class, size, depth, width):
        assert depth in [1, 2, 4]
        width = r_uint(width)
        self.width = width
        self.mapping_factor = display.MINIMUM_DEPTH / depth
        self.words_per_line = r_uint(width / 32 + 1)
        self.bits_in_last_word = width % 32
        W_DisplayBitmap.__init__(self, space, w_class, size, depth)
    
    @jit.unroll_safe
    def set_pixelbuffer_word(self, n, word):
        n = r_uint(n)
        word = r_uint(word)
        pos = self.compute_pos(n)
        buf = self.display.screen.c_pixels
        
        if (n+1) % self.words_per_line == 0:
            # This is the last word on the line. A few bits are cut off.
            bits = self.bits_in_last_word
        else:
            bits = 32
        
        depth = r_uint(self._depth)
        rshift = 32 - depth
        for i in range(r_uint(bits) / depth):
            pixel = word >> rshift
            buf[pos] = rffi.cast(rffi.UCHAR, pixel)
            word <<= self._depth
            pos += 1
        
    def compute_pos(self, n):
        word_on_line = n % self.words_per_line
        complete_lines = r_uint((n - word_on_line) / self.words_per_line)
        return complete_lines * self.width + 32*word_on_line
