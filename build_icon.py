import struct, zlib

width, height = 32, 32
pixels = bytearray()
for y in range(height):
    for x in range(width):
        dx, dy = x - 16, y - 16
        dist = (dx*dx + dy*dy) ** 0.5
        if dist < 15:
            r, g, b, a = 45, 125, 70, 255
        elif dist < 16:
            r, g, b, a = 45, 125, 70, 255
        else:
            r, g, b, a = 0, 0, 0, 0
        pixels.extend([b, g, r, a])

def create_png(w, h, px):
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    raw = b''
    for y in range(h):
        raw += b'\x00'
        raw += bytes(px[y*w*4:(y+1)*w*4])
    ihdr = struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) +
            chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))

png_data = create_png(width, height, pixels)

def create_ico(w, h, png_bytes):
    size = len(png_bytes)
    header = struct.pack('<HHH', 0, 1, 1)
    entry = struct.pack('<BBBBHHII', w if w < 256 else 0,
                        h if h < 256 else 0, 0, 0, 1, 32, size, 22)
    return header + entry + png_bytes

with open('icon.ico', 'wb') as f:
    f.write(create_ico(width, height, png_data))
print('Icon generated: icon.ico')
