from collections import defaultdict
from functools import reduce
import math
import operator
import random

from flax.component import Breakable, IPhysics, Empty
import flax.entity as e
from flax.entity import (
    Entity, CaveWall, Floor, Tree, Grass, CutGrass, Salamango, Armor,
    Potion, StairsDown, StairsUp,
    KadathGate
)
from flax.geometry import Blob, Direction, Point, Rectangle, Size, Span
from flax.map import Map
from flax.noise import discrete_perlin_noise_factory


def random_normal_int(mu, sigma):
    """Return a normally-distributed random integer, given a mean and standard
    deviation.  The return value is guaranteed never to lie outside µ ± 3σ, and
    anything beyond µ ± 2σ is very unlikely (4% total).
    """
    ret = int(random.gauss(mu, sigma) + 0.5)

    # We have to put a limit /somewhere/, and the roll is only outside these
    # bounds 0.3% of the time.
    lb = int(math.ceil(mu - 2 * sigma))
    ub = int(math.floor(mu + 2 * sigma))

    if ret < lb:
        return lb
    elif ret > ub:
        return ub
    else:
        return ret


def random_normal_range(lb, ub):
    """Return a normally-distributed random integer, given an upper bound and
    lower bound.  Like `random_normal_int`, but explicitly specifying the
    limits.  Return values will be clustered around the midpoint.
    """
    # Like above, we assume the lower and upper bounds are 6σ apart
    mu = (lb + ub) / 2
    sigma = (ub - lb) / 4
    ret = int(random.gauss(mu, sigma) + 0.5)

    if ret < lb:
        return lb
    elif ret > ub:
        return ub
    else:
        return ret


class MapCanvas:
    def __init__(self, size):
        self.rect = size.to_rect(Point.origin())

        # TODO i think using types instead of entities /most of the time/ is
        # more trouble than it's worth
        self._arch_grid = {
            point: CaveWall for point in self.rect.iter_points()}
        self._item_grid = {point: [] for point in self.rect.iter_points()}
        self._creature_grid = {
            point: None for point in self.rect.iter_points()}

        self.floor_spaces = set()

    def clear(self, entity_type):
        for point in self.rect.iter_points():
            self._arch_grid[point] = entity_type

        if entity_type.components.get(IPhysics) is Empty:
            self.floor_spaces = set(self.rect.iter_points())
        else:
            self.floor_spaces = set()

    def set_architecture(self, point, entity_type):
        self._arch_grid[point] = entity_type

        # TODO this is a little hacky, but it's unclear how this /should/ work
        # before there are other kinds of physics
        if isinstance(entity_type, Entity):
            entity_type = entity_type.type

        if entity_type.components.get(IPhysics) is Empty:
            self.floor_spaces.add(point)
        else:
            self.floor_spaces.discard(point)

    def add_item(self, point, entity_type):
        self._item_grid[point].append(entity_type)

    def set_creature(self, point, entity_type):
        # assert entity_type.layer is Layer.creature
        self._creature_grid[point] = entity_type

    def maybe_create(self, type_or_thing):
        if isinstance(type_or_thing, Entity):
            return type_or_thing
        else:
            return type_or_thing()

    def to_map(self):
        map = Map(self.rect.size)
        maybe_create = self.maybe_create

        for point in self.rect.iter_points():
            map.place(maybe_create(self._arch_grid[point]), point)
            for item_type in self._item_grid[point]:
                map.place(maybe_create(item_type), point)
            if self._creature_grid[point]:
                map.place(maybe_create(self._creature_grid[point]), point)

        return map


class Room:
    """A room, which has not yet been drawn.
    """
    def __init__(self, rect):
        self.rect = rect

    @classmethod
    def randomize(cls, region, *, minimum_size=Size(5, 5)):
        """Place a room randomly in a region, randomizing its size and position.
        """
        # TODO need to guarantee the region is big enough
        size = Size(
            random_normal_range(minimum_size.width, region.width),
            random_normal_range(minimum_size.height, region.height),
        )
        left = region.left + random.randint(0, region.width - size.width)
        top = region.top + random.randint(0, region.height - size.height)
        rect = Rectangle(Point(left, top), size)

        return cls(rect)

    def draw_to_canvas(self, canvas):
        assert self.rect in canvas.rect

        for point in self.rect.iter_points():
            canvas.set_architecture(point, e.Floor)

        for point, _ in self.rect.iter_border():
            canvas.set_architecture(point, e.Wall)


class Fractor:
    """The agent noun form of 'fractal'.  An object that generates maps in a
    particular style.

    This is a base class, containing some generally-useful functionality; the
    interesting differentiation happens in subclasses.
    """
    def __init__(self, map_size, region=None):
        self.map_canvas = MapCanvas(map_size)
        if region is None:
            self.region = self.map_canvas.rect
        else:
            self.region = region

    def generate_map(self, up=None, down=None):
        """The method you probably want to call.  Does some stuff, then spits
        out a map.
        """
        self.generate()
        self.place_stuff()

        # TODO putting this here doesn't seem right, given that the first floor
        # explicitly needs to put the down portal in a specific area
        # TODO also not really sure how this works for multiple connections, or
        # special kinds of portals, or whatever.  that's, like, half about the
        # particular kind of map.  i'm starting to think that a map design
        # itself may need to be an object/function.
        if up:
            self.place_portal(StairsUp, up)
        if down:
            self.place_portal(StairsDown, down)

        return self.map_canvas.to_map()

    def generate(self):
        """Implement in subclasses.  Ought to do something to the canvas."""
        raise NotImplementedError

    # Utility methods follow

    def generate_room(self, region):
        # TODO lol not even using room_size
        room = Room.randomize(region)
        room.draw_to_canvas(self.map_canvas)

    def place_stuff(self):
        # TODO this probably varies by room style too, but we don't have a huge
        # variety yet of stuff to generate yet, so.
        assert self.map_canvas.floor_spaces, \
            "can't place player with no open spaces"
        points = random.sample(list(self.map_canvas.floor_spaces), 10)
        self.map_canvas.set_creature(points[0], Salamango)
        self.map_canvas.add_item(points[1], Armor)
        self.map_canvas.add_item(points[2], Potion)
        self.map_canvas.add_item(points[3], Potion)
        self.map_canvas.add_item(points[4], e.Gem)
        self.map_canvas.add_item(points[5], e.Crate)

    def place_portal(self, portal_type, destination):
        from flax.component import Portal
        portal = portal_type(Portal(destination=destination))

        # TODO not guaranteed
        assert self.map_canvas.floor_spaces, \
            "can't place portal with no open spaces"
        point = random.choice(list(self.map_canvas.floor_spaces))
        self.map_canvas.set_architecture(point, portal)


# TODO this is better, but still not great.  rooms need to be guaranteed
# to not touch each other, for one.  also has some biases towards big rooms
# still (need a left-leaning distribution for room size?) and it's easy to end
# up with an obvious grid
# TODO also lol needs hallways
class BinaryPartitionFractor(Fractor):
    # TODO should probably accept a (minimum) room size instead, and derive
    # minimum partition size from that
    def __init__(self, *args, minimum_size):
        super().__init__(*args)
        self.minimum_size = minimum_size

    def generate(self):
        regions = self.maximally_partition()
        for region in regions:
            self.generate_room(region)

    def maximally_partition(self):
        # TODO this should preserve the tree somehow, so a hallway can be drawn
        # along the edges
        regions = [self.region]
        # TODO configurable?  with fewer, could draw bigger interesting things
        # in the big spaces
        wanted = 7

        while regions and len(regions) < wanted:
            region = regions.pop(0)

            new_regions = self.partition(region)
            regions.extend(new_regions)

            regions.sort(key=lambda r: r.size.area, reverse=True)

        return regions

    def partition(self, region):
        # Partition whichever direction has more available space
        rel_height = region.height / self.minimum_size.height
        rel_width = region.width / self.minimum_size.width

        if rel_height < 2 and rel_width < 2:
            # Can't partition at all
            return [region]

        if rel_height > rel_width:
            return self.partition_horizontal(region)
        else:
            return self.partition_vertical(region)

    def partition_horizontal(self, region):
        # We're looking for the far edge of the top partition, so subtract 1
        # to allow it on the border of the minimum size
        min_height = self.minimum_size.height
        top = region.top + min_height - 1
        bottom = region.bottom - min_height

        assert top <= bottom

        midpoint = random.randint(top, bottom + 1)

        return [
            region.replace(bottom=midpoint),
            region.replace(top=midpoint + 1),
        ]

    def partition_vertical(self, region):
        # Exactly the same as above
        min_width = self.minimum_size.width
        left = region.left + min_width - 1
        right = region.right - min_width

        assert left <= right

        midpoint = random.randint(left, right + 1)

        return [
            region.replace(right=midpoint),
            region.replace(left=midpoint + 1),
        ]


class PerlinFractor(Fractor):
    def _a_star(self, start, goals, costs):
        assert goals
        # TODO need to figure out which points should join to which!  need a...
        # minimum number of paths?  some kind of spanning tree that's
        # minimal...
        # TODO technically there might only be one local minima
        seen = set()
        pending = [start]  # TODO actually a sorted set heap thing
        paths = {}

        def estimate_cost(start, goal):
            dx, dy = goal - start
            dx = abs(dx)
            dy = abs(dy)
            return max(dx, dy) * min(costs[start], costs[goal])

        g_score = {start: 0}
        f_score = {start: min(estimate_cost(start, goal) for goal in goals)}

        while pending:
            pending.sort(key=f_score.__getitem__)
            current = pending.pop(0)
            if current in goals:
                # CONSTRUCT PATH HERE
                break

            seen.add(current)
            for npt in current.neighbors:
                if npt not in self.region or npt in seen:
                    continue
                tentative_score = g_score[current] + costs[npt]

                if npt not in pending or tentative_score < g_score[npt]:
                    paths[npt] = current
                    g_score[npt] = tentative_score
                    f_score[npt] = tentative_score + min(
                        estimate_cost(npt, goal) for goal in goals)
                    pending.append(npt)

        final_path = []
        while current in paths:
            final_path.append(current)
            current = paths[current]
        final_path.reverse()
        return final_path

    def _generate_river(self, noise):
        # TODO seriously starting to feel like i need a Feature type for these
        # things?  like, passing `noise` around is a really weird way to go
        # about this.  what would the state even look like though?

        '''
        # TODO i think this needs another flooding algorithm, which probably
        # means it needs to be a lot simpler and faster...
        noise_factory = discrete_perlin_noise_factory(
            *self.region.size, resolution=2, octaves=1)

        noise = {
            point: abs(noise_factory(*point) - 0.5) * 2
            for point in self.region.iter_points()
        }
        for point, n in noise.items():
            if n < 0.2:
                self.map_canvas.set_architecture(point, e.Water)
        return
        '''

        # Build some Blob internals representing the two halves of the river.
        left_side = {}
        right_side = {}
        river = {}

        center_factory = discrete_perlin_noise_factory(
            self.region.height, resolution=3)
        width_factory = discrete_perlin_noise_factory(
            self.region.height, resolution=6, octaves=2)
        center = random_normal_int(
            self.region.center().x, self.region.width / 4 / 3)
        for y in self.region.range_height():
            center += (center_factory(y) - 0.5) * 3
            width = width_factory(y) * 2 + 5
            x0 = int(center - width / 2)
            x1 = int(x0 + width + 0.5)
            for x in range(x0, x1 + 1):
                self.map_canvas.set_architecture(Point(x, y), e.Water)

            left_side[y] = (Span(self.region.left, x0 - 1),)
            right_side[y] = (Span(x1 + 1, self.region.right),)
            river[y] = (Span(x0, x1),)

        return Blob(left_side), Blob(river), Blob(right_side)

    def generate(self):
        # This noise is interpreted roughly as the inverse of "frequently
        # travelled" -- low values are walked often (and are thus short grass),
        # high values are left alone (and thus are trees).
        noise_factory = discrete_perlin_noise_factory(
            *self.region.size, resolution=6)
        noise = {
            point: noise_factory(*point)
            for point in self.region.iter_points()
        }
        local_minima = set()
        for point, n in noise.items():
            # We want to ensure that each "walkable region" is connected.
            # First step is to collect all local minima -- any walkable tile is
            # guaranteed to be conneted to one.
            if all(noise[npt] >= n for npt in point.neighbors if npt in noise):
                local_minima.add(point)

            if n < 0.3:
                arch = CutGrass
            elif n < 0.6:
                arch = Grass
            else:
                arch = Tree
            self.map_canvas.set_architecture(point, arch)

        left_bank, river_blob, right_bank = self._generate_river(noise)

        # Decide where bridges should go.  They can only cross where there's
        # walkable space on both sides, so find all such areas.
        # TODO maybe a nicer api for testing walkability here
        # TODO this doesn't detect a walkable area on one side that has no
        # walkable area on the other side, and tbh i'm not sure what to do in
        # such a case anyway.  could forcibly punch a path through the trees, i
        # suppose?  that's what i'll have to do anyway, right?
        # TODO this will break if i ever add a loop in the river, but tbh i
        # have no idea how to draw bridges in that case
        new_block = True
        start = None
        end = None
        blocks = []
        for y, (span,) in river_blob.spans.items():
            if self.map_canvas._arch_grid[Point(span.start - 1, y)] is not Tree and \
                    self.map_canvas._arch_grid[Point(span.end + 1, y)] is not Tree:
                if new_block:
                    start = y
                    end = y
                    new_block = False
                else:
                    end = y
            else:
                if not new_block:
                    blocks.append((start, end))
                new_block = True
        if not new_block:
            blocks.append((start, end))

        for start, end in blocks:
            y = random_normal_range(start, end)
            span = river_blob.spans[y][0]
            local_minima.add(Point(span.start - 1, y))
            local_minima.add(Point(span.end + 1, y))
            for x in span:
                self.map_canvas.set_architecture(Point(x, y), e.Bridge)

        # Consider all local minima along the edges, as well.
        for x in self.region.range_width():
            for y in (self.region.top, self.region.bottom):
                point = Point(x, y)
                n = noise[point]
                if (n < noise.get(Point(x - 1, y), 1) and
                        n < noise.get(Point(x + 1, y), 1)):
                    local_minima.add(point)
        for y in self.region.range_height():
            for x in (self.region.left, self.region.right):
                point = Point(x, y)
                n = noise[point]
                if (n < noise.get(Point(x, y - 1), 1) and
                        n < noise.get(Point(x, y + 1), 1)):
                    local_minima.add(point)

        for point in local_minima:
            if point not in river_blob:
                self.map_canvas.set_architecture(point, e.Dirt)

        for blob in (left_bank, right_bank):
            paths = self.flood_valleys(blob, local_minima, noise)

            for path_point in paths:
                self.map_canvas.set_architecture(path_point, e.Dirt)

        # Whoops time for another step: generating a surrounding cave wall.
        for edge in Direction.orthogonal:
            width = self.region.edge_length(edge)
            wall_noise = discrete_perlin_noise_factory(width, resolution=6)
            for n in self.region.edge_span(edge):
                offset = int(wall_noise(n) * 4 + 1)
                for m in range(offset):
                    point = self.region.edge_point(edge, n, m)
                    self.map_canvas.set_architecture(point, e.CaveWall)

    def flood_valleys(self, region, goals, depthmap):
        # We want to connect all the minima with a forest path.
        # Let's flood the forest.  The algorithm is as follows:
        # - All the local minima are initally full of water, forming a set of
        # distinct puddles.
        # - Raise the water level.  Each newly-flooded tile must touch at least
        # one other flooded tile; it becomes part of that puddle, and remembers
        # the tile that flooded it.
        # - Whenever a tile touches two or more puddles, they merge into one
        # large puddle.  That tile is part of the forest path.  For each
        # puddle, walk back along the chain of flooded tiles to the original
        # minima; these tiles are also part of the forest path.
        # When only one puddle remains, we're done, and all the minima are
        # joined by a path along the lowest route.
        flooded = {}
        puddle_map = {}
        path_from_puddle = defaultdict(dict)
        paths = set()
        for puddle, point in enumerate(goals):
            if point not in region:
                continue
            flooded[point] = puddle
            puddle_map[puddle] = puddle
        flood_order = sorted(
            frozenset(region.iter_points()) - flooded.keys(),
            key=depthmap.__getitem__)
        for point in flood_order:
            # Group any flooded neighbors by the puddle they're in.
            # puddle => [neighboring points...]
            adjacent_puddles = defaultdict(list)
            for npt in point.neighbors:
                if npt not in flooded:
                    continue
                puddle = puddle_map[flooded[npt]]
                adjacent_puddles[puddle].append(npt)
            # Every point is either a local minimum OR adjacent to a point
            # lower than itself, by the very definition of "local minimum".
            # Thus there must be at least one adjacent puddle.
            # TODO not so true any more...  maybe should determine local minima
            # automatically here...
            if not adjacent_puddles:
                continue
            assert adjacent_puddles

            # Remember how to get from adjacent puddles to this point.
            # Only store the lowest adjacent point.
            for puddle, points in adjacent_puddles.items():
                path_from_puddle[point][puddle] = min(
                    points, key=depthmap.__getitem__)

            flooded[point] = this_puddle = min(adjacent_puddles)
            if len(adjacent_puddles) > 1:
                # Draw the path from both puddles' starting points to here
                paths.add(point)
                for puddle in adjacent_puddles:
                    path_point = point
                    while path_point:
                        paths.add(path_point)

                        next_point = None
                        cand_paths = path_from_puddle[path_point]
                        for cand_puddle, cand_point in cand_paths.items():
                            if puddle_map[cand_puddle] == puddle and (
                                    next_point is None or
                                    depthmap[cand_point] < depthmap[next_point]
                            ):
                                next_point = cand_point
                        path_point = next_point

                # This point connects two puddles; merge them.  Have to update
                # the whole mapping, in case some other puddle is already
                # mapped to one we're about to remap.
                for from_puddle, to_puddle in puddle_map.items():
                    if {from_puddle, to_puddle} & adjacent_puddles.keys():
                        puddle_map[from_puddle] = this_puddle

                # If there's only one puddle left, we're done!
                if len(frozenset(puddle_map.values())) == 1:
                    break

        return paths

    def place_stuff(self):
        super().place_stuff()
        assert self.map_canvas.floor_spaces, \
            "can't place player with no open spaces"

        floor = self.map_canvas.floor_spaces
        points = random.sample(list(floor), 1)
        self.map_canvas.add_item(points[0], e.Key)

def generate_caves(map_canvas, region, wall_tile, force_walls=(), force_floors=()):
    """Uses cellular automata to generate a cave system.

    Idea from: http://www.roguebasin.com/index.php?title=Cellular_Automata_Method_for_Generating_Random_Cave-Like_Levels
    """
    base_grid = {}
    for point in force_walls:
        base_grid[point] = True
    for point in force_floors:
        base_grid[point] = False

    grid = {point: random.random() < 0.40 for point in region.iter_points()}
    grid.update(base_grid)
    for generation in range(5):
        next_grid = base_grid.copy()
        for point in region.iter_points():
            neighbors = grid[point] + sum(grid.get(neighbor, True) for neighbor in point.neighbors)
            # The 4-5 rule: the next gen is a wall if either:
            # - the current gen is a wall and 4+ neighbors are walls;
            # - the current gen is a space and 5+ neighbors are walls.
            next_grid[point] = neighbors >= 5
        grid = next_grid

    # TODO need to connect any remaining areas here
    # TODO maybe i should LET this become a lot of small disjoint caves, so it
    # acts like a bunch of rooms.  then connect them with doors + hallways!

    for point in region.iter_points():
        if grid[point]:
            map_canvas.set_architecture(point, wall_tile)
        else:
            map_canvas.set_architecture(point, e.CaveFloor)


# TODO it would be slick to have a wizard menu with commands like "regenerate
# this entire level"

class RuinFractor(Fractor):
    # TODO should really really let this wrap something else
    def generate(self):
        self.map_canvas.clear(Floor)

        # So what I want here is to have a cave system with a room in the
        # middle, then decay the room.
        # Some constraints:
        # - the room must have a wall where the entrance could go, which faces
        # empty space
        # - a wall near the entrance must be destroyed
        # - the player must start in a part of the cave connected to the
        # destroyed entrance
        # - none of the decay applied to the room may block off any of its
        # interesting features

        # TODO it would be nice if i could really write all this without ever
        # having to hardcode a specific direction, so the logic could always be
        # rotated freely
        side = random.choice([Direction.left, Direction.right])

        # TODO assert region is big enough
        room_size = Size(
            random_normal_range(9, int(self.region.width * 0.4)),
            random_normal_range(9, int(self.region.height * 0.4)),
        )

        room_position = self.region.center() - room_size // 2
        room_position += Point(
            random_normal_int(0, self.region.width * 0.1),
            random_normal_int(0, self.region.height * 0.1),
        )

        room_rect = Rectangle(room_position, room_size)
        self.room_region = room_rect

        room = Room(room_rect)

        cave_area = (
            Blob.from_rectangle(self.region)
            - Blob.from_rectangle(room_rect)
        )
        self.cave_region = cave_area
        walls = [point for (point, _) in self.region.iter_border()]
        floors = []
        for point, edge in room_rect.iter_border():
            if edge is side or edge.adjacent_to(side):
                floors.append(point)
                floors.append(point + side)
        generate_caves(
            self.map_canvas, cave_area, CaveWall,
            force_walls=walls, force_floors=floors,
        )

        room.draw_to_canvas(self.map_canvas)

        # OK, now draw a gate in the middle of the side wall
        if side is Direction.left:
            x = room_rect.left
        else:
            x = room_rect.right
        mid_y = room_rect.top + room_rect.height // 2
        if room_rect.height % 2 == 1:
            min_y = mid_y - 1
            max_y = mid_y + 1
        else:
            min_y = mid_y - 2
            max_y = mid_y + 1
        for y in range(min_y, max_y + 1):
            self.map_canvas.set_architecture(Point(x, y), KadathGate)

        # Beat up the border of the room near the gate
        y = random.choice(
            tuple(range(room_rect.top, min_y))
            + tuple(range(max_y + 1, room_rect.bottom))
        )
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                point = Point(x + dx, y + dy)
                # TODO i think what i may want is to have the cave be a
                # "Feature", where i can check whether it has already claimed a
                # tile, or draw it later, or whatever.
                if self.map_canvas._arch_grid[point] is not CaveWall:
                    distance = abs(dx) + abs(dy)
                    ruination = random_normal_range(0, 0.2) + distance * 0.2
                    self.map_canvas.set_architecture(
                        point, e.Rubble(Breakable(ruination)))

        # And apply some light ruination to the inside of the room
        border = list(room_rect.iter_border())
        # TODO don't do this infinitely; give up after x tries
        while True:
            point, edge = random.choice(border)
            if self.map_canvas._arch_grid[point + edge] is CaveWall:
                break
        self.map_canvas.set_architecture(point, CaveWall)
        self.map_canvas.set_architecture(point - edge, CaveWall)
        # TODO this would be neater if it were a slightly more random pattern
        for direction in (
                Direction.up, Direction.down, Direction.left, Direction.right):
            self.map_canvas.set_architecture(
                point - edge + direction, CaveWall)

    def place_stuff(self):
        assert self.map_canvas.floor_spaces, \
            "can't place player with no open spaces"

        cave_floor = frozenset(self.cave_region.iter_points())
        cave_floor &= self.map_canvas.floor_spaces
        points = random.sample(list(cave_floor), 5)
        from flax.component import Portal
        # TODO this should exit.  also confirm.  should be part of the ladder
        # entity?  also, world doesn't place you here.  maybe the map itself
        # should know this?
        # TODO lol this is such a stupid hack
        ladder = e.Ladder(Portal(destination='__exit__'))
        self.map_canvas.set_architecture(points[0], ladder)

        self.map_canvas.add_item(points[1], e.Gem)
        self.map_canvas.add_item(points[2], e.Crate)

    def place_portal(self, portal_type, destination):
        from flax.component import Portal
        if portal_type is e.StairsDown:
            # Add the down stairs to the room, surrounded by some pillars
            room_center = self.room_region.center()
            self.map_canvas.set_architecture(
                room_center,
                portal_type(Portal(destination=destination)),
            )
            for direction in (
                Direction.up_right, Direction.down_right,
                Direction.up_left, Direction.down_left
            ):
                self.map_canvas.set_architecture(room_center + direction, e.Pillar)
        else:
            super().place_portal(portal_type, destination)


class RuinedHallFractor(Fractor):
    def generate(self):
        self.map_canvas.clear(CaveWall)

        # First create a bunch of hallways and rooms.
        # For now, just carve a big area, run a hallway through the middle, and
        # divide either side into rooms.
        area = Room.randomize(self.region, minimum_size=self.region.size // 2)
        area.draw_to_canvas(self.map_canvas)

        center = area.rect.center()
        y0 = center.y - 2
        y1 = center.y + 2
        hallway = Rectangle(origin=Point(area.rect.left, center.y - 2), size=Size(area.rect.width, 5))
        Room(hallway).draw_to_canvas(self.map_canvas)

        top_space = area.rect.replace(bottom=hallway.top)
        bottom_space = area.rect.replace(top=hallway.bottom)

        rooms = []
        for orig_space in (top_space, bottom_space):
            space = orig_space
            # This includes walls!
            minimum_width = 7
            # Note that the rooms overlap where they touch, so we subtract one
            # from both the total width and the minimum width, in effect
            # ignoring all the walls on one side
            maximum_rooms = (space.width - 1) // (minimum_width - 1)
            # The maximum number of rooms that will fit also affects how much
            # wiggle room we're willing to have.  For example, if at most 3 rooms
            # will fit, then generating 2 rooms is also reasonable.  But if 10
            # rooms will fit, generating 2 rooms is a bit silly.  We'll arbitrarily
            # use 1/3 the maximum as the minimum.  (Plus 1, to avoid rounding down
            # to zero.)
            minimum_rooms = maximum_rooms // 6 + 1
            num_rooms = random_normal_range(minimum_rooms, maximum_rooms)

            # TODO normal distribution doesn't have good results here.  think
            # more about how people use rooms -- often many of similar size,
            # with some exceptions.  also different shapes, bathrooms or
            # closets nestled together, etc.
            while num_rooms > 1:
                # Now we want to divide a given amount of space into n chunks, where
                # the size of each chunk is normally-distributed.  I have no idea how
                # to do this in any strict mathematical sense, so instead we'll just
                # carve out one room at a time and hope for the best.
                min_width = minimum_width
                avg_width = (space.width - 1) // num_rooms + 1
                max_width = space.width - (minimum_width - 1) * (num_rooms - 1)
                room_width = random_normal_int(avg_width, min(max_width - avg_width, avg_width - min_width) // 3)

                room = space.replace(right=space.left + room_width - 1)
                rooms.append(room)
                space = space.replace(left=room.right)
                num_rooms -= 1

            rooms.append(space)

        for rect in rooms:
            Room(rect).draw_to_canvas(self.map_canvas)

        from flax.component import Lockable

        # Add some doors for funsies.
        locked_room = random.choice(rooms)
        for rect in rooms:
            x = random.randrange(rect.left + 1, rect.right - 1)
            if rect.top > hallway.top:
                side = Direction.down
            else:
                side = Direction.up
            point = rect.edge_point(side.opposite, x, 0)
            door = e.Door(Lockable(locked=rect is locked_room))
            self.map_canvas.set_architecture(point, door)

        self.hallway_area = Blob.from_rectangle(hallway)
        self.locked_area = Blob.from_rectangle(locked_room)
        self.rooms_area = reduce(operator.add, (Blob.from_rectangle(rect) for rect in rooms if rect is not locked_room))


    def place_stuff(self):
        # TODO having to override this per room is becoming increasingly
        # tedious and awkward and copy-pastey.
        assert self.map_canvas.floor_spaces, \
            "can't place player with no open spaces"

        floor_spaces = self.map_canvas.floor_spaces
        room_floors = floor_spaces & frozenset(self.rooms_area.iter_points())
        hall_floors = floor_spaces & frozenset(self.hallway_area.iter_points())
        lock_floors = floor_spaces & frozenset(self.locked_area.iter_points())

        points = random.sample(list(room_floors), 8)
        self.map_canvas.set_creature(points[0], Salamango)
        self.map_canvas.set_creature(points[1], Salamango)
        self.map_canvas.set_creature(points[2], Salamango)
        self.map_canvas.add_item(points[3], e.Armor)
        self.map_canvas.add_item(points[4], e.Potion)
        self.map_canvas.add_item(points[5], e.Potion)
        self.map_canvas.add_item(points[6], e.Gem)
        self.map_canvas.add_item(points[7], e.Crate)

        points = random.sample(list(lock_floors), 1)
        self.map_canvas.add_item(points[0], e.Crown)

    def place_portal(self, portal_type, destination):
        # TODO and this part is even worse yes
        from flax.component import Portal
        portal = portal_type(Portal(destination=destination))

        # TODO not guaranteed
        assert self.map_canvas.floor_spaces, \
            "can't place portal with no open spaces"

        floor_spaces = self.map_canvas.floor_spaces
        room_floors = floor_spaces & frozenset(self.rooms_area.iter_points())
        hall_floors = floor_spaces & frozenset(self.hallway_area.iter_points())
        lock_floors = floor_spaces & frozenset(self.locked_area.iter_points())

        if portal_type is e.StairsDown:
            # Down stairs go in an unlocked room
            point = random.choice(list(room_floors))
        else:
            # Up stairs go in the hallway
            point = random.choice(list(hall_floors))
        self.map_canvas.set_architecture(point, portal)


class MapLayout:
    """Knows how to generate a specific style of map, based on some set of
    parameters.
    """
    def generate_map(self):
        raise NotImplementedError
