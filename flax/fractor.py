from itertools import product

from flax.things.arch import CaveWall, Wall, Floor, Player


class MapCanvas:
    def __init__(self, height, width):
        self.height = height
        self.width = width

        self.grid = [[CaveWall for _ in range(width)] for _ in range(height)]

    def draw_room(self, x0, y0, dx, dy):
        assert x0 + dx <= self.width
        assert y0 + dy <= self.height

        for x, y in product(range(x0 + 1, x0 + dx - 1), range(y0 + 1, y0 + dy - 1)):
            self.grid[x][y] = Floor

        # Left and right
        for x in range(x0 + 1, x0 + dx - 1):
            self.grid[x][y0] = Wall
            self.grid[x][y0 + dy - 1] = Wall

        # Top and bottom, plus corners
        for y in range(y0, y0 + dy):
            self.grid[x0][y] = Wall
            self.grid[x0 + dx - 1][y] = Wall
