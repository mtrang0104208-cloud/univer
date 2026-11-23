# ASCII Universe
# @dwcminh.ascii, 2026
#
#   pip install numpy pygame-ce
#   python universe.py
#
# One unbroken shot, from the engines to the whole Earth. It opens close on the engines, already
# firing, the camera shaking as it cranes up the rocket standing at its tower before dawn. The
# rocket lifts off and the camera goes with it: the pad falls away, the lights of the coast
# spread out below, the boosters drop off. Then the camera lets go and pulls back, further and further: the rocket
# becomes a spark on a thread of smoke curving over the edge of the world, the sun breaks over
# the horizon, and the whole Earth hangs there, half in daylight, half in city lights. And it
# keeps pulling back: the Earth shrinks to a ball, the other planets come into view one after
# another, lined up out from the sun; then the sun becomes one star among the stars streaming past, and
# at last the whole galaxy lies there, with a spark in one of its arms where all of this happened.
#
# Everything is traced, one ray for every letter: the rocket is a few cones, the smoke is
# spheres, the Earth is one big sphere with a map wrapped round it.
#
# Space pause, R restart, S screenshot, Esc quit

import sys
import time
from pathlib import Path

import numpy as np
import pygame

CREDIT = "@dwcminh.ascii"

TAU = np.pi * 2
LOOP = 31.4                                     # length of one run (s)

# timeline (s)
T_LIFT = 2.4                                    # the engines have been burning since before 0 s; now it lets go
T_SEP = 7.6                                     # the two boosters drop off
T_CUTOFF = 11.0                                 # engine off: it is in orbit, coasting
T_DEPLOY = 14.2                                 # the satellite is let go: a glint
T_COSMOS = 15.6                                 # the camera leaves the Earth behind: planets, stars, the galaxy
FLASH = 0.6                                     # how long something new glows white (s)

# the world, in km
R_EARTH = 6371.0
ATMOSPHERE = 90.0                               # how high the glowing skin of air reaches
ORBIT = 420.0                                   # the altitude it ends up at
DOWNRANGE = 30.0                                # how far round the Earth it has flown by 16 s (degrees)
PAD_H = 0.006                                   # the engines stand this high above the ground
SITE = (10.4, 107.2)                            # the launch pad: latitude, longitude (the coast of Viet Nam)
SUN_DIP = 6.0                                   # at launch the sun is this far below the eastern horizon (degrees)
MOON_FAR, MOON_R = 150000.0, 6500.0             # a moon nearer and bigger than the real one

CORE, FAIRING, BOOST_L, BOOST_R, BELL, SMOKE, OCEAN, LAND, ICE, MOON = range(10)
N_PARTS = 10
# SEAM[a, b]: a cell of part a is outlined where it touches part b, however close they are in depth
SEAM = np.zeros((N_PARTS, N_PARTS), bool)
SEAM[LAND, OCEAN] = SEAM[ICE, OCEAN] = True                     # coastlines
POOLS = ["1il!;:", "rtfjcvxz=+", "aeoun0{}[]<>", "08B$#&%Q"]   # fill letters, dark -> bright
C = lambda ch: ord(ch) - 32                     # character -> glyph index
FILL = np.array([[C(p[k % len(p)]) for k in range(12)] for p in POOLS])
SLOPE = np.array([C(c) for c in "-/|\\-"])

WHITE = np.array([1.00, 0.98, 0.94])
HULL = np.array([0.94, 0.96, 1.00])             # the rocket's skin
BLACK = np.array([0.20, 0.22, 0.28])            # the bands painted on it
RED = np.array([1.00, 0.20, 0.22])
GOLD = np.array([1.00, 0.82, 0.36])
METAL = np.array([0.78, 0.64, 0.46])            # engine bells
STEEL = np.array([0.50, 0.66, 0.92])            # the tower, in strokes
FIRE = np.array([[1.00, 0.22, 0.05], [1.00, 0.52, 0.10], [1.00, 0.84, 0.36], [1.00, 1.00, 0.92]])   # cool -> hot
VACUUM = np.array([0.62, 0.80, 1.00])           # the plume in space: thin and blue
HAZE = np.array([0.56, 0.58, 0.78])             # smoke, away from the fire
SEA = np.array([0.12, 0.47, 1.00])
GRASS = np.array([0.26, 0.86, 0.36])
SAND = np.array([0.96, 0.78, 0.40])
SNOW = np.array([0.92, 0.96, 1.00])
AIR = np.array([0.36, 0.74, 1.00])              # the skin of air along the edge of the Earth
DAWN = np.array([1.00, 0.56, 0.22])             # ...where the sun is just coming up
CITY = np.array([1.00, 0.80, 0.42])
MOONLIGHT = np.array([0.86, 0.87, 0.92])
STAR_INK = np.array([[1.0, 1.0, 1.0], [0.70, 0.82, 1.0], [1.0, 0.86, 0.66]])
DIM, ACCENT, SIGN = (104, 112, 132), (255, 170, 80), (176, 184, 208)


def smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def unit(v):
    v = np.asarray(v, float)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def slope_char(dx, dy):
    # screen direction (y up) -> the ASCII stroke that looks most like it
    ang = np.degrees(np.arctan2(dy, dx)) % 180
    return SLOPE[np.digitize(ang, [25, 72, 108, 155])]


def outline_letter(gx, gy):
    ax, ay = np.abs(gx), np.abs(gy)
    c = np.where(ax > 2 * ay, C("|"), np.where(ay > 2 * ax, np.where(gy > 0, C("_"), C("-")),
                 np.where(gx * gy > 0, C("/"), C("\\"))))
    return np.where(ax + ay == 0, C("+"), c)


def track(t, times, values):
    # a smooth path through keyframes (a spline that passes through every one of them)
    i = int(np.clip(np.searchsorted(times, t, side="right") - 1, 0, len(times) - 2))
    h = times[i + 1] - times[i]
    u = np.clip((t - times[i]) / h, 0, 1)
    slope = np.gradient(values, times, axis=0)
    return ((2 * u ** 3 - 3 * u ** 2 + 1) * values[i] + (u ** 3 - 2 * u ** 2 + u) * h * slope[i]
            + (3 * u ** 2 - 2 * u ** 3) * values[i + 1] + (u ** 3 - u ** 2) * h * slope[i + 1])


def climb(t, times, values):
    # like track, for one value, but it never overshoots: between two keys it only goes one way
    rise = np.diff(values) / np.diff(times)
    slope = np.zeros(len(values))
    same = rise[:-1] * rise[1:] > 0
    slope[1:-1][same] = 2 * rise[:-1][same] * rise[1:][same] / (rise[:-1][same] + rise[1:][same])
    slope[0] = rise[0]
    i = int(np.clip(np.searchsorted(times, t, side="right") - 1, 0, len(times) - 2))
    h = times[i + 1] - times[i]
    u = np.clip((t - times[i]) / h, 0, 1)
    return ((2 * u ** 3 - 3 * u ** 2 + 1) * values[i] + (u ** 3 - 2 * u ** 2 + u) * h * slope[i]
            + (3 * u ** 2 - 2 * u ** 3) * values[i + 1] + (u ** 3 - u ** 2) * h * slope[i + 1])


# the Earth: y is its axis (north up), longitude runs eastwards, to the right as seen from outside

def on_globe(lat, lon):
    lat, lon = np.radians(lat), np.radians(lon)
    return np.stack([np.cos(lat) * np.cos(lon), np.sin(lat), -np.cos(lat) * np.sin(lon)], -1)


NORTH = np.array([0.0, 1.0, 0.0])
U0 = on_globe(*SITE)                                            # straight up at the pad
E0 = unit(np.cross(NORTH, U0))                                  # east there
N0 = np.cross(U0, E0)                                           # north there
SUN = unit(np.cos(np.radians(SUN_DIP)) * E0 - np.sin(np.radians(SUN_DIP)) * U0 - 0.30 * N0)   # ...and to the south: November
PAD = (R_EARTH + PAD_H) * U0

# the map: one letter for every 3 degrees, north at the top, 180 W at the left
WORLD = [
    "........................................................................................................................",
    "........................................................................................................................",
    "...............................########....#########....................................................................",
    "............................##########################..........###........................##...........................",
    "....................####..#.######...#################.......................................####.......................",
    "..................#####.#..##.###........############.........................#....#...#############.##.................",
    "......#####........#.#####..#.#######.....##########...............###............###############################.......",
    "##...############################...###...#######................########..#############################################",
    ".....###########################...####....####......##........####.####################################################",
    ".....########################.....##........##................####.###################################################..",
    "......###.....###############.....#####.......................####..#######################################......#......",
    "...............#################..######..................##...##..#######################################......##......",
    ".................########################................#.#.###############################################....#.......",
    "..................#####################..#.................#################################################............",
    "...................####################....................###############################################..............",
    "..................###################....................#############...################################..#............",
    "...................#################.....................###.....######################################.................",
    "...................################......................###.........###############################..#...#.............",
    "....................##############........................######........############################....##..............",
    ".....................############........................#########.##.###############################...................",
    "......................######....#.......................####################.########################...................",
    "........................####...........................######################.######################....................",
    ".........................###..........................##################.#######...################.....................",
    ".........................###..#.....#.................#########################.....#####..####.........................",
    "...........................####.......................###################.####......###.....####....#...................",
    "..............................##......................######################.........##......###........................",
    "...............................#...####................######################........##........#........................",
    "..................................#######...............#####################................#.......#..................",
    "..................................#########..............#....##############................###...##....................",
    "..................................#########....................############..................##..##.....................",
    ".................................############..................###########...................##.###.#...#...............",
    ".................................###############................#########.....................#.....#....###............",
    ".................................###############................#########........................#........###...........",
    "..................................##############................#########...............................................",
    "..................................#############.................##########..#..........................##..#............",
    "...................................############.................#########..##........................#####.##...........",
    "....................................###########.................########...#........................#########...........",
    "....................................##########...................#######..##......................############..........",
    "....................................########.....................######...........................#############.........",
    "....................................########.....................######...........................#############.........",
    "....................................#######.......................####............................#############.........",
    "....................................######........................#................................#.....#####..........",
    "...................................######..................................................................###........#.",
    "...................................####...............................................................................#.",
    "...................................###..............................................................................##..",
    "...................................###..............................................................................#...",
    "...................................###..................................................................................",
    "...................................##...................................................................................",
    "........................................................................................................................",
    "........................................................................................................................",
    "........................................................................................................................",
    "........................................................................................................................",
    "......................................#....................................#######.....######################...........",
    "....................................###......................#####.#.##############.################################....",
    "..........................##############...............#############################################################....",
    "...........##########################.............################################################################......",
    ".........#########################.........##...##################################################################......",
    "........###############################..###########################################################################....",
    "########################################################################################################################",
    "########################################################################################################################",
]
LAND_MAP = np.array([[c == "#" for c in row] for row in WORLD], float)


def is_land(lat, lon):
    # the map read between its letters, so coasts come out rounded rather than in steps
    r = np.clip((90 - lat) / 3 - 0.5, 0, LAND_MAP.shape[0] - 1.001)
    c = ((lon + 180) / 3 - 0.5) % LAND_MAP.shape[1]
    r0, c0 = r.astype(int), c.astype(int)
    c1 = (c0 + 1) % LAND_MAP.shape[1]
    fr, fc = r - r0, c - c0
    v = (LAND_MAP[r0, c0] * (1 - fc) + LAND_MAP[r0, c1] * fc) * (1 - fr) \
        + (LAND_MAP[r0 + 1, c0] * (1 - fc) + LAND_MAP[r0 + 1, c1] * fc) * fr
    return v > 0.5


# where people live, roughly: (latitude, longitude, how wide in degrees, how bright); the lights
# of the night side are scattered inside these
PEOPLE = np.array([
    (10.8, 106.7, 1.6, 0.9), (21.0, 105.8, 1.6, 0.8), (16.0, 108.0, 1.0, 0.5), (13.7, 100.5, 1.6, 0.7),
    (-7.0, 110.0, 3.5, 0.7), (14.6, 121.0, 1.6, 0.6), (23.0, 113.5, 2.6, 0.9), (31.0, 121.0, 3.2, 0.9),
    (37.0, 116.0, 5.0, 0.8), (36.5, 127.5, 2.0, 0.9), (35.5, 137.0, 3.6, 0.9), (24.0, 121.0, 1.2, 0.8),
    (27.0, 80.0, 7.0, 0.7), (13.0, 78.0, 6.0, 0.5), (24.0, 90.0, 2.2, 0.8), (2.5, 102.5, 2.2, 0.7),
    (30.0, 105.0, 3.0, 0.6), (31.0, 73.0, 3.0, 0.6), (50.0, 8.0, 12.0, 0.6), (39.0, -80.0, 10.0, 0.6),
    (35.0, -119.0, 3.0, 0.6), (-23.0, -46.0, 4.0, 0.6), (30.0, 31.0, 2.0, 0.7), (25.0, 52.0, 4.0, 0.4),
    (-34.0, 151.0, 2.0, 0.6), (-38.0, 145.0, 1.6, 0.5), (7.0, 5.0, 4.0, 0.4), (19.5, -99.0, 2.6, 0.6),
    (55.7, 37.6, 3.0, 0.5), (-26.0, 28.0, 2.0, 0.5), (41.0, 29.0, 2.0, 0.5), (-6.2, 106.8, 1.2, 0.9)])
# and the dry places, sand rather than green: (latitude, longitude, half height, half width in degrees)
DRY = np.array([(24.0, 20.0, 9.0, 36.0), (24.0, 48.0, 8.0, 10.0), (-25.0, 130.0, 6.0, 13.0), (42.0, 85.0, 6.0, 26.0),
                (30.0, 62.0, 6.0, 8.0), (35.0, -112.0, 5.0, 7.0), (-23.0, 18.0, 5.0, 5.0)])


def city_map():
    # a grid of half degrees: True where a light burns; denser the nearer the middle of a crowd
    lat, lon = np.meshgrid(89.75 - 0.5 * np.arange(360), -179.75 + 0.5 * np.arange(720), indexing="ij")
    crowd = np.full(lat.shape, 0.012)
    for la, lo, wide, bright in PEOPLE:
        gap = np.hypot(lat - la, ((lon - lo + 180) % 360 - 180) * np.cos(np.radians(la)))
        crowd += bright * np.exp(-(gap / wide) ** 2)
    dice = np.random.default_rng(7).random(lat.shape)
    lit = is_land(lat, lon) & (dice < np.minimum(crowd, 0.9))
    return lit, lit & (dice < 0.3 * crowd)                      # every light, and the big cities among them


LIGHTS, BIG_LIGHTS = city_map()


# the flight: straight up, then leaning over to the east, faster and faster, into orbit

def altitude(t):
    tau = max(t - T_LIFT, 0.0)
    climb = 0.02 * tau ** 2 * (1 + (tau / 2.2) ** 5)            # km: slow off the pad, then away
    return ORBIT * (1 - np.exp(-climb / ORBIT))                 # ...levelling off at its orbit


def downrange(t):
    return np.radians(DOWNRANGE) * (np.clip(t - 5.0, 0.0, 11.0) / 11.0) ** 3


def position(t):
    # where the base of the rocket is, and which way is up there
    phi = downrange(t)
    up = np.cos(phi) * U0 + np.sin(phi) * E0
    return (R_EARTH + PAD_H + altitude(t)) * up, up


def rocket(t):
    # the rocket at time t: the position of its base, and its own axes (x across, y along its
    # length, z across), which follow the way it is travelling
    p, up = position(t)
    along = unit(position(t + 0.02)[0] - position(t - 0.02)[0] + 2e-5 * up)
    across = unit(np.cross(N0, along))
    return p, np.stack([across, along, np.cross(across, along)])


# the rocket's shape, in metres along its own axis: cones and cylinders (x, z of the axis, y from,
# y to, radius from, radius to, part)
CORE_SHAPE = np.array([
    (0, 0, 0.0, 3.4, 1.90, 1.00, BELL),                         # engine bell
    (0, 0, 3.4, 5.0, 1.60, 2.60, CORE),                         # skirt
    (0, 0, 5.0, 50.0, 2.60, 2.60, CORE),                        # tanks
    (0, 0, 50.0, 60.0, 2.60, 2.60, FAIRING),                    # the fairing round the satellite...
    (0, 0, 60.0, 65.0, 2.60, 1.90, FAIRING),                    # ...rounding off...
    (0, 0, 65.0, 68.5, 1.90, 0.90, FAIRING),
    (0, 0, 68.5, 70.0, 0.90, 0.05, FAIRING)])                   # ...to a point
BOOSTER_SHAPE = np.array([
    (0, 0, 0.0, 3.0, 1.45, 0.80, BELL),
    (0, 0, 3.0, 38.0, 1.70, 1.70, BOOST_L),
    (0, 0, 38.0, 42.0, 1.70, 1.10, BOOST_L),
    (0, 0, 42.0, 45.0, 1.10, 0.05, BOOST_L)])
BOOSTER_OUT = 4.4                                               # how far each booster's axis is from the core's
ROCKET_LEN = 70.0
# flat round plates closing them off: (x, z, y, radius); the first of each is the fire inside the bell
CORE_PLATES = np.array([(0, 0, 2.4, 1.30), (0, 0, 3.4, 1.60)])
BOOSTER_PLATES = np.array([(0, 0, 2.0, 1.00), (0, 0, 3.0, 1.70)])


def hit_cones(o, d, shape):
    # where each ray (from o, along each row of d) first meets each cone: distance along the ray
    cx, cz, y0, y1, r0, r1 = shape[:, :6].T
    k = (r1 - r0) / (y1 - y0)                                   # how fast the radius changes along it
    ox, oy, oz = o[0] - cx, o[1], o[2] - cz
    rr = r0 + k * (oy - y0)
    dx, dy, dz = d[:, 0:1], d[:, 1:2], d[:, 2:3]
    a = dx * dx + dz * dz - (k * dy) ** 2
    b = ox * dx + oz * dz - k * rr * dy
    c = ox * ox + oz * oz - rr * rr
    disc = b * b - a * c
    root = np.sqrt(np.maximum(disc, 0))
    a = np.where(np.abs(a) < 1e-12, 1e-12, a)
    best = np.full(disc.shape, np.inf)
    for t in ((-b + root) / a, (-b - root) / a):                # far side first, so the near side wins
        y = oy + t * dy
        ok = (disc > 0) & (t > 0) & (y >= y0) & (y <= y1) & (r0 + k * (y - y0) >= 0) & (t < best)
        best = np.where(ok, t, best)
    return best, k


def hit_plates(o, d, plates):
    cx, cz, yc, r = plates.T
    dy = np.where(np.abs(d[:, 1:2]) < 1e-9, 1e-9, d[:, 1:2])
    t = (yc - o[1]) / dy
    x, z = o[0] + t * d[:, 0:1] - cx, o[2] + t * d[:, 2:3] - cz
    return np.where((t > 0) & (x * x + z * z < r * r), t, np.inf)


def trace_body(eye, rays, origin, axes, shape, plates):
    # one rigid thing made of cones and plates, standing at `origin` (km) with its own `axes`:
    # for every ray, how far away it is hit (km), what by, where on it, and the surface's normal
    o = axes @ (eye - origin) * 1000.0                          # the eye, in the body's own metres
    d = rays @ axes.T
    t_cone, k = hit_cones(o, d, shape)
    t_all = np.concatenate([t_cone, hit_plates(o, d, plates)], 1)
    which = np.argmin(t_all, 1)
    t = t_all[np.arange(len(d)), which]
    hit = np.flatnonzero(np.isfinite(t))
    which, t = which[hit], t[hit]
    p = o + t[:, None] * d[hit]
    cone = which < len(shape)
    j = np.where(cone, which, 0)
    rx, rz = p[:, 0] - shape[j, 0], p[:, 2] - shape[j, 1]
    n = unit(np.stack([rx, -k[j] * np.hypot(rx, rz), rz], 1))
    n = np.where(cone[:, None], n, [0.0, -1.0, 0.0])
    n = n * -np.sign((n * d[hit]).sum(1, keepdims=True))        # facing the eye (the inside of a bell faces in)
    part = np.where(cone, shape[j, 6], BELL).astype(int)
    fire = ~cone & (which == len(shape))                        # the plate that is the fire inside the bell
    return hit, t / 1000.0, part, p[:, 1], np.arctan2(rz, rx), n @ axes, fire


def paint_core(part, y, ang):
    # the paint on the core: white, a chequered band, a black ring, a red band with gold stars,
    # a red tip; returns colour and a glyph of its own (or -1)
    rgb = np.tile(HULL, (len(y), 1))
    glyph = np.full(len(y), -1)
    black = ((y > 24) & (y < 29) & ((np.floor(ang / (TAU / 8)) + np.floor((y - 24) / 2.5)) % 2 == 0)) | ((y > 48.6) & (y < 50))
    red = ((y > 37) & (y < 42)) | (y > 66)
    rgb[black], rgb[red] = BLACK, RED
    star = (np.abs(y - 39.5) < 0.9) & (np.abs((ang % (TAU / 4)) - TAU / 8) < 0.16)
    glyph[star] = C("*")
    rgb[star] = GOLD
    rgb[part == BELL] = METAL
    return rgb, glyph


def paint_booster(part, y, ang):
    rgb = np.tile(HULL, (len(y), 1))
    rgb[(y > 30) & (y < 32)] = BLACK
    rgb[y > 38] = RED
    rgb[part == BELL] = METAL
    return rgb, np.full(len(y), -1)


# the tower and the light masts by the pad: strokes. In the pad's own metres (x east, y up, z south)

def tower_lines():
    lines, half, top = [], 3.6, 78.0
    cx, cz = -12.5, -9.0                                        # the tower stands to the north-west
    corners = [(cx - half, cz - half), (cx + half, cz - half), (cx + half, cz + half), (cx - half, cz + half)]
    levels = np.arange(0, top + 0.1, 6.5)
    for (x, z) in corners:
        lines.append(((x, 0, z), (x, top, z)))                  # legs
    for n, (a, b) in enumerate(zip(corners, corners[1:] + corners[:1])):
        for i, (lo, hi) in enumerate(zip(levels[:-1], levels[1:])):
            lines.append(((a[0], hi, a[1]), (b[0], hi, b[1])))  # rings
            p, q = (a, b) if (i + n) % 2 else (b, a)
            lines.append(((p[0], lo, p[1]), (q[0], hi, q[1])))  # braces, zigzag
    lines.append(((cx, top, cz), (cx, top + 16, cz)))           # the mast on top
    for x, z, tall in ((-46, -14, 58), (40, -34, 58), (34, 40, 52)):
        lines.append(((x, 0, z), (x, tall, z)))                 # light masts round the pad
    pts, way = [], []
    for a, b in lines:
        a, b = np.array(a, float), np.array(b, float)
        n = max(2, int(np.linalg.norm(b - a) / 0.35))
        pts.append(a + (b - a) * np.linspace(0, 1, n)[:, None])
        way.append(np.tile(unit(b - a), (n, 1)))
    return np.concatenate(pts), np.concatenate(way)


TOWER_PTS, TOWER_WAY = tower_lines()
LAMPS = np.array([(-12.5, 94.0, -9.0), (-46, 58, -14), (40, 58, -34), (34, 52, 40)], float)   # the beacon, the floodlights
PAD_AXES = rocket(0.0)[1]                                       # the pad's own axes: the rocket's, before it moves

# smoke: balls of it rolling out along the ground from under the engines, growing as they go
N_SMOKE = 72
SMOKE_SEED = np.random.default_rng(3).random((N_SMOKE, 5))


def smoke(t):
    # centres (km, in the world) and radii of the balls of smoke at time t
    born = -3.0 + SMOKE_SEED[:, 0] * 8.5                        # from before the start to well after lift-off
    age = t - born
    live = np.flatnonzero((age > 0) & (age < 9))
    age, s = age[live], SMOKE_SEED[live]
    az = np.pi * (s[:, 1] > 0.5) + 0.9 * (s[:, 0] * 7 % 1 - 0.5)                    # east or west, along the flame trench
    out = (10 + 38 * s[:, 2]) * (1 - np.exp(-age / 1.6)) + 1.5 * age                # metres from the pad
    r = (2.5 + 6.0 * s[:, 3] ** 2) * (1 - np.exp(-age / 1.2)) * (1 - smooth((age - 7) / 2))
    y = 0.55 * r + 16 * s[:, 4] ** 2 * (1 - np.exp(-age / 2.5)) - 1000 * PAD_H     # some of it boils up as it goes
    local = np.stack([out * np.cos(az), y, out * np.sin(az)], 1)
    return PAD + (local @ PAD_AXES) / 1000.0, r / 1000.0


def hit_balls(eye, rays, centres, radii):
    # nearest ball each ray meets: distance, which ball, and the normal there
    oc = centres - eye
    b = rays @ oc.T
    a = (rays * rays).sum(1, keepdims=True)
    disc = b * b - a * ((oc * oc).sum(1) - radii ** 2)
    t = np.where(disc > 0, (b - np.sqrt(np.maximum(disc, 0))) / a, np.inf)
    t = np.where(t > 0, t, np.inf)
    which = np.argmin(t, 1)
    t = t[np.arange(len(rays)), which]
    hit = np.flatnonzero(np.isfinite(t))
    n = unit(eye + t[hit, None] * rays[hit] - centres[which[hit]])
    return hit, t[hit], which[hit], n


def plume(eye, rays, start, way, length, wide, t, seed):
    # a jet of fire from `start` along `way`: for every ray, how deep into the fire it passes
    # (0 = misses, 1 = through the core), how far down the jet, and how far from the eye
    w = eye - start
    b, e, f = rays @ way, rays @ w, way @ w
    a = (rays * rays).sum(1)
    den = np.where(np.abs(a - b * b) < 1e-12, 1e-12, a - b * b)
    s = np.clip((a * f - b * e) / den, 0, length)               # the point on the jet's axis nearest the ray
    tr = np.maximum((s * b - e) / a, 0)                         # ...and the point on the ray nearest to that
    gap = np.linalg.norm(w + tr[:, None] * rays - s[:, None] * way, axis=1)
    v = s / length
    lick = 1 + 0.16 * np.sin(v * 23 - t * 46 + seed) + 0.10 * np.sin(v * 61 - t * 83 + 2 * seed)   # the flame flickers
    radius = wide * (0.9 + 2.1 * v ** 0.7) * np.sqrt(np.clip(1 - v ** 3, 0, 1)) * lick
    return np.clip(1 - gap / np.maximum(radius, 1e-9), 0, 1) * (tr > 0), v, tr


# camera: one shot. (time, where it stands as seen from the rocket: compass bearing and elevation
# in degrees and distance in km (log10), how far up the rocket it looks (m), how much it rides
# with the rocket (0 = stays by the pad), how much it looks at the Earth instead, lens: tan of
# half the view's height)
SHOT = np.array([
    (0.0, 158, 2, np.log10(0.026), 8, 0.0, 0.00, 0.62),         # close on the engines
    (1.2, 150, 4, np.log10(0.050), 16, 0.0, 0.00, 0.58),        # craning up and back
    (2.4, 140, 6, np.log10(0.110), 30, 0.0, 0.00, 0.50),        # the whole rocket: lift-off
    (3.6, 134, 5, np.log10(0.120), 34, 0.0, 0.00, 0.50),        # watching it rise from the ground
    (5.0, 126, -4, np.log10(0.115), 22, 1.0, 0.00, 0.48),       # ...then going with it
    (6.4, 150, 24, np.log10(0.125), 22, 1.0, 0.00, 0.46),       # round and above: the ground falls away
    (7.6, 185, 22, np.log10(0.140), 26, 1.0, 0.00, 0.46),       # the boosters drop off
    (8.4, 205, 18, np.log10(0.200), 26, 1.0, 0.00, 0.44),
    (9.0, 232, 13, np.log10(2.5), 25, 1.0, 0.00, 0.42),         # letting go: pulling back
    (9.7, 258, 10, np.log10(80.0), 25, 1.0, 0.00, 0.40),        # behind it, looking east into the sunrise
    (10.5, 268, 14, np.log10(900.0), 25, 1.0, 0.00, 0.38),
    (11.3, 262, 34, np.log10(5000.0), 25, 1.0, 0.35, 0.34),     # the edge of the world, curved
    (12.6, 215, 70, np.log10(15000.0), 25, 1.0, 0.85, 0.30),    # over the top, round to the day side
    (14.2, 160, 76, np.log10(27000.0), 25, 1.0, 1.00, 0.29),    # the whole Earth
    (16.0, 150, 74, np.log10(29000.0), 25, 1.0, 1.00, 0.29)])


def camera(t):
    if t > T_COSMOS:
        return far_camera(t)
    az, el, dist, aim, ride, earth, lens = track(t, SHOT[:, 0], SHOT[:, 1:])
    az, el, dist = np.radians(az), np.radians(el), 10 ** dist
    ride, earth = np.clip(ride, 0, 1), np.clip(earth, 0, 1)
    p, axes = rocket(t)
    anchor = PAD + (p - PAD) * ride
    up = unit(anchor)
    east = unit(np.cross(N0, up))
    eye = anchor + dist * (np.cos(el) * (np.sin(az) * east + np.cos(az) * N0) + np.sin(el) * up)
    look = (p + axes[1] * aim / 1000.0) * (1 - earth)           # at the rocket, later at the Earth's centre
    rumble = 1 - smooth((t - 3.0) / 2.0)                        # the ground shakes while it is near
    look = look + dist * 0.006 * rumble * (np.sin(t * 47) * east + np.sin(t * 61 + 1) * up)
    fwd = unit(look - eye)
    right = unit(np.cross(fwd, unit(up * (1 - earth) + NORTH * earth)))
    return eye, np.stack([right, np.cross(right, fwd), fwd]), lens


# beyond the Earth (km): the sun and its planets, then the galaxy
AU, LY = 1.496e8, 9.461e12
SUN_AT = SUN * AU                                               # the sun itself (the Earth is at the origin)
ECL_X = -SUN                                                    # the planets' plane: this way from the sun to the Earth...
ECL_UP = unit(NORTH - (NORTH @ SUN) * SUN)                      # ...and this way is up out of it
ECL_Y = np.cross(ECL_UP, ECL_X)
LABELS = False                                                   # write each planet's name beside it
GALAXY_R = 52000 * LY                                           # the radius of the galaxy's disc
HOME_R, HOME_TURN = 26000 * LY, 215.0                           # where in it the sun is: how far out, and which way round
GAL_UP = unit(0.5 * ECL_UP + 0.866 * ECL_Y)                     # the disc is tilted 60 degrees from the planets' plane
GAL_X = unit(np.cross(GAL_UP, ECL_UP))
GAL_Z = np.cross(GAL_X, GAL_UP)
GAL_AT = SUN_AT - HOME_R * (np.cos(np.radians(HOME_TURN)) * GAL_X + np.sin(np.radians(HOME_TURN)) * GAL_Z)   # its centre
GAL_PITCH, GAL_SPIN = 17.0, 0.012                               # how tightly the arms wind (degrees); how fast it turns
GAL_TILT, GAL_ROLL = 29.0, 30.0                                 # the last shot: degrees above the disc, and rolled this much
GAL_CORE = np.array([1.00, 0.90, 0.70])
ARM_BLUE = np.array([0.50, 0.70, 1.00])
ARM_VIOLET = np.array([0.74, 0.52, 1.00])
DUST = np.array([0.88, 0.46, 0.24])
KNOT = np.array([1.00, 0.46, 0.76])

# the second half of the shot: (seconds after T_COSMOS, how far the camera is from what it looks at,
# in km). What it looks at, and from where, follow from the distance alone.
COSMOS = np.array([
    (0.0, 3.5e4),
    (1.0, 2.6e5),                                               # the Earth shrinks to a ball...
    (8.6, 1.0e12),                                              # (the picture of the solar system comes in between)
    (9.4, 1.0e14),                                              # out among the stars
    (10.6, 3.0e16),
    (12.0, 1.30e18),                                            # the whole galaxy
    (15.8, 1.45e18)])
COSMOS[:, 1] = np.log10(COSMOS[:, 1])


def near_camera_end():
    # where the first half of the shot leaves the camera: the second half starts from there
    eye, basis, lens = camera(T_COSMOS)
    return eye, lens


EYE0, LENS0 = near_camera_end()
COSMOS[0, 1] = np.log10(np.linalg.norm(EYE0))
VIEW0 = unit(EYE0)                                              # looking down on the Earth, as the first half ended
VIEW1 = unit(0.78 * ECL_UP + 0.62 * unit(VIEW0 - (VIEW0 @ ECL_UP) * ECL_UP))       # from well above the planets' plane
_flat = unit(VIEW1 - (VIEW1 @ GAL_UP) * GAL_UP)
VIEW2 = unit(np.sin(np.radians(GAL_TILT)) * GAL_UP + np.cos(np.radians(GAL_TILT)) * _flat)   # low over the galaxy's disc
UP2 = unit(np.cos(np.radians(GAL_ROLL)) * GAL_UP + np.sin(np.radians(GAL_ROLL)) * unit(np.cross(GAL_UP, VIEW2)))


def far_camera(t):
    dist = climb(t - T_COSMOS, COSMOS[:, 0], COSMOS[:, 1])      # log10 km
    a, b = smooth((dist - 7.6) / 1.0), smooth((dist - 17.0) / 0.9)      # it looks at the Earth, then the sun, then the
    focus = SUN_AT * a * (1 - b) + GAL_AT * b                           # middle of the galaxy
    a, b = smooth((dist - 5.2) / 3.2), smooth((dist - 14.0) / 3.6)      # ...from above the Earth, the planets, the disc
    way = unit(unit(VIEW0 * (1 - a) + VIEW1 * a) * (1 - b) + VIEW2 * b)
    up = unit(unit(NORTH * (1 - a) + ECL_UP * a) * (1 - b) + UP2 * b)
    eye = focus + 10 ** dist * way
    fwd = unit(focus - eye)
    right = unit(np.cross(fwd, up))
    return eye, np.stack([right, np.cross(right, fwd), fwd]), LENS0


def moon_place():
    # the moon hangs where the last shot of the Earth will find it: up in the left corner, far behind
    eye, basis, lens = camera(T_COSMOS - 0.3)
    return eye + MOON_FAR * unit(basis[2] - 0.52 * lens * basis[0] + 0.68 * lens * basis[1])


MOON_AT = moon_place()


def project(p, eye, basis, lens, cols, rows, aspect):
    # world points -> screen cells (may be fractional) and depth
    cam = (p - eye) @ basis.T
    z = np.maximum(cam[..., 2], 1e-9)
    x, y = np.clip(cam[..., 0] / z / (lens * aspect), -1e6, 1e6), np.clip(cam[..., 1] / z / lens, -1e6, 1e6)
    return (x + 1) * 0.5 * cols, (1 - y) * 0.5 * rows, cam[..., 2]


_GRID = {}


def grid(rows, cols):
    # for a screen of this size: each cell's place across and down (-1..1), and a hash of it
    if (rows, cols) not in _GRID:
        r, c = np.mgrid[0:rows, 0:cols]
        _GRID[rows, cols] = (((c + 0.5) / cols * 2 - 1).ravel(), (1 - (r + 0.5) / rows * 2).ravel(),
                             np.random.default_rng(1).integers(0, 9973, rows * cols))
    return _GRID[rows, cols]


def sunlit(p):
    # is this point out of the Earth's shadow? (0..1, soft at the edge)
    along = p @ SUN
    off = np.linalg.norm(p - along * SUN)
    return 1.0 if along > 0 else float(smooth((off - R_EARTH) / 40.0))


def earth_layer(eye, rays, t, hsh):
    # the Earth, for every ray: the day side as sea, land and ice; the night side dark but for
    # the lights of its cities; and round its edge a thin skin of air that glows where the sun is
    n = len(rays)
    part, lum, glyph = np.full(n, -1), np.zeros(n), np.full(n, -1)
    rgb, depth = np.zeros((n, 3)), np.full(n, np.inf)
    a = (rays * rays).sum(1)
    b = rays @ eye
    disc = b * b - a * (eye @ eye - R_EARTH ** 2)
    high = np.linalg.norm(eye) - R_EARTH                        # how high the camera is
    hit = np.flatnonzero((disc > 0) & (b < 0))
    tt = (-b[hit] - np.sqrt(disc[hit])) / a[hit]
    p = unit(eye + tt[:, None] * rays[hit])
    depth[hit] = tt
    lat, lon = np.degrees(np.arcsin(p[:, 1])), np.degrees(np.arctan2(-p[:, 2], p[:, 0]))
    sun = p @ SUN
    day = smooth((sun - 0.02) / 0.30)                           # full daylight only once the sun is well up
    land = is_land(lat, lon)
    ice = (land & (np.abs(lat) > 66)) | (lat > 80)
    dry = np.zeros(len(hit), bool)
    for la, lo, hh, hw in DRY:
        dry |= (np.abs(lat - la) < hh) & (np.abs((lon - lo + 180) % 360 - 180) < hw)
    ink = np.where(ice[:, None], SNOW, np.where(land[:, None], np.where(dry[:, None], SAND, GRASS), SEA))
    # the sun glints off the sea; the land is lit brighter than the water
    glint = np.clip((p * unit(SUN - unit(rays[hit]))).sum(1), 0, 1) ** 60
    shade = np.where(land, 0.78 + 0.34 * np.clip(sun, 0, 1), 0.60 + 0.26 * np.clip(sun, 0, 1) + 0.9 * glint * ~land)
    # clouds: swirls of white, thickest along the equator and in the two belts of storms
    la, lo = np.radians(lat), np.radians(lon)
    swirl = (np.sin(3 * lo + 2.2 * np.sin(2 * la) + 0.04 * t) * np.sin(7 * la + 1.7 * np.sin(4 * lo + 1))
             + 0.6 * np.sin(11 * lo - 5 * la + np.sin(6 * la)) * np.sin(9 * la + 2 * np.sin(5 * lo)))
    belt = 0.50 * np.exp(-(lat / 9) ** 2) + 0.70 * np.exp(-((np.abs(lat) - 52) / 13) ** 2) + 0.16
    cloud = swirl > 1.25 - 1.3 * belt
    ink = np.where(cloud[:, None], SNOW, ink)
    shade = np.where(cloud, 0.92 + 0.30 * np.clip(sun, 0, 1), shade)
    # the air thickens towards the edge: everything fades to its blue there
    haze = (1 - np.clip(-(p * unit(rays[hit])).sum(1), 0, 1)) ** 3
    ink = ink + (AIR - ink) * 0.75 * haze[:, None]
    shade = shade + 0.35 * haze
    ink = ink + (DAWN - ink) * 0.55 * (1 - np.abs(2 * day - 1))[:, None] * (day > 0.02)[:, None]     # dawn along the line
    lit = day > 0.25
    part[hit[lit]] = np.where(ice, ICE, np.where(land, LAND, OCEAN))[lit]
    lum[hit[lit]] = (shade * (0.70 + 0.30 * day))[lit]
    rgb[hit[lit]] = ink[lit]
    # city lights on the night side, once the camera is high enough to see them
    fine = np.sin(np.floor(lat / 0.03) * 12.9898 + np.floor(lon / 0.03) * 78.233) * 43758.5453 % 1.0   # a hash of the spot
    stray = (np.stack([fine, fine * 7.31 % 1.0]) - 0.5) * 0.5                   # towns have ragged edges, not square ones
    r, c = np.clip(((90 - lat - stray[0]) * 2).astype(int), 0, 359), ((lon + stray[1] + 180) * 2).astype(int) % 720
    seen = float(smooth((high - 15) / 60))
    twinkle = 0.75 + 0.25 * np.sin(t * 5 + hsh[hit] * 1.7)
    wide = tt * 2 * 0.4 / 72 / R_EARTH * 57.3                   # how many degrees of ground one letter covers
    town = LIGHTS[r, c] & (day < 0.2) & (seen > 0.05) & (fine < np.clip(wide / 0.4, 0.07, 1.0))
    big = town & BIG_LIGHTS[r, c]
    glyph[hit[town]] = np.where(big, C("*"), C("."))[town]
    lum[hit[town]] = (np.where(big, 1.25, 0.95) * twinkle * seen)[town]
    rgb[hit[town]] = CITY
    # the glow of the pad on the ground beneath the rocket, while it is still near
    spot = np.linalg.norm(p * R_EARTH - PAD, axis=1) * 1000.0
    heat = np.clip(1 - spot / 15.0, 0, 1) * float(1 - smooth((t - 3.4) / 1.6)) * (0.8 + 0.2 * np.sin(t * 31 + hsh[hit]))
    hot = heat > 0.06
    glyph[hit[hot]] = FILL[np.clip((heat * 4).astype(int), 0, 3), (hsh[hit] + int(t * 12)) % 12][hot]
    lum[hit[hot]] = (0.25 + 1.0 * heat)[hot]
    rgb[hit[hot]] = FIRE[np.clip((heat * 3.6).astype(int), 0, 3)][hot]
    # the skin of air, seen edge on beyond the horizon: brightest just above the ground
    miss = np.flatnonzero((disc <= 0) & (b < 0))
    reach = np.sqrt(np.maximum(eye @ eye - b[miss] ** 2 / a[miss], 0)) - R_EARTH    # how far over the horizon the ray passes
    air = miss[reach < ATMOSPHERE]
    v = reach[reach < ATMOSPHERE] / ATMOSPHERE
    near = unit(eye - (b[air] / a[air])[:, None] * rays[air])   # the point of the Earth the ray skims over
    sun = near @ SUN
    day = smooth((sun + 0.30) / 0.36)
    glow = (1 - v) ** 2.4 * (0.20 + 1.15 * day) * float(smooth((high - 2) / 60))
    tint = AIR + (DAWN - AIR) * (np.clip(1 - np.abs(sun + 0.08) / 0.22, 0, 1) * (1 - 0.6 * v))[:, None]
    ok = glow > 0.24
    glyph[air[ok]] = FILL[np.clip((glow * 3.2).astype(int), 0, 3), (hsh[air] + int(t * 3)) % 12][ok]
    lum[air[ok]] = np.minimum(0.2 + glow, 1.3)[ok]
    rgb[air[ok]] = (tint + (WHITE - tint) * np.clip(glow - 0.8, 0, 1)[:, None])[ok]
    return part, lum, rgb, glyph, depth, hit


N_STARS = 9000                                  # over the whole sky: a couple of hundred in view at a time
STAR_AT = unit(np.random.default_rng(5).normal(size=(N_STARS, 3)))
STAR_SEED = np.random.default_rng(6).random((N_STARS, 4))
FLASHERS = 0.972                                # the few stars above this (of 0..1) flash now and then
SPARK_SEED = np.random.default_rng(8).random((110, 5))
PATH_T = np.linspace(T_LIFT, T_CUTOFF, 1600)
PATH = np.array([position(t)[0] for t in PATH_T])               # the way it flew: its trail of smoke hangs along this


def put(char, col, y, x, ch, rgb, k):
    if 0 <= y < char.shape[0] and 0 <= x < char.shape[1]:
        char[y, x], col[y, x] = C(ch), np.asarray(rgb) * k


def flare(char, col, cy, cx, reach, rgb, strength=1.0, streak=0):
    # a four-pointed flare: long arms sideways and up/down, short diagonals; `streak` stretches
    # the sideways arms into the long flat flare of a film lens
    rows, cols = char.shape
    for dist in range(1, max(reach, streak) + 1):
        arms = [(0, 1, "-"), (0, -1, "-")]
        if dist <= reach:
            arms += [(1, 0, "|"), (-1, 0, "|")]
        if dist <= reach // 2:
            arms += [(1, 1, "\\"), (-1, -1, "\\"), (1, -1, "/"), (-1, 1, "/")]
        for dy, dx, ch in arms:
            far = max(reach, streak) if dy == 0 else reach
            k = (1 - dist / (far + 1)) * strength * (0.7 if dx and dy else 1.0)
            yy, xx = cy + dy * dist, cx + dx * dist * (2 if dy == 0 else 1)
            if 0 <= yy < rows and 0 <= xx < cols and col[yy, xx].max() < k:
                char[yy, xx], col[yy, xx] = C(ch), rgb * k
    put(char, col, cy, cx, "*", rgb, 1.3 * strength)


def stars(char, col, basis, lens, aspect, t, free, front, k):
    # the stars: fixed in the sky, so they slide as the camera turns. They go only where nothing
    # else is (`free`), the brightest also in front of the galaxy (`front`). A few of them flash:
    # a flare that swells and is gone.
    rows, cols = char.shape
    x, y, z = project(STAR_AT, np.zeros(3), basis, lens, cols, rows, aspect)
    ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
    share = min(1.0, (0.29 / lens) ** 2)                        # a wide lens takes in more sky: show fewer of them
    ok = np.flatnonzero((z > 0) & (ix >= 0) & (ix < cols) & (iy >= 0) & (iy < rows) & (STAR_SEED[:, 3] < share))
    ok = ok[free[iy[ok], ix[ok]] | (front[iy[ok], ix[ok]] & (STAR_SEED[ok, 2] > 0.55))]
    tw = 0.5 + 0.5 * np.sin(t * (1 + 3 * STAR_SEED[ok, 0]) + STAR_SEED[ok, 1] * 40)
    big = STAR_SEED[ok, 2] * tw
    char[iy[ok], ix[ok]] = np.where(big > 0.72, C("*"), np.where(big > 0.38, C("+"), C(".")))
    col[iy[ok], ix[ok]] = STAR_INK[ok % 3] * (0.30 + 0.70 * big)[:, None] * k
    for i in ok[STAR_SEED[ok, 2] > FLASHERS]:
        flash = max(0.0, np.sin(t * (1.1 + 1.6 * STAR_SEED[i, 0]) + STAR_SEED[i, 1] * 40)) ** 10
        clear = free[max(iy[i] - 4, 0):iy[i] + 5, max(ix[i] - 9, 0):ix[i] + 10].all()      # room for its rays
        if flash > 0.06 and clear:
            flare(char, col, iy[i], ix[i], int(1.5 + 3.5 * flash), STAR_INK[i % 3] * 0.4 + WHITE * 0.6, (0.45 + 0.55 * flash) * k,
                  streak=int(7 * flash))


def write(char, col, y, x, text, rgb, k):
    for i, ch in enumerate(text):
        put(char, col, y, x + i, ch, rgb, k)


# the solar system as a picture. True to scale it is all dots (every planet smaller than one
# letter), so here it is drawn the way it is in books: the planets big and close together, in the
# right order, each a ball lit by the sun. Sizes and distances are in units of this picture's own.
SUN_R = 13.0
# (name, radius of its orbit, its own radius, degrees round its orbit, when it comes into view
#  (seconds after T_COSMOS))
ORRERY = [("Mercury", 20.0, 1.00, 5, 1.9), ("Venus", 24.5, 1.50, -4, 1.5), ("Earth", 29.5, 1.60, 0, 0.0),
          ("Mars", 34.5, 1.25, 4, 1.6), ("Jupiter", 53.0, 4.80, -1, 2.3), ("Saturn", 68.0, 3.90, 1, 2.7),
          ("Uranus", 81.0, 2.50, -2, 3.1), ("Neptune", 92.0, 2.40, 1, 3.4)]
BELTS = [(39.0, 44.5, 420, 2.1), (101.0, 111.0, 600, 3.6)]     # rocks: (from, to, how many, when they come into view)
POSTER = (57.0, 40.0, 600.0, 34.6)                              # the picture is seen from: degrees round, degrees above
                                                                # the planets' plane, this far off; half its height
BELT_SEED = np.random.default_rng(15).random((1100, 4))
ROCK = np.array([0.86, 0.66, 0.36])
T_ORRERY = (1.0, 3.8, 6.8, 8.6)                                 # seconds after T_COSMOS: in, the picture, pulling away, out
SUN_INK = np.array([[1.00, 0.30, 0.06], [1.00, 0.55, 0.10], [1.00, 0.80, 0.25], [1.00, 0.97, 0.80]])
PLANET_INK = {                                                  # each planet's two colours
    "Mercury": ((0.78, 0.74, 0.68), (0.52, 0.50, 0.48)), "Venus": ((1.00, 0.88, 0.58), (0.92, 0.66, 0.34)),
    "Mars": ((1.00, 0.42, 0.22), (0.70, 0.24, 0.14)), "Jupiter": ((1.00, 0.86, 0.64), (0.90, 0.50, 0.26)),
    "Saturn": ((1.00, 0.88, 0.60), (0.86, 0.68, 0.42)), "Uranus": ((0.62, 0.94, 0.96), (0.46, 0.80, 0.90)),
    "Neptune": ((0.30, 0.48, 1.00), (0.16, 0.28, 0.86))}


def orrery_place(k, t):
    name, far, size, where, since = ORRERY[k]
    w = np.radians(where) + 0.012 * (t - T_COSMOS) * (20.0 / far)       # they creep round the sun
    return far * (np.cos(w) * ECL_X + np.sin(w) * ECL_Y)


def orrery_stations():
    # the four places the camera passes through: leaving the Earth, the picture, the picture a
    # little later, and far out above it all. Each: what it looks at, from which way, how far,
    # which way is up, the lens.
    eye, basis, lens = far_camera(T_COSMOS + T_ORRERY[0])       # where the real camera has got to
    home = orrery_place(2, T_COSMOS + T_ORRERY[0])
    start = (home, unit(eye), np.log10(ORRERY[2][2] * np.linalg.norm(eye) / R_EARTH), basis[1], lens)
    out = []
    for turn, zoom in ((0.0, 1.0), (-5.0, 0.94)):               # the picture, and the same a little later: drifting round
        az, el = np.radians(POSTER[0] + turn), np.radians(POSTER[1])
        way = unit(np.cos(el) * (-np.sin(az) * ECL_X - np.cos(az) * ECL_Y) + np.sin(el) * ECL_UP)
        # seen from far off through a long lens, so that near and far planets keep their sizes
        out.append((46.0 * ECL_X, way, np.log10(POSTER[2]), ECL_UP, POSTER[3] * zoom / POSTER[2]))
    eye, basis, lens = far_camera(T_COSMOS + T_ORRERY[3])       # ...and where the real camera takes over again
    end = (np.zeros(3), unit(eye - SUN_AT), np.log10(45000.0), basis[1], lens)
    return [start] + out + [end]


def orrery_camera(t):
    tau = t - T_COSMOS
    i = int(np.clip(np.searchsorted(T_ORRERY, tau, side="right") - 1, 0, 2))
    u = np.clip((tau - T_ORRERY[i]) / (T_ORRERY[i + 1] - T_ORRERY[i]), 0, 1)
    u = u if i == 1 else smooth(u)                              # gliding in and away; drifting in between
    a, b = STATIONS[i], STATIONS[i + 1]
    look, lens = a[0] + (b[0] - a[0]) * u, a[4] * (b[4] / a[4]) ** u
    way, up = unit(a[1] + (b[1] - a[1]) * u), unit(a[3] + (b[3] - a[3]) * u)
    eye = look + 10 ** (a[2] + (b[2] - a[2]) * u) * way
    fwd = unit(look - eye)
    right = unit(np.cross(fwd, up))
    return eye, np.stack([right, np.cross(right, fwd), fwd]), lens


def paint_planet(name, n, t):
    # the face of a planet: colour and extra brightness for every point on it (n: which way the
    # surface faces there). Bands for the giants, a red spot, caps of ice, the real map for the Earth.
    lat = np.arcsin(np.clip(n @ ECL_UP, -1, 1))
    lon = np.arctan2(n @ ECL_Y, n @ ECL_X) + 0.5 * (t - T_COSMOS)       # they turn
    if name == "Earth":
        land = is_land(np.degrees(lat), (np.degrees(lon) + 180) % 360 - 180)
        ink = np.where(land[:, None], GRASS, SEA)
        cloud = np.sin(3 * lon + 2.2 * np.sin(2 * lat)) * np.sin(7 * lat + 1.7 * np.sin(4 * lon + 1)) > 0.45
        ink = np.where((cloud | (np.abs(lat) > 1.2))[:, None], SNOW, ink)
        return ink, 0.12 * land + 0.25 * cloud
    light, dark = (np.array(c) for c in PLANET_INK[name])
    if name == "Jupiter":
        band = np.sin(11 * lat + 0.5 * np.sin(3 * lon))
        spot = ((np.angle(np.exp(1j * (lon - 1.0))) / 0.34) ** 2 + ((lat + 0.36) / 0.13) ** 2) < 1     # the great red spot
        ink = np.where((band > 0.1)[:, None], light, dark)
        return np.where(spot[:, None], (0.96, 0.30, 0.20), ink), 0.16 * (band > 0.1) + 0.2 * spot
    if name == "Saturn":
        band = np.sin(9 * lat)
        return np.where((band > 0)[:, None], light, dark), 0.12 * (band > 0)
    if name == "Mars":
        patch = np.sin(4 * lon + 2 * np.sin(3 * lat)) * np.cos(2.5 * lat) > 0.35
        ink = np.where(patch[:, None], dark, light)
        return np.where((np.abs(lat) > 1.25)[:, None], SNOW, ink), -0.1 * patch
    swirl = np.sin(6 * lat + 1.5 * np.sin(2 * lon + 4 * lat)) > 0.2      # the rest: soft streaks of cloud, or craters
    return np.where(swirl[:, None], light, dark), 0.10 * swirl


def orrery(t, cols, rows, aspect, cell):
    tau = t - T_COSMOS
    eye, basis, lens = orrery_camera(t)
    sx, sy, hsh = grid(rows, cols)
    rays = basis[2] + np.outer(sx * lens * aspect, basis[0]) + np.outer(sy * lens, basis[1])
    n_rays = len(rays)
    part, lum, glyph = np.full(n_rays, -1), np.zeros(n_rays), np.full(n_rays, -1)
    rgb, depth = np.zeros((n_rays, 3)), np.full(n_rays, np.inf)

    def over(idx, dist, prt, L, ink, own):
        m = dist < depth[idx]
        idx = idx[m]
        depth[idx], part[idx], lum[idx], rgb[idx], glyph[idx] = dist[m], np.broadcast_to(prt, m.shape)[m], L[m], ink[m], own[m]

    # the sun: a ball of fire, white-hot in the middle, red at the edge, seething; and its glow
    # just beyond the edge
    hit, dist, _, n = hit_balls(eye, rays, np.zeros((1, 3)), np.array([SUN_R]))
    if len(hit):
        face = np.clip(-(n * unit(rays[hit])).sum(1), 0, 1)                 # 1 in the middle of the disc, 0 at its edge
        seethe = 0.5 + 0.5 * np.sin(n @ ECL_X * 19 + t * 2.3) * np.sin(n @ ECL_UP * 23 - t * 1.7) * np.sin(n @ ECL_Y * 17 + t)
        heat = np.clip(0.18 + 0.72 * face ** 0.7 + 0.22 * seethe, 0, 0.999)
        level = (heat * 4).astype(int)
        over(hit, dist, -1, 0.72 + 0.62 * heat, SUN_INK[level], FILL[level, (hsh[hit] + int(t * 9)) % 12])
    a = (rays * rays).sum(1)
    b = -(rays @ eye)
    gap = np.sqrt(np.maximum(eye @ eye - b * b / a, 0)) / SUN_R - 1        # how far outside the sun's edge each ray passes
    halo = np.flatnonzero((b > 0) & (gap > 0) & (gap < 0.30) & ~np.isfinite(depth))
    glow = (1 - gap[halo] / 0.30) ** 2 * (0.75 + 0.25 * np.sin(t * 7 + hsh[halo]))
    halo, glow = halo[glow > 0.14], glow[glow > 0.14]
    over(halo, b[halo] / a[halo], -1, 0.30 + 0.75 * glow, SUN_INK[np.clip((glow * 2.6).astype(int), 0, 2)],
         FILL[np.clip((glow * 3).astype(int), 0, 2), (hsh[halo] + int(t * 9)) % 12])

    # the planets: each a ball, lit from the sun's side, with its own face; then rings
    centres = np.array([orrery_place(k, t) for k in range(len(ORRERY))])
    grown = np.array([float(smooth((tau - since) / 0.5)) for _, _, _, _, since in ORRERY])
    radii = np.array([size for _, _, size, _, _ in ORRERY]) * (0.35 + 0.65 * grown) * (grown > 0.02)
    hit, dist, which, n = hit_balls(eye, rays, centres, np.maximum(radii, 1e-6))
    if len(hit):
        ink, shade = np.zeros((len(hit), 3)), np.zeros(len(hit))
        for k, (name, _, _, _, _) in enumerate(ORRERY):
            m = which == k
            if m.any():
                ink[m], extra = paint_planet(name, n[m], t)
                sun = np.clip(-(n[m] * unit(centres[k])).sum(1), 0, 1)     # the sun is at the middle of everything
                shade[m] = 0.40 + 0.66 * sun ** 0.8 + extra
        over(hit, dist, which, shade, ink, np.full(len(hit), -1))
    for k, tilt, spans, tone in ((5, unit(ECL_UP + 0.42 * ECL_Y + 0.10 * ECL_X), ((1.28, 1.62), (1.70, 2.22)), PLANET_INK["Saturn"][0]),
                                 (6, unit(ECL_X + 0.25 * ECL_UP - 0.20 * ECL_Y), ((1.62, 1.74),), (0.80, 0.96, 1.0))):
        if radii[k] <= 1e-3:
            continue
        drop = rays @ tilt                                                  # where each ray crosses the ring's plane
        tt = ((centres[k] - eye) @ tilt) / np.where(np.abs(drop) < 1e-9, 1e-9, drop)
        away = np.linalg.norm(eye + tt[:, None] * rays - centres[k], axis=1) / radii[k]
        for lo, hi in spans:
            idx = np.flatnonzero((tt > 0) & (away > lo) & (away < hi))
            lit = 0.72 + 0.20 * np.sin(away[idx] * 40)                      # ringlets
            over(idx, tt[idx], 20 + k, lit, np.tile(tone, (len(idx), 1)) * (0.8 + 0.2 * (away[idx] < 1.9))[:, None],
                 np.full(len(idx), -1))

    # letters and outlines, as everywhere: filled by brightness, outlined where a ball ends
    shape2 = (rows, cols)
    prt, dep, own, L = part.reshape(shape2), depth.reshape(shape2), glyph.reshape(shape2), lum.reshape(shape2)
    solid = (prt >= 0) & (own < 0)
    pp, pd = np.pad(prt, 1, constant_values=-1), np.pad(dep, 1, constant_values=np.inf)
    edge, gx, gy = np.zeros(shape2, bool), np.zeros(shape2), np.zeros(shape2)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == dy == 0:
                continue
            nb, nz = pp[1 + dy:rows + 1 + dy, 1 + dx:cols + 1 + dx], pd[1 + dy:rows + 1 + dy, 1 + dx:cols + 1 + dx]
            out = solid & (nb != prt) & (nz > dep * 1.004)
            gx += dx * out
            gy += dy * out
            if dx == 0 or dy == 0:
                edge |= out
    h2 = hsh.reshape(shape2)
    level = np.clip(((L - 0.42) * 4.6).astype(int), 0, 3)
    char = np.where(own >= 0, own, np.where(solid, FILL[level, (h2 + (t * 4 + h2 % 11).astype(int)) % 12], 0))
    char = np.where(edge, outline_letter(gx, gy), char)
    bright = np.where(own >= 0, L, np.where(edge, np.maximum(0.85, L), np.clip(0.45 + 0.55 * L / 0.9, 0.45, 1.0)))
    col = rgb.reshape(rows, cols, 3) * np.where((prt >= 0) | (own >= 0), np.minimum(bright, 1.45), 0.0)[..., None]

    def dots(p, glyphs, ink, k):
        x, y, z = project(p, eye, basis, lens, cols, rows, aspect)
        ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
        ok = np.flatnonzero((ix >= 0) & (ix < cols) & (iy >= 0) & (iy < rows) & (z > 0) & (k > 0.04))
        ok = ok[z[ok] < dep[iy[ok], ix[ok]] * 1.0005]
        ok = ok[np.argsort(k[ok])]
        char[iy[ok], ix[ok]] = np.broadcast_to(glyphs, k.shape)[ok]
        col[iy[ok], ix[ok]] = np.broadcast_to(ink, (len(k), 3))[ok] * k[ok, None]

    # stars behind it all (always through the same lens, or the long lens of the picture would
    # leave hardly any in view)
    flares = []
    stars(char, col, basis, LENS0, aspect, t, char == 0, np.zeros(shape2, bool), 1.0)

    # the orbits, in strokes; and the two belts of rocks, each rock a speck going round
    seen = float(smooth((tau - T_ORRERY[0]) / 1.2))
    turn = np.linspace(0, TAU, 900)
    for k, (name, far, size, where, since) in enumerate(ORRERY):
        ring = far * (np.outer(np.cos(turn), ECL_X) + np.outer(np.sin(turn), ECL_Y))
        x, y, z = project(ring, eye, basis, lens, cols, rows, aspect)
        dots(ring, slope_char(np.gradient(x) * cell, -np.gradient(y)), STEEL, np.full(len(turn), 0.40 * seen * (0.3 + 0.7 * grown[k])))
    first = 0
    for lo, hi, count, since in BELTS:
        s = BELT_SEED[first:first + count]
        first += count
        far = lo + (hi - lo) * s[:, 0]
        w = s[:, 1] * TAU + 0.04 * (t - T_COSMOS) * (40.0 / far)
        rocks = far[:, None] * (np.outer(np.cos(w), ECL_X) + np.outer(np.sin(w), ECL_Y)) + np.outer((s[:, 2] - 0.5) * 1.6, ECL_UP)
        show = float(smooth((tau - since) / 0.8))
        dots(rocks, np.where(s[:, 3] > 0.8, C("o"), np.where(s[:, 3] > 0.45, C("*"), C("."))), ROCK,
             (0.45 + 0.55 * s[:, 3]) * show)

    # each planet flashes as it comes into view; its name, if wanted; the sun from far off is a flare
    for k, (name, far, size, where, since) in enumerate(ORRERY):
        x, y, z = project(centres[k][None], eye, basis, lens, cols, rows, aspect)
        new = float(np.sin(np.pi * grown[k])) if 0 < grown[k] < 1 else 0.0
        if new > 0.15 and z[0] > 0:
            flares.append((int(y[0]), int(x[0]), int(2 + 4 * new), new, WHITE))
        if LABELS and grown[k] > 0.6 and z[0] > 0:
            up_ = size / z[0] / lens * 0.5 * rows
            write(char, col, int(y[0] - up_) - 2, int(x[0] - len(name) / 2 + 0.5), name, np.array(PLANET_INK.get(name, ((0.5, 0.8, 1.0),))[0]), 0.7)
    x, y, z = project(np.zeros((1, 3)), eye, basis, lens, cols, rows, aspect)
    small = SUN_R / max(z[0], 1e-9) / lens * 0.5 * rows                     # the sun's radius on screen, in rows
    if z[0] > 0 and small < 1.5:
        flares.append((int(y[0]), int(x[0]), int(5 + 3 * small), 1.0, WHITE))
    for cy, cx, reach, strength, ink in flares:
        if 0 <= cy < rows and 0 <= cx < cols:
            flare(char, col, cy, cx, reach, ink, strength)

    moving = max(float(1 - smooth((tau - T_ORRERY[1] + 0.6) / 0.6)), float(smooth((tau - T_ORRERY[2]) / 0.5)))
    far = 10 ** climb(tau, COSMOS[:, 0], COSMOS[:, 1])
    away = f"{far:,.0f} km" if far < 1e7 else f"{far / 1e6:,.0f} million km" if far < 0.5 * AU else f"{far / AU:,.1f} AU"
    info = {"hud": f"the solar system      {away} from home", "letters": int((char > 0).sum()), "trail": TRAIL * (1 - 0.8 * moving)}
    return char, col, info


N_PASSING = 1500
PASSING_WAY = unit(np.random.default_rng(11).normal(size=(N_PASSING, 3)))
PASSING_FAR = 10 ** np.random.default_rng(12).uniform(12.6, 17.7, N_PASSING)       # km from the sun, every scale


def passing_stars(from_sun):
    # the sun's neighbours: stars at every distance from it, so that however far out the camera
    # is, some are just streaming past; returns where they are and how bright
    ratio = np.log10(PASSING_FAR / from_sun)
    k = np.clip(1 - np.abs(ratio + 0.3) / 0.8, 0, 1)
    return SUN_AT + PASSING_FAR[:, None] * PASSING_WAY, k


def galaxy(eye, rays, t, hsh, seen):
    # the galaxy, for every ray: where the ray crosses its disc, how bright the disc is there
    # (two spiral arms winding out, dust lanes along their inner edges, clumps), plus the glow of
    # the bulge in the middle; returns a glyph and a colour for every letter
    drop = rays @ GAL_UP
    tt = ((GAL_AT - eye) @ GAL_UP) / np.where(np.abs(drop) < 1e-9, 1e-9, drop)
    p = eye + tt[:, None] * rays - GAL_AT
    x, z = p @ GAL_X, p @ GAL_Z
    u = np.hypot(x, z) / GALAXY_R                                   # 0 at the centre, 1 at the edge
    th = np.arctan2(z, x) + GAL_SPIN * t
    wind = 2 * (th - np.log(np.maximum(u, 0.02) / 0.08) / np.tan(np.radians(GAL_PITCH)))   # where round the two arms
    arm = (0.5 + 0.5 * np.cos(wind)) ** 2.4 + 0.35 * (0.5 + 0.5 * np.cos(2 * wind + 1.3)) ** 3
    lane = (0.5 + 0.5 * np.cos(wind + 1.0)) ** 8 * smooth((u - 0.10) / 0.10) * (1 - smooth((u - 0.70) / 0.25))
    fall = np.exp(-u / 0.34) * (1 - smooth((u - 0.80) / 0.35)) * (tt > 0)
    grain = np.sin(np.floor(x / GALAXY_R * 70) * 12.9898 + np.floor(z / GALAXY_R * 70) * 78.233) * 43758.5453 % 1.0
    disc = 2.9 * fall * (0.12 + 1.15 * arm) * (0.70 + 0.60 * grain) * (1 - 0.72 * lane)
    # the bulge: how close each ray passes to the centre (it is a little flattened)
    s = ((GAL_AT - eye) * rays).sum(1) / (rays * rays).sum(1)
    q = eye + s[:, None] * rays - GAL_AT
    qn = q @ GAL_UP
    miss = np.sqrt(np.maximum((q * q).sum(1) - qn * qn, 0) + (qn / 0.62) ** 2) / GALAXY_R
    bulge = 1.9 * np.exp(-miss / 0.055) + 0.45 * np.exp(-miss / 0.16)
    light = np.minimum(disc + bulge, 1.7) * seen
    # colour: warm in the middle, blue along the arms, violet at the edge, brown in the dust
    ink = GAL_CORE + (ARM_BLUE - GAL_CORE) * smooth((u - 0.10) / 0.30)[:, None]
    ink = ink + (ARM_VIOLET - ink) * (0.75 * smooth((u - 0.50) / 0.45))[:, None]
    ink = ink + (DUST - ink) * np.clip(1.3 * lane, 0, 1)[:, None]
    ink = (ink * disc[:, None] + GAL_CORE * bulge[:, None]) / np.maximum(disc + bulge, 1e-9)[:, None]
    ink = ink + (WHITE - ink) * np.clip(light - 1.1, 0, 0.8)[:, None]
    level = np.clip((light * 3.6).astype(int), 0, 3)
    char = np.where(light > 0.12, FILL[level, (hsh + int(t * 3)) % 12], 0)
    col = ink * np.minimum(0.36 + 0.90 * light, 1.40)[:, None]
    # bright knots along the arms: pink clouds where stars are being born, and blue young stars
    spot = (grain * 17.0) % 1.0
    knot = (light > 0.12) & (spot < 0.085 * arm) & (u > 0.14) & (u < 0.95) & (lane < 0.3)
    char = np.where(knot, np.where(spot < 0.05 * arm, C("*"), C("+")), char)
    col = np.where(knot[:, None], np.where((spot < 0.05 * arm)[:, None], KNOT, ARM_BLUE + 0.2) * 1.15 * seen, col)
    return char, col


STATIONS = orrery_stations()


def frame(t, cols, rows, aspect, cell):
    if T_ORRERY[0] <= t - T_COSMOS < T_ORRERY[3]:                # in between, the picture of the solar system
        return orrery(t, cols, rows, aspect, cell)
    eye, basis, lens = camera(t)
    sx, sy, hsh = grid(rows, cols)
    rays = basis[2] + np.outer(sx * lens * aspect, basis[0]) + np.outer(sy * lens, basis[1])   # one ray per letter
    pos, axes = rocket(t)
    high = altitude(t)
    burning = float(1 - smooth((t - T_CUTOFF) / 0.4))           # the core's engine
    boost = float(1 - smooth((t - T_SEP + 0.1) / 0.2))          # the boosters' engines
    thin = float(smooth((high - 25) / 60))                      # how thin the air is: 1 = space
    in_sun = sunlit(pos)
    key = unit(-0.50 * basis[0] + 0.62 * basis[1] - 0.60 * basis[2])     # a light over the camera's left shoulder
    half = unit(key - basis[2])

    # the Earth first, then everything nearer on top of it
    far = np.linalg.norm(eye)                                   # how far the camera is from the Earth
    from_sun = np.linalg.norm(eye - SUN_AT)                     # ...and from the sun
    if far < 2e6:
        part, lum, rgb, glyph, depth, _ = earth_layer(eye, rays, t, hsh)
    else:                                                       # by now the Earth is smaller than a letter
        n = len(rays)
        part, lum, rgb, glyph, depth = np.full(n, -1), np.zeros(n), np.zeros((n, 3)), np.full(n, -1), np.full(n, np.inf)
    earth_depth = depth.copy()
    edge_of_earth = np.isfinite(depth).reshape(rows, cols)

    def over(idx, dist, prt, L, ink, own):
        # put something in front of what is already there, where it is nearer
        m = dist < depth[idx]
        idx = idx[m]
        depth[idx], part[idx], lum[idx], rgb[idx], glyph[idx] = dist[m], np.broadcast_to(prt, m.shape)[m], L[m], ink[m], own[m]

    # the moon
    hit, dist, _, n = hit_balls(eye, rays, MOON_AT[None], np.array([MOON_R])) if t < T_COSMOS + 0.5 else ([], 0, 0, 0)
    if len(hit):
        over(hit, dist, MOON, 0.50 + 0.62 * np.clip(n @ SUN, 0, 1), np.tile(MOONLIGHT, (len(hit), 1)), np.full(len(hit), -1))

    # the smoke rolling out from the pad, lit by the fire while it is near
    near_fire = float(1 - smooth((high - 0.25) / 0.9))
    if t < 9:
        centres, radii = smoke(t)
        hit, dist, which, n = hit_balls(eye, rays, centres, radii)
        if len(hit):
            to_fire = unit(pos - axes[1] * 0.004 - (eye + dist[:, None] * rays[hit]))
            away = np.linalg.norm(centres[which] - PAD, axis=1) * 1000.0
            reach = np.exp(-away / 48.0) * near_fire * burning      # the fire's light falls off with distance
            heat = reach * (0.16 + 0.84 * np.clip((n * to_fire).sum(1), 0, 1) ** 1.5)      # the side facing the fire is hot
            ink = FIRE[np.clip((heat * 4.2).astype(int), 0, 3)]
            seen = reach > 0.10                                     # unlit, it is lost in the dark
            over(hit[seen], dist[seen], SMOKE, (0.36 + 0.95 * heat)[seen], ink[seen], np.full(seen.sum(), -1))

    # the rocket: the core, and a booster on each side, which fall away tumbling after T_SEP
    since = t - T_SEP
    bodies = [(pos, axes, CORE_SHAPE, CORE_PLATES, paint_core, burning, CORE)]
    for side, prt in ((-1, BOOST_L), (1, BOOST_R)):
        origin, own_axes = pos + axes[0] * side * BOOSTER_OUT / 1000.0, axes
        if since > 0:
            # let go: drifting out sideways, falling behind, turning end over end
            origin = origin + (axes[0] * side * (9 * since + 14 * since ** 2) - axes[1] * 30 * since ** 2) / 1000.0
            turn = side * 0.9 * since ** 1.5
            own_axes = np.array([[np.cos(turn), np.sin(turn), 0], [-np.sin(turn), np.cos(turn), 0], [0, 0, 1]]) @ axes
        if since < 3.2:
            bodies.append((origin, own_axes, BOOSTER_SHAPE, BOOSTER_PLATES, paint_booster, boost, prt))
    size = ROCKET_LEN / 1000.0 / np.linalg.norm(pos - eye) / lens * 0.5 * rows       # the rocket's length, in rows
    if size > 2.5:
        for origin, own_axes, shape, plates, paint, firing, prt in bodies:
            hit, dist, kind, y, ang, n, fire = trace_body(eye, rays, origin, own_axes, shape, plates)
            if len(hit) == 0:
                continue
            ink, own = paint(kind, y, ang)
            dark = ink.sum(1) < 0.9                                 # black paint stays black
            shade = 0.56 + 0.44 * np.clip(n @ key, 0, 1) + 0.5 * np.clip(n @ half, 0, 1) ** 24
            shade += 0.55 * in_sun * np.clip(n @ SUN, 0, 1)
            ink = ink + (GOLD - ink) * 0.35 * in_sun * np.clip(n @ SUN, 0, 1)[:, None]      # sunlight is warm
            warm = firing * np.exp(-np.maximum(y, 0) / 14.0) * (1 - 0.7 * thin)             # the fire lights its lower end
            ink = ink + (FIRE[2] - ink) * np.clip(0.9 * warm, 0, 1)[:, None]
            shade = shade + 0.5 * warm
            shade = np.where(dark, 0.42, shade)
            ink[dark] = BLACK
            ink[fire], shade[fire], own[fire] = FIRE[3] * firing + BLACK * (1 - firing), 1.35, C("#")
            kind = np.where(kind == BELL, BELL, np.where(kind == FAIRING, FAIRING, prt))
            over(hit, dist, kind, shade, ink, own)

    # the fire: a jet from each engine. Short and fat in thick air, long, wide and blue in space.
    # On the pad it has nowhere to go but sideways: two more jets along the ground, east and west
    ground = (np.linalg.norm(pos) - R_EARTH) * 1000.0               # metres of air under the engines
    reach = (48 + 34 * smooth((t - T_LIFT) / 2.0)) * (1 + 1.6 * thin)
    jets = [(pos, -axes[1], min(ground + 3.0, reach), 1.9 * (1 + 1.8 * thin), burning)]
    jets += [(o, -a[1], min(ground + 3.0, 0.8 * reach), 1.45 * (1 + 1.8 * thin), f * (since < 0.25))
             for o, a, _, _, _, f, _ in bodies[1:]]
    blast = burning * float(1 - smooth((ground - 10) / 50))
    if blast > 0.05:
        foot = unit(pos) * (R_EARTH + 0.0012)
        jets += [(foot, unit(side * PAD_AXES[0] + 0.10 * U0), 40 * blast, 1.5, blast) for side in (-1, 1)]
    for n_jet, (start, way, length, wide, firing) in enumerate(jets):
        if firing < 0.05 or size < 0.4:
            continue
        deep, v, dist = plume(eye, rays, start, way, length / 1000.0, wide / 1000.0, t, 1.7 * n_jet)
        heat = deep * (1 - 0.55 * v) * firing * (0.86 + 0.14 * np.sin(t * 53 + hsh * 0.7))
        idx = np.flatnonzero(heat > 0.05)
        h = heat[idx]
        level = np.clip((h * 4.4).astype(int), 0, 3)
        ink = FIRE[level] + (VACUUM - FIRE[level]) * (0.75 * thin * (1 - h))[:, None]
        over(idx, dist[idx], -1, (0.55 + 0.95 * h) * (1 - 0.35 * thin), ink, FILL[level, (hsh[idx] + int(t * 20)) % 12])

    # letters and outlines: solids are filled with letters by brightness and outlined where they
    # end or meet another part; everything that glows keeps its own glyph and brightness
    shape2 = (rows, cols)
    prt, dep, own, L = part.reshape(shape2), depth.reshape(shape2), glyph.reshape(shape2), lum.reshape(shape2)
    body = prt >= 0
    solid = body & (own < 0)
    pp, pd = np.pad(prt, 1, constant_values=-1), np.pad(dep, 1, constant_values=np.inf)
    pe = np.pad(edge_of_earth, 1, mode="edge")
    bare_earth = edge_of_earth & (depth == earth_depth).reshape(shape2)      # the Earth, with nothing in front of it
    billow = prt == SMOKE                                       # smoke: every ball of it gets its own outline
    edge, rim = np.zeros(shape2, bool), np.zeros(shape2, bool)
    gx, gy = np.zeros(shape2), np.zeros(shape2)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == dy == 0:
                continue
            nb, nz = pp[1 + dy:rows + 1 + dy, 1 + dx:cols + 1 + dx], pd[1 + dy:rows + 1 + dy, 1 + dx:cols + 1 + dx]
            off = bare_earth & ~pe[1 + dy:rows + 1 + dy, 1 + dx:cols + 1 + dx]         # the Earth's own edge
            other = (nb != prt) | billow
            jump = nz > dep * np.where(billow, 1.03, 1.004)
            out = solid & ((other & jump) | (SEAM[np.maximum(prt, 0), np.maximum(nb, 0)] & (nb >= 0))) | off
            gx += dx * out
            gy += dy * out
            if dx == 0 or dy == 0:
                edge |= out
                rim |= off
    h2 = hsh.reshape(shape2)
    level = np.clip(((L - 0.42) * 4.6).astype(int), 0, 3)
    inside = FILL[level, (h2 + (t * 4 + h2 % 11).astype(int)) % 12]
    char = np.where(own >= 0, own, np.where(body, inside, 0))
    char = np.where(edge & (solid | rim) & (own < 0), outline_letter(gx, gy), char)
    bright = np.where(own >= 0, L, np.where(edge, np.maximum(0.85, L), np.clip(0.45 + 0.55 * L / 0.9, 0.45, 1.0)))
    col = rgb.reshape(rows, cols, 3) * np.where(body | (own >= 0), np.minimum(bright, 1.45), 0.0)[..., None]
    # the Earth's edge where nothing else is drawn: a line of air, bright where the sun reaches it
    bare = rim & (own < 0)
    if bare.any():
        look = unit(rays).reshape(rows, cols, 3)[bare]
        mid = unit(eye + (-(look @ eye))[:, None] * look)       # the point of the limb each of those rays grazes
        sun = mid @ SUN
        day = smooth((sun + 0.30) / 0.36)
        tint = AIR + (DAWN - AIR) * np.clip(1 - np.abs(sun + 0.08) / 0.22, 0, 1)[:, None]
        col[bare] = tint * (0.30 + 0.90 * day)[:, None]

    def dots(p, glyphs, ink, k):
        # loose points of light, hidden where something solid is in front of them
        x, y, z = project(p, eye, basis, lens, cols, rows, aspect)
        ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
        ok = np.flatnonzero((ix >= 0) & (ix < cols) & (iy >= 0) & (iy < rows) & (z > 0) & (k > 0.04))
        ok = ok[z[ok] < dep[iy[ok], ix[ok]] * 1.0005]
        ok = ok[np.argsort(k[ok])]
        char[iy[ok], ix[ok]] = np.broadcast_to(glyphs, k.shape)[ok]
        col[iy[ok], ix[ok]] = np.broadcast_to(ink, (len(k), 3))[ok] * k[ok, None]

    # the galaxy, once the camera is far enough out to see its shape
    in_galaxy = np.zeros((rows, cols), bool)
    shape_seen = float(smooth((np.log10(from_sun) - 16.5) / 1.1))
    if shape_seen > 0.01:
        g_char, g_col = galaxy(eye, rays, t, hsh, shape_seen)
        in_galaxy = ((g_char > 0) & (char.ravel() == 0)).reshape(rows, cols)
        char[in_galaxy], col[in_galaxy] = g_char.reshape(rows, cols)[in_galaxy], g_col.reshape(rows, cols, 3)[in_galaxy]

    # stars, where nothing else is (the brightest also in front of the galaxy)
    stars(char, col, basis, lens, aspect, t, (char == 0) & ~edge_of_earth, in_galaxy, 0.55 + 0.45 * thin)

    # the sun's neighbours streaming past, on the way out to the galaxy
    if from_sun > 2e11 and shape_seen < 0.98:
        near, k = passing_stars(from_sun)
        dots(near, np.where(k > 0.7, C("*"), np.where(k > 0.35, C("+"), C("."))), STAR_INK[np.arange(N_PASSING) % 3],
             (0.25 + 0.85 * k) * (k > 0.02) * (1 - shape_seen))

    # the tower, in strokes, lit by the fire; each stroke drawn along its own direction on screen
    flares = []
    if t < 6.5:
        world = PAD + (TOWER_PTS @ PAD_AXES) / 1000.0
        x, y, z = project(world, eye, basis, lens, cols, rows, aspect)
        x2, y2, _ = project(world + (TOWER_WAY @ PAD_AXES) * 1e-4, eye, basis, lens, cols, rows, aspect)
        warm = np.exp(-np.linalg.norm(world - pos, axis=1) * 1000 / 45.0) * burning
        ink = STEEL + (FIRE[2] - STEEL) * np.clip(1.5 * warm, 0, 1)[:, None]
        dots(world, slope_char((x2 - x) * cell, y - y2), ink, np.minimum(0.52 + 0.8 * warm, 1.1))
        for n_lamp, lamp in enumerate(LAMPS):                       # a red beacon on the mast, floodlights round the pad
            beat = 0.5 + 0.5 * np.sin(t * 6 + n_lamp * 2.1)
            flares.append((PAD + (lamp @ PAD_AXES) / 1000.0, 2 + (n_lamp > 0), 0.6 + 0.4 * beat, RED if n_lamp == 0 else WHITE, 0))

    # sparks thrown out along the ground while it sits on the pad burning
    if t < T_LIFT + 1.6:
        age = (t * (0.9 + 0.5 * SPARK_SEED[:, 0]) + SPARK_SEED[:, 1]) % 1.0
        az = SPARK_SEED[:, 2] * TAU
        out = (8 + 58 * SPARK_SEED[:, 3]) * age
        local = np.stack([out * np.cos(az), -1000 * PAD_H + 0.5 + 26 * SPARK_SEED[:, 4] * age * (1 - age) * 4, out * np.sin(az)], 1)
        dots(PAD + (local @ PAD_AXES) / 1000.0, np.where(age < 0.5, C("*"), C(".")), FIRE[2] + (WHITE - FIRE[2]) * (1 - age)[:, None],
             (1.25 - age) * float(1 - smooth((t - T_LIFT - 0.8) / 0.8)))

    # the trail: the smoke it left hangs along the way it flew, hot near the engines, then cooling
    if t > T_LIFT + 0.4 and far < 3e5:
        flown = PATH_T < min(t, T_CUTOFF) - 0.02
        if flown.sum() > 2:
            gone = np.linalg.norm(pos - PATH[flown], axis=1)        # how far behind the rocket each point is
            want = 0.03 * 1.006 ** np.arange(2600)                  # sample it finely near the rocket, coarsely far back
            want = want[(want > gone.min()) & (want < gone.max())]
            way = PATH[flown][::-1]
            trail = np.stack([np.interp(want, gone[::-1], way[:, i]) for i in range(3)], 1)
            x, y, z = project(trail, eye, basis, lens, cols, rows, aspect)
            hot = np.exp(-want / (0.25 + 0.5 * np.linalg.norm(pos - eye))) * burning
            ink = HAZE + (GOLD - HAZE) * 0.4 * in_sun
            ink = ink + (FIRE[1] - ink) * hot[:, None]
            if len(want) > 2:
                dots(trail, slope_char(np.gradient(x) * cell, -np.gradient(y)), ink, 0.42 + 0.6 * hot)

    # the rocket seen from far away: a stroke, then a spark with a flare; the satellite's glint
    if size <= 6 and far < 3e5:
        x, y, z = project(pos[None], eye, basis, lens, cols, rows, aspect)
        if size > 0.8:
            stroke = pos + np.outer(np.linspace(0, ROCKET_LEN / 1000.0, 40), axes[1])
            x2, y2, _ = project(stroke[-1:], eye, basis, lens, cols, rows, aspect)
            dots(stroke, slope_char((x2 - x) * cell, y - y2), HULL, np.full(40, 1.0))
        glow = 0.55 + 0.45 * burning + 0.3 * in_sun
        flares.append((pos, int(2 + 2 * burning + 2 * in_sun * (size < 1)), glow, FIRE[3] if burning > 0.3 else WHITE, 0))
    freed = t - T_DEPLOY
    if 0 < freed < 2.5:
        pop = float(np.clip(1 - freed / 1.2, 0, 1))
        flares.append((pos + basis[1] * 0.012 * freed * np.linalg.norm(pos - eye),     # drifting clear of the rocket
                       int(2 + 5 * pop), 0.5 + 0.5 * pop, WHITE, int(8 * pop)))
    if 0 <= since < 0.5:                                            # the flash as the boosters let go
        flares.append((pos + axes[1] * 0.02, int(3 + 5 * (1 - since / 0.5)), 1 - since / 0.5, WHITE, 0))

    # the sun: when it clears the edge of the Earth, a flare with a long flat streak; from further
    # out it shrinks, until it is one star among the others
    x, y, z = project(SUN_AT[None], eye, basis, lens, cols, rows, aspect)
    along = eye @ SUN
    clear = (np.linalg.norm(eye - along * SUN) - R_EARTH - 30) / 400.0 if along < 0 and far < 1e6 else 1.0
    up_ = float(smooth(clear))
    cx, cy = int(x[0]), int(y[0])
    small = 1 - 0.45 * float(smooth((np.log10(far) - 6.5) / 2)) - 0.40 * float(smooth((np.log10(far) - 11) / 2.5))
    if z[0] > 0 and up_ > 0.02 and -8 < cx < cols + 8 and -8 < cy < rows + 8 and shape_seen < 0.5:
        pulse = 0.9 + 0.1 * np.sin(t * 9)
        flare(char, col, cy, cx, int((3 + 11 * up_ * pulse) * small), GOLD + (WHITE - GOLD) * up_, 0.6 + 0.4 * up_,
              streak=int(26 * up_ * small ** 3))
        for dx in (-1, 0, 1):
            put(char, col, cy, cx + dx, "@" if dx == 0 else "#", WHITE, 1.4 * up_)

    home = float(smooth((shape_seen - 0.5) / 0.5))                  # in the galaxy: a spark where the sun is
    if home > 0.05:
        beat = 0.75 + 0.25 * np.sin(t * 5)
        flares.append((SUN_AT, 2, home * beat, GOLD, 0))
        if LABELS and 0 <= cy < rows:
            write(char, col, cy - 1, cx + 3, "Earth", GOLD, 0.8 * home)

    for p, reach, strength, ink, streak in flares:
        x, y, z = project(np.asarray(p)[None], eye, basis, lens, cols, rows, aspect)
        cy, cx = int(y[0]), int(x[0])
        if z[0] > 0 and 0 <= cy < rows and 0 <= cx < cols and z[0] <= dep[cy, cx] * 1.001:
            flare(char, col, cy, cx, reach, ink, strength, streak)

    # while the camera flies back the whole picture moves: no trails then, or everything smears
    # (but among the stars the trails are wanted: they streak)
    flying = float(smooth((t - 8.2) / 0.6) * (1 - smooth((t - 13.6) / 1.0)))
    flying = max(flying, float(smooth((t - T_COSMOS - 0.2) / 0.6) * (t < T_COSMOS + 2)))
    stage = "ignition" if t < T_LIFT else "lift-off" if t < T_SEP else "second stage" if t < T_CUTOFF else "in orbit"
    alt = f"{high * 1000:,.0f} m" if high < 1 else f"{high:,.0f} km"
    hud = f"{stage}      altitude {alt}      downrange {downrange(t) * R_EARTH:,.0f} km"
    if t > T_COSMOS + 0.6:
        stage = "the Earth" if far < 3e7 else "the solar system" if from_sun < 2e12 else "the stars" if shape_seen < 0.5 \
            else "the Milky Way"
        away = f"{far:,.0f} km" if far < 1e7 else f"{far / 1e6:,.0f} million km" if far < 0.5 * AU else \
            f"{far / AU:,.1f} AU" if far < 0.05 * LY else f"{far / LY:,.1f} light-years" if far < 100 * LY else \
            f"{far / LY:,.0f} light-years"
        hud = f"{stage}      {away} from home"
    info = {"hud": hud, "letters": int((char > 0).sum()), "trail": TRAIL * (1 - 0.8 * flying)}
    return char, col, info


# window

TITLE = "ASCII Universe"
CW, CH, FONT_PX = 9, 14, 15
COLS, ROWS = 88, 74
W, H = COLS * CW, ROWS * CH
MONO = "consolas,menlo,dejavusansmono,couriernew,monospace"
HINT = "Space pause · R restart · S screenshot · Esc quit"
TRAIL = 0.45                                    # how much of the last frame stays behind (motion trails)


class Renderer:
    def __init__(self, cols=COLS, rows=ROWS, cw=CW, ch=CH, font_px=FONT_PX, hud_px=15, hint=True):
        self.cols, self.rows, self.cw, self.ch = cols, rows, cw, ch
        self.w, self.h = cols * cw, rows * ch
        font = pygame.font.SysFont(MONO, font_px)
        atlas = []
        for code in range(32, 127):
            s = pygame.Surface((cw, ch))
            g = font.render(chr(code), True, (255, 255, 255))
            s.blit(g, ((cw - g.get_width()) // 2, (ch - g.get_height()) // 2))
            atlas.append(pygame.surfarray.array3d(s).transpose(1, 0, 2))
        self.atlas = np.stack(atlas)                            # glyph, CH, CW, 3
        self.art = pygame.Surface((self.w, self.h))
        self.trail = pygame.Surface((self.w, self.h))
        self.out = pygame.Surface((self.w, self.h))
        self.small = pygame.font.SysFont(MONO, hud_px)
        self.hud_gap = int(hud_px * 1.45)
        self.hint = hint
        self.last_t = None

    @staticmethod
    def blur(src, size, radius):
        small = pygame.transform.smoothscale(src, size)
        if hasattr(pygame.transform, "gaussian_blur"):
            small = pygame.transform.gaussian_blur(small, max(1, radius))
        return small

    def glow(self, src):
        # a tight glow and a wide one; the wide one is made from the tight one
        w, h = self.w, self.h
        tight = self.blur(src, (w // 4, h // 4), 2)
        wide = self.blur(tight, (w // 8, h // 8), 3)
        for layer, amount in ((tight, 0.75), (wide, 0.45)):
            layer = pygame.transform.smoothscale(layer, (w, h))
            layer.fill((int(255 * amount),) * 3, special_flags=pygame.BLEND_MULT)
            self.out.blit(layer, (0, 0), special_flags=pygame.BLEND_ADD)

    def draw(self, t):
        w, h = self.w, self.h
        char, col, info = frame(t, self.cols, self.rows, w / h, self.cw / self.ch)
        pygame.surfarray.blit_array(self.art, self.atlas[char].transpose(1, 3, 0, 2, 4).reshape(w, h, 3))
        tint = pygame.surfarray.make_surface((np.clip(col, 0, 1) * 255).astype(np.uint8).transpose(1, 0, 2))
        self.art.blit(pygame.transform.scale(tint, (w, h)), (0, 0), special_flags=pygame.BLEND_MULT)
        if self.last_t is None or t < self.last_t:
            self.trail.fill((0, 0, 0))                          # restarted: no trails from before
        self.last_t = t
        self.trail.fill((int(info["trail"] * 255),) * 3, special_flags=pygame.BLEND_MULT)
        self.trail.blit(self.art, (0, 0), special_flags=pygame.BLEND_MAX)
        self.out.fill((0, 0, 0))
        self.out.blit(self.trail, (0, 0))
        self.glow(self.out)
        lines = [info["hud"], f"letters {info['letters']:,}"]
        if self.hint:
            lines.append(HINT)
        g = self.hud_gap
        wide = max(self.small.size(text)[0] for text in lines) + 28
        panel = pygame.Surface((wide, g * (len(lines) + 1) + g // 3 + 14))
        panel.set_alpha(170)                                    # so it reads over the fire
        self.out.blit(panel, (10, h - 18 - g * (len(lines) + 1) - g // 3 - 8))
        for i, text in enumerate(lines):
            self.out.blit(self.small.render(text, True, DIM), (24, h - 18 - g * (len(lines) - i)))
        self.out.blit(self.small.render(CREDIT, True, SIGN), (24, h - 18 - g * (len(lines) + 1) - g // 3))
        tt = self.small.render(f"{'●' if int(t * 2) % 2 == 0 else ' '} t {t:05.2f}s", True, ACCENT)
        self.out.blit(tt, (w - 24 - tt.get_width(), 20))
        return self.out


def window_size():
    info = pygame.display.Info()
    k = 1.0
    if info.current_w > 0 and info.current_h > 0:
        k = min(1.0, 0.88 * info.current_h / H, 0.95 * info.current_w / W)
    return int(W * k), int(H * k)


def main():
    pygame.init()
    size = window_size()
    window = pygame.display.set_mode(size)
    pygame.display.set_caption(TITLE)
    renderer, clock = Renderer(), pygame.time.Clock()
    t, paused = 0.0, False
    screen = renderer.draw(t)
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                pygame.quit()
                return 0
            if e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE:
                paused = not paused
            if e.type == pygame.KEYDOWN and e.key == pygame.K_r:
                t = 0.0
            if e.type == pygame.KEYDOWN and e.key == pygame.K_s:
                pygame.image.save(screen, str(Path(__file__).with_name(f"universe_{int(time.time())}.png")))
        dt = clock.tick(30) / 1000
        if not paused:
            t += min(dt, 1 / 15)
            if t > LOOP:
                t = 0.0
            screen = renderer.draw(t)
        window.blit(screen if size == (W, H) else pygame.transform.smoothscale(screen, size), (0, 0))
        pygame.display.flip()


if __name__ == "__main__":
    sys.exit(main())
