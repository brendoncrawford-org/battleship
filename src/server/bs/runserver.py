#!/usr/bin/env python3

"""
BattleShip Web Service
"""

import sys
import json
import uuid

import numpy as np
import tornado.ioloop
import tornado.web


GAMES = {}
SESSION_KEY = "X-Bs-Session-Id"
GRID_SIZE = 10
SHIPS = {
    "carrier": {
        "intcode": 1,
        "length": 5
    }
    "battleship": {
        "intcode": 2,
        "length": 4
    },
    "cruiser": {
        "intcode": 3,
        "length": 3
    },
    "submarine": {
        "intcode": 4,
        "length": 3
    },
    "destroyer": {
        "intcode": 5,
        "length": 2
    }
}
SHIPS_INTCODES = dict(lambda s: (s[1]["intcode"], s[0]), SHIPS.items())
MOVE_HIT = 1
MOVE_MISS = 2


class ShipModel(object):

    id = None
    hits = None
    sunk = None
    length = None
    intcode = None

    def __init__(self, id_, length, intcode):
        self.id = id_
        self.length = length
        self.intcode = intcode
        self.hits = 0
        self.sunk = False
        return None

    def add_hit(self):
        if self.hits < self.length:
            self.hits += 1
        if self.hits >= self.length:
            self.sunk = True
        return True

    def export(self):
        return {
            "hits": self.hits,
            "sunk": self.sunk,
            "length": self.length,
            "intcode": self.intcode
        }

    @classmethod
    def get_ship_id_by_intcode(cls, intcode):
        return SHIPS_INTCODES[intcode]

    @classmethod
    def make_ship_by_id(cls, ship_id):
        ship_def = SHIPS[ship_id]
        return ShipModel(ship_id, ship_def["length"], ship_def["intcode"])


class PlayerModel(object):

    id = None
    session_id = None
    moves_map = None
    moves_index = None
    ships = None
    grid = None
    grid_attempts = None
    sunk_all = None

    def __init__(self):
        self.id = str(uuid.uuid4())
        self.session_id = str(uuid.uuid4())
        self.moves_index = []
        self.moves_map = {}
        self.ships = {}
        self.grid = np.zeros((GRID_SIZE, GRID_SIZE))
        self.grid_attempts = np.zeros((GRID_SIZE, GRID_SIZE))
        self.sunk_all = False
        return None

    def export(self, this_player_id=None):
        is_this_player = this_player_id == self.id
        return {
            "id": self.id,
            "moves_index": self.moves_index,
            "sunk_all": self.sunk_all,
            "grid_attempts": self.grid.tolist(),
            "grid": self.grid.tolist() if is_this_player else None,
            "ships": (
                list(map(lambda s: s.export(), self.ships))
                if is_this_player
                else None
            )
        }

    def get_moves(self):
        return self.moves_index

    def check_session(self, session_id):
        return session_id is not None and session_id == self.session_id

    def has_ship(self, ship_id):
        return (ship_id in self.ships)

    def check_all_ships_added(self):
        return (len(self.ships) == len(SHIPS))

    def add_ship(self, ship_id, coords, orientation):
        if self.has_ship(ship_id):
            return False
        ship = ShipModel.make_ship_by_id(ship_id)
        ship_arr = self.get_ship_arr(ship.length, coords, orientation)
        available = self.is_space_available(ship_arr)
        if not available:
            return False
        self.add_ship_coords_to_grid(ship_arr, ship.intcode)
        self.ships[ship_id] = ship
        return True

    def add_ship_coord_to_grid(self, ship_arr, ship_intit):
        ship_arr.fill(ship_intit)
        return True

    def is_space_available(self, ship_arr):
        return (len(filter(lambda k: k > 0, ship_arr)) == 0)

    def get_ship_arr(self, ship_len, coords, orientation):
        x, y = coords
        if orientation == "x":
            return self.grid[y][x:(x + ship_len)]
        if orientation == "y":
            return self.grid[y:(y + ship_len),x]
        return None

    def parse_ship_coords(coords_code):
        parts = move_code.split("-")
        if len(parts) != 3:
            return False
        try:
            x = int(parts[0])
            y = int(parts[1])
        except ValueError:
            return False
        orientation = parts[2]
        if orientation not in ["x", "y"]:
            return False
        return ((x, y), orientation)

    def parse_move(self, move_code):
        parts = move_code.split("-")
        if len(parts) != 2:
            return None
        try:
            x = int(parts[0])
            y = int(parts[1])
        except ValueError:
            return None
        return (x, y)

    def get_ship_at_coords(self, coords):
        x, y = coords
        intcode = self.grid[y][x]
        if intcode == 0:
            return None
        ship_id = ShipModel.get_ship_id_by_intcode(intcode)
        ship = self.ships[ship_id]
        return ship

    def add_grid_attempt(self, is_hit, coords):
        x, y = coords
        code = MOVE_HIT if is_hit else MOVE_MISS
        self.grid_attempts[y][x] = code
        return True

    def is_sunk_all(self):
        return (len(list(filter(lambda s: not s.sunk, self.ships))) == 0)

    def register_hit(self, coords):
        """
        `move` is an (x, y) tuple
        """
        if not self.check_all_ships_added():
            return (False, None, "not_all_ships_added")
        if self.sunk_all:
            return (False, None, "all_ships_already_sunk")
        ship = self.get_ship_at_coords(coords)
        is_hit = (ship is not None)
        self.add_grid_attempt(is_hit, coords)
        self.moves_map[coords] = True
        self.moves_index.append(self.moves_map[coords])
        if not is_hit:
            return (
                True,
                {
                    "hit": False,
                    "sunk": None,
                    "sunk_all": False
                },
                None
            )
        ship.add_hit()
        if self.is_sunk_all():
            self.sunk_all = True
        return (
            True,
            {
                "hit": True,
                "sunk": ship.sunk,
                "sunk_all": self.sunk_all
            },
            None
        )


class GameModel(object):

    id = None
    players = None
    game_status = None
    win_player = None

    def __init__(self):
        self.id = str(uuid.uuid4())
        self.players = {}
        game_status = True
        win_player = None
        return None

    def add_player(self):
        if len(self.players) >= 2:
            return None
        player = PlayerModel()
        self.players[player.id] = player
        return player

    def export(self, this_player_id=None):
        return {
            "id": self.id,
            "game_status": self.game_status,
            "win_player": self.win_player,
            "players": (
                list(
                    map(
                        lambda p: p.export(this_player_id),
                        self.players.values()
                    )
                )
            )
        }

    def get_player_by_session_id(self, session_id):
        players = (
            list(
                filter(
                    lambda p: p.session_id == session_id,
                    self.players.values()
                )
            )
        )
        if len(players) == 0:
            return None
        return players[0]

    def has_player(self, player_id):
        return (player_id in self.players)

    def get_player(self, player_id):
        return (self.players[player_id])

    def get_opposing_player(self, this_player):
        other_players (
            list(
                filter(
                    lambda p: p[0] != this_player.id,
                    self.players.items()
                )
            )
        )
        if len(other_players) == 0:
            return None
        return other_players[0][0]

    def make_move(self, this_player, coords):
        oppose_player = self.get_opposing_player(this_player)
        if oppose_player is None:
            return (False, None, "no_opposing_player")
        hit_status, hit_data, hit_msg = oppose_player.register_hit(coords)
        if not hit_status:
            return (False, None, msg)
        if oppose_player.sunk_all:
            self.register_winner(player)
        return (True, hit_data, None)

    def register_winner(player):
        self.game_status = False
        self.win_player = player
        return True

    @classmethod
    def game_exists(cls, game_id):
        return (game_id in GAMES)

    @classmethod
    def get_game_by_id(cls, game_id):
        if game_id not in GAMES:
            return None
        return GAMES[game_id]

    @classmethod
    def create_game_from_id(cls, game_id):
        game = GameModel()
        GAMES[game.id] = game
        return game


class BaseHandler(tornado.web.RequestHandler):

    def get_session_id(self):
        if SESSION_KEY not in self.request.headers:
            return None
        return self.request.headers[SESSION_KEY]

    def response(self, body_obj=None, status=200, code="ok", headers=None):
        self.set_status(status)
        self.set_header("Content-Type", "application/json")
        if headers is not None:
            for key, val in headers:
                self.set_header(key, val)
        self.write(json.dumps({
            "code": code,
            "data": body_obj
        }))
        return None


class GamesHandler(BaseHandler):

    def post(self):
        game = GameModel.create_game_from_id()
        player = game.add_player()
        exported = game.export(player.id)
        return self.response(exported)

    def get(self):
        game_ids = list(GAMES.keys())
        return self.response(game_ids)


class GameHandler(BaseHandler):

    def get(self, game_id):
        """
        Gets status for current game
        """
        session_id = self.get_session_id()
        if session_id is None:
            return self.response(None, 401, "no_session_id")
        player = GameModel.get_player_by_session_id(session_id)
        if not GameModel.game_exists(game_id):
            return self.response(None, 404, "game_not_found")
        game = GameModel.get_game_by_id(game)
        exported = game.export(player.id)
        return self.response(exported)


class PlayersHandler(BaseHandler):

    def post(self, game_id):
        """
        Allows a user to join an existing game
        """
        if not GameModel.game_exists(game_id):
            return self.response(None, 404, "game_not_found")
        game = GameModel.get_game_by_id(game_id)
        player = game.add_player()
        if player is None:
            return self.response(None, 401, "max_players_already_joined")
        return self.response(
            {
                "game_id": game.id,
                "player_id": player.id
            },
            headers=[(SESSION_KEY, player.session_id)]
        )


class MovesHandler(BaseHandler):

    def put(self, game_id, player_id, move_code):
        game = GameModel.get_game_by_id(game)
        if game is None:
            return self.response(None, 404, "game_not_found")
        player = game.get_player(player_id)
        if player is None:
            return self.response(None, 403, "player_id_not_specified")
        if not player.check_session(self.get_session_id()):
            return self.response(None, 403, "player_session_not_authorized")
        coords = player.parse_move(move_code)
        if coords is None:
            return self.response(None, 404, "bad_move")
        move_status, move_data, move_msg = game.make_move(player, coords)
        if not move_status:
            return self.response(None, 404, move_msg)
        return self.response(move_data)


class ShipsHandler(BaseHandler):

    def put(self, game_id, player_id, ship_id, coords_code):
        game = GameModel.get_game_by_id(game)
        if game is None:
            return self.response(None, 404, "game_not_found")
        player = game.get_player(player_id)
        if player is None:
            return self.response(None, 403, "player_id_not_specified")
        if not player.check_session(self.get_session_id()):
            return self.response(None, 403, "player_session_not_authorized")
        coords, orientation = player.parse_ship_coords(coords_code)
        if not coords:
            return self.response(None, 404, "bad_ship_coords")
        ship_status = player.add_ship(ship_id, coords, orientation)
        if not ship_status:
            return self.response(None, 404, "bad_ship_coords")
        return self.response()


def make_app():
    return (
        tornado.web.Application([
            (
                r"/games",
                GamesHandler
            ),
            (
                r"/games/([A-Za-z0-9-]{36})",
                GameHandler
            ),
            (
                r"/games/([A-Za-z0-9-]{36})/players",
                PlayersHandler
            ),
            (
                r"/games/([A-Za-z0-9-]{36})"
                r"/players/([A-Za-z0-9-]{32})/ships/%(SHIPS)s"
                r"/([0-9]{1,2}-[0-9]{1,2}-[xy])" %
                (
                    r"|".join(SHIPS.keys())
                ),
                ShipsHandler
            ),
            (
                r"/games/([A-Za-z0-9-]{36})"
                r"/players/([A-Za-z0-9-]{32})/moves/([0-9]{1,2}-[0-9]{1,2})",
                MovesHandler
            )
        ])
    )


def main():
    app = make_app()
    app.listen(8888)
    tornado.ioloop.IOLoop.current().start()
    return True


if __name__ == "__main__":
    main()
    sys.exit(0)