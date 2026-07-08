"""Parameterized isometric grid projection.

CityPulse's ``iso(gx, gy, gz)`` and LivingForest's ``isoS(gx, gy, z)`` are the
same formula — grid coordinates to screen pixels via a tile half-width/height
and a screen origin — just with different constants baked in. ``IsoGrid``
bundles those constants once per scene so both can share the same math.
"""


class IsoGrid:
    def __init__(self, origin_x, origin_y, tile_hw, tile_hh):
        self.ox = origin_x
        self.oy = origin_y
        self.hw = tile_hw
        self.hh = tile_hh

    def project(self, gx, gy, gz=0.0):
        return (self.ox + (gx - gy) * self.hw,
                self.oy + (gx + gy) * self.hh - gz)

    def box_points(self, gx, gy, w, d, h):
        """Screen-space corners of an iso box: base A,B,C,D and roof At..Dt.
        A = back corner, B = right, C = front (closest to camera), D = left."""
        A, B = self.project(gx, gy), self.project(gx + w, gy)
        C, D = self.project(gx + w, gy + d), self.project(gx, gy + d)
        At, Bt = self.project(gx, gy, h), self.project(gx + w, gy, h)
        Ct, Dt = self.project(gx + w, gy + d, h), self.project(gx, gy + d, h)
        return A, B, C, D, At, Bt, Ct, Dt
