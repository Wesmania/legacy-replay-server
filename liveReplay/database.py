import time
import logging
import os
from enum import Enum
from PyQt5.QtSql import QSqlDatabase, QSqlQuery


class DbContext:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self.db.open()

    def __exit__(self, exc_type, exc_value, traceback):
        self.db.close()


def _qv(self, query, enum_value):
    return query.value(enum_value.value)


class Database:
    __logger = logging.getLogger(__name__)

    class ReplayInfoQueryValues(Enum):
        GAMEMOD = 0
        GAMETYPE = 1
        FILENAME = 2
        GAMENAME = 3
        HOST = 4
        LOGIN = 5
        PLAYER_ID = 6
        AI = 7
        TEAM = 8

    class ModInfoQueryValues(Enum):
        FILE_ID = 0
        VERSION = 1

    def __init__(self, hostname, port, name, login, password):
        self.db = QSqlDatabase.addDatabase("QMYSQL")
        self.db.setHostName(hostname)
        self.db.setPort(port)
        self.db.setDatabaseName(name)
        self.db.setUserName(login)
        self.db.setPassword(password)

    def replay_info(self, uid):
        ret = {}
        ret["game_end"] = time.time()

        with DbContext(self.db):
            query = QSqlQuery(self.db)
            queryStr = ("""
            SELECT game_featuredMods.gamemod, gameType, filename, gameName, host, login, playerId, AI, team
            FROM `game_stats`
                LEFT JOIN game_player_stats
                    ON `game_player_stats`.`gameId` = game_stats.id
                LEFT JOIN table_map
                    ON `game_stats`.`mapId` = table_map.id
                LEFT JOIN login
                    ON login.id = `game_player_stats`.`playerId`
                LEFT JOIN game_featuredMods
                    ON `game_stats`.`gameMod` = game_featuredMods.id
            WHERE game_stats.id = {}
            """.format(uid))
            query.exec_(queryStr)
            if query.size() == 0:
                return None

            RV = self.ReplayInfoQueryValues

            ret["num_players"] = query.size()
            query.first()
            ret["featured_mod"] = str(_qv(query, RV.GAMEMOD))
            ret["game_type"] = int(_qv(query, RV.GAMETYPE) or 0)
            ret["title"] = str(_qv(query, RV.GAMENAME).encode('utf-8'))
            ret["featured_mod_versions"] = self._featured_mod_versions(
                _qv(query, RV.GAMEMOD))
            mapname = str(_qv(query, RV.FILENAME))
            ret["mapname"] = os.path.splitext(os.path.basename(mapname))[0]
            ret["complete"] = True

            query.previous()
            teams = {}
            while next(query):
                team = int(_qv(query, RV.TEAM))
                name = str(_qv(query, RV.LOGIN))
                isAi = int(_qv(query, RV.AI))

                if int(_qv(query, RV.HOST)) == int(_qv(query, RV.PLAYER_ID)):
                    ret["host"] = name
                if isAi == 0:
                    if team not in teams:
                        teams[team] = []
                    teams[team].append(name)
            ret["teams"] = teams
            return ret

    def _featured_mod_versions(self, modname):
        ret = {}
        mod_table = "updates_{}".format(modname)
        mod_files_table = "{}_files".format(mod_table)

        query = QSqlQuery(self.db)
        query.prepare("""
        SELECT fileId, MAX(version)
            FROM `{mod_files_table}`
                LEFT JOIN {mod_table}
                    ON `fileId` = {mod_table}.id
            GROUP BY fileId
        """.format(mod_files_table=mod_files_table, mod_table=mod_table))
        query.exec_()

        MV = self.ModInfoQueryValues
        while next(query):
            ret[int(_qv(query, MV.FILE_ID))] = int(_qv(query, MV.VERSION))
        return ret

    def add_replay_entry(self, uid):
        with DbContext(self.db):
            query = QSqlQuery(self.db)
            query.prepare("INSERT INTO `game_replays`(`UID`) VALUES (?)")
            query.addBindValue(self.uid)
            if not query.exec_():
                self.__logger.debug("error adding replay to database")
