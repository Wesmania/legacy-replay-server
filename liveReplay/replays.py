
from PySide import QtCore, QtNetwork, QtGui
from PySide.QtSql import QSqlQuery
import time
import zipfile
import logging
import os, copy
import json
import zlib


DELAY = 300 # Delay in seconds. Add "lag" in the data stream for listeners.

UNIT16 = 8

REPLAY_PATH = "/var/www/faf/replays"
GW_REPLAY_PATH  = "/var/www/faf/gwreplays"

import struct

def readLine(offset, bin):
    line = ''
    while True :
        char = struct.unpack("s", bin[offset:offset+1])
        offset = offset + 1
        if char[0] == '\r' :
            break
        elif char[0] == '\x00' :
            break
        else :
            line = line + char[0]
    return offset, line

def readInt(offset, bin):
    int = struct.unpack("i", bin[offset:offset+4])[0]
    return offset+4, int

class session(object):
    def __init__(self, socket):
        self.socket = socket

    def getSocket(self):
        return self.socket

    def removeSocket(self):
        if self.socket != None :
            self.socket.abort()

    
class replay(object):
    __logger = logging.getLogger("faf.replay")
    __logger.setLevel(logging.DEBUG)
    
    def __init__(self, gameid, replayName, gw=False, parent = None):
        
        self.startTime = time.time()
        self.gw = gw
        self.replayInfo = {}
        self.replayInfo["uid"] = gameid
        self.replayInfo["featured_mod"] = "faf"
        
        self.parent = parent
        self.replayName = replayName
        self.uid = gameid        
        
        self.listeners = []
        self.writers = []
        
        self.fileHandle = None
        
        self.currentWriter = None


    def forceEnd(self):
        self.__logger.debug("forcing ending")
        for listener in self.listeners :
            listener.done()
        
        for writer in self.writers :
            writer.stop()
        
    def getGWReplaysInfos(self):
        self.parent.db.open()
        self.replayInfo["game_end"] = time.time()
        query = QSqlQuery(self.parent.db)
        self.replayInfo["featured_mod"] = "gw"
        self.replayInfo["game_type"] = 0
        query.prepare("SELECT filename, planets.name, avatars.name \
FROM galacticwar.game_stats \
LEFT JOIN galacticwar.game_player_stats ON galacticwar.game_player_stats.`gameId` = galacticwar.game_stats.id \
LEFT JOIN galacticwar.planets ON galacticwar.planets.id = galacticwar.game_stats.planetuid \
LEFT JOIN galacticwar.planet_maps ON galacticwar.planet_maps.planetuid =  galacticwar.game_stats.planetuid \
LEFT JOIN faf_lobby.table_map ON galacticwar.planet_maps.`mapuid` = faf_lobby.table_map.id \
LEFT JOIN galacticwar.avatars ON galacticwar.avatars.id = galacticwar.game_player_stats.`avatarId` \
WHERE galacticwar.game_stats.id = ? ")
        query.addBindValue(self.uid)
        query.exec_()
        if  query.size() != 0: 
            self.replayInfo["num_players"] = query.size()
            query.first()
            mapname = str(query.value(0))
            self.replayInfo["title"] = str("battle on " +query.value(1))
            self.replayInfo["featured_mod_versions"] = {}
            tableMod = "updates_gw" 
            tableModFiles = tableMod + "_files"
            
            query2 = QSqlQuery(self.parent.db)
            query2.prepare("SELECT fileId, MAX(version) FROM `%s` LEFT JOIN %s ON `fileId` = %s.id GROUP BY fileId" % (tableModFiles, tableMod, tableMod))
            query2.exec_()
            if query2.size() != 0 :
                while query2.next() :
                    self.replayInfo["featured_mod_versions"][int(query2.value(0))] = int(query2.value(1))  
            
            self.replayInfo["mapname"] = os.path.splitext(os.path.basename(mapname))[0]
            self.replayInfo["complete"] = True
   
        self.parent.db.close()
        
    def getReplaysInfos(self):
        #general stats
        self.parent.db.open()
        
        self.replayInfo["game_end"] = time.time()
        query = QSqlQuery(self.parent.db)
        queryStr = ("SELECT game_featuredMods.gamemod, gameType, filename, gameName, host, login, playerId, AI, team FROM `game_stats` LEFT JOIN game_player_stats ON `game_player_stats`.`gameId` = game_stats.id LEFT JOIN table_map ON `game_stats`.`mapId` = table_map.id LEFT JOIN login ON login.id = `game_player_stats`.`playerId`  LEFT JOIN  game_featuredMods ON `game_stats`.`gameMod` = game_featuredMods.id WHERE game_stats.id = %i" % self.uid)
        query.exec_(queryStr)
        if  query.size() != 0: 
            self.replayInfo["num_players"] = query.size()
            query.first()
            self.replayInfo["featured_mod"] = str(query.value(0))
            self.replayInfo["game_type"] = int( query.value(1))
            mapname = str(query.value(2))
            self.replayInfo["title"] = str(query.value(3).encode('utf-8'))
            
            self.replayInfo["featured_mod_versions"] = {}
            # checking featured mod version
            tableMod = "updates_" + str(query.value(0))
            tableModFiles = tableMod + "_files"
            
            query2 = QSqlQuery(self.parent.db)
            query2.prepare("SELECT fileId, MAX(version) FROM `%s` LEFT JOIN %s ON `fileId` = %s.id GROUP BY fileId" % (tableModFiles, tableMod, tableMod))
            query2.exec_()
            if query2.size() != 0 :
                while query2.next() :
                    self.replayInfo["featured_mod_versions"][int(query2.value(0))] = int(query2.value(1))  

            self.replayInfo["mapname"] = os.path.splitext(os.path.basename(mapname))[0]
            
            self.replayInfo["complete"] = True
            
            teams = {}
            
            while query.next() :

                team = int(query.value(8))
                name = str(query.value(5))
                isAi = int(query.value(7))
                
                if int(query.value(4)) == int(query.value(6)) :
                    self.replayInfo["host"] = name
                
                if isAi == 0 :
                    if not team in teams :
                        teams[team] = []

                    teams[team].append(name)
            
            self.replayInfo["teams"] = teams
        self.parent.db.close()


    def dataAdded(self):
        for listener in self.listeners :
            listener.sendDatas(True)


    def switchData(self, stream):
        self.fileHandle = stream
        for listener in self.listeners :
            listener.newStream() 
    
    def getReplayData(self):
        return self.fileHandle     
    
    def __len__(self):
        return self.fileHandle.length() 

    def addWriter(self, writer):
        self.writers.append(writer)

            

    def removeWriter(self, writer):
        if writer in self.writers :
            
            if len(self.writers) == 1 :
                #writer.sendRestOfDatas()
                for listener in self.listeners :
                    listener.sendDatas(False)
                    listener.neverSwitch = True
                
                self.done()
            
            self.writers.remove(writer)

    def addListener(self, session):
        
        listener = replayListener(self, session)
        self.listeners.append(listener)
        listener.newStream()

    def removeListener(self, session):
        self.__logger.debug("removing listener")
        for listener in reversed(self.listeners) :
            if listener.getSession() == session :
                listener.done()
                self.listeners.remove(listener)
                break    

    def getListeners(self):
        return self.listeners
    
    def isListened(self):
        if len(self.listeners) != 0 :
            return True
        else : 
            return False

    def isInProgress(self):
        if len(self.writers) > 0 :
            return True
        else :
            return False
        
    def done(self):
        #writing file
        self.__logger.debug("writing the replay")
        self.__logger.debug(self.uid)
        
        if self.gw :
            self.getGWReplaysInfos()
        else:
            self.getReplaysInfos()
        
        path = REPLAY_PATH
        if self.gw :
            path = GW_REPLAY_PATH

        # NOTE : this will write a temporary file in the disk as the replay is saved in the DB.
        # It was originally written on the disk, and can be reverted to that state as the code is the same.

        filename = os.path.join(path, str(self.uid) + ".fafreplay")
        writeFile = QtCore.QFile(filename)
        if(writeFile.open(QtCore.QIODevice.WriteOnly)) :

            writeFile.write(json.dumps(self.replayInfo))
            writeFile.write('\n')

            replayData = QtCore.QByteArray()
            
            replayDataQByte = QtCore.QByteArray()
            replayDataStream = QtCore.QDataStream(replayDataQByte, QtCore.QIODevice.WriteOnly)
            
            
            replayStream = QtCore.QDataStream(self.getReplayData(), QtCore.QIODevice.ReadOnly)
            replayStream.device().seek(0)
            
            while replayStream.atEnd() == False :
                        
                timePacket = replayStream.readDouble()
                lenData = replayStream.readUInt32()
                datas = replayStream.readRawData(lenData)
                replayData.append(datas)
            
            replayDataStream.writeUInt32(replayData.size())
            replayDataStream.writeRawData(zlib.compress(replayData.data(),9))


            
            
            writeFile.write(replayDataQByte.toBase64())


        writeFile.close()
        
        result = open(str(writeFile.fileName())).read()
        
        # We put the replay inside the Database.
        self.parent.db.open()
        query = QSqlQuery(self.parent.db)
        if self.gw :
            query.prepare("INSERT INTO `galacticwar`.`game_replays`(`UID`, `file`) VALUES (?,?)")
        else :
            query.prepare("INSERT INTO `game_replays`(`UID`, `file`) VALUES (?,?)")
        query.addBindValue(self.uid)
        query.addBindValue(result)
        if query.exec_() :
            os.remove(str(writeFile.fileName())) # THIS is deleted the replay. If removed, it's reverted to the old system
            
        self.parent.db.close()
        
        
       
        self.__logger.debug("fafreplay written")
       

            

class replayListener(object):
    __logger = logging.getLogger("faf.replay.listener")
    __logger.setLevel(logging.DEBUG)    
    
    def __init__(self, replay, session, parent = None):
        self.parent = parent
        self.replay = replay
        self.session = session

        self.pos = 0

        self.replaySent = QtCore.QByteArray()
        
        self.timePacket = 0
        self.packetTimeRead = False

        self.neverSwitch = False
        self.replaydatas = None



    def stripHeader(self, bin):
        offset = 0
        offset, supcomVersion = readLine(offset, bin)
        offset = offset + 3
        offset, replayVersion = readLine(offset, bin)
        offset = offset + 1
        offset, map = readLine(offset, bin)
        offset = offset + 4
        offset, count = readInt(offset, bin)
        offset = offset + count
        offset, count = readInt(offset, bin)
        offset = offset + count
        
        numSource = struct.unpack("b", bin[offset:offset+1])[0]
        offset = offset + 1
        
        for i in range(numSource) :
            offset, name = readLine(offset, bin)
            offset = offset + 4
        
        offset = offset + 1
        
        numArmies = struct.unpack("b", bin[offset:offset+1])[0]
        offset = offset + 1
        
        for i in range(0,numArmies) :
            offset, val = readInt(offset, bin)
            offset = offset + val
            b = struct.unpack("b", bin[offset:offset+1])[0]
            offset = offset + 1
            if b != -1 :
                offset = offset + 1     
        
        offset, randomSeed = readInt(offset, bin)
        return bin[offset:]




    def newStream(self):
        try :
            if self.neverSwitch == True :
                self.__logger.debug("We are trying to switch a completed replay")
                return
    
            self.replaydatas = QtCore.QDataStream(self.replay.getReplayData(), QtCore.QIODevice.ReadOnly)
            
            if self.replaySent.length() == 0 :
                return
            
            old_replay_sent = self.stripHeader(QtCore.QByteArray(self.replaySent))
    
            self.replaySent = QtCore.QByteArray()
            
            while True :
                if self.replaydatas.atEnd() :
                    break
            
                self.replaydatas.readDouble()
                lenData = self.replaydatas.readUInt32()
                data = self.replaydatas.readRawData(lenData)  
            
                self.replaySent.append(data)
                
                if self.replaySent.contains(old_replay_sent) :
                    # we are at a point where the old replay was already sent.
                    # We check if we miss some datas.
                    if old_replay_sent.length() != (self.replaySent.length() - self.replaySent.indexOf(old_replay_sent)) :
                        # if the length of the old replay is different than the current one minus the header..
                        self.session.getSocket().write(self.replaySent[self.replaySent.indexOf(old_replay_sent)+old_replay_sent.length():])
                        # we send it !
                        self.__logger.info("Sending left over")
                    
                    # and we stop sending more.
                    break
            
            
            self.packetTimeRead = False
        except :
            self.__logger.exception("Something awful happened while switching threads !")
            

    def sendDatas(self, timeCheck):         
        while True :
            
            if not self.replaydatas :
                return
            
            if self.replaydatas.atEnd() :
                return
            
            if self.packetTimeRead == False :
                #print "read new packet time"
                self.timePacket = self.replaydatas.readDouble()
                self.packetTimeRead = True
                

            if time.time() - self.timePacket > DELAY or timeCheck == False :
                
                lenData = self.replaydatas.readUInt32()
                datas = self.replaydatas.readRawData(lenData)
                
                socket = self.session.getSocket()
                if socket != None :
                    if socket.isValid() and socket.state() == 3 :
                        self.session.getSocket().write(datas)
                        self.replaySent.append(datas)
                        
                self.packetTimeRead = False

                
            else :

                return
       
    def getSession(self):
        return self.session
    
    def done(self):
        self.session.removeSocket()
        self.replaydatas = None


class replayWriter(object):
    
    __logger = logging.getLogger("faf.replay.writer")
    __logger.setLevel(logging.DEBUG)
        
    def __init__(self, replay, parent = None):
        
        
        self.parent = parent
        self.replay = replay

        
        self.readPos = 0
        self.writePos = 0
        
        self.replay.addWriter(self)
        
        self.writerStream = QtCore.QByteArray()
        
        self.stream = QtCore.QDataStream(self.writerStream, QtCore.QIODevice.ReadWrite) 
        
    
    def stop(self):
        self.replay.removeWriter(self)
        if self.replay.currentWriter == self :
            self.replay.currentWriter = None
        self.writerStream.clear()
        self.writerStream = None
        self.stream = None
        self.parent.inputSocket.abort()
    
  
   
    def write(self, datas):
        
        if self.replay.currentWriter == None :
            self.replay.switchData(self.writerStream)
            self.replay.currentWriter = self
        
        if len(datas) > 0 :
            curTime = float(time.time())

            self.stream.writeDouble(curTime)
            self.stream.writeUInt32(len(datas))
            self.stream.writeRawData(datas)
            
        
            if self.replay.currentWriter == self :
                self.replay.dataAdded() 

    def getName(self):
        return self.replayName
    
        
class replays(object):
    
    __logger = logging.getLogger("faf.replays.container")
    __logger.setLevel(logging.DEBUG)
    
    def __init__(self):
        self.replays = []
        self.gwreplays = []
        
    def get(self, gameid, gw=False):
        result = None
        if gw :
            for replay in self.gwreplays :
                if replay.uid == gameid and replay.isInProgress() :
                    self.__logger.debug("replay found")
                    return replay            
        else :
            for replay in self.replays :
                if replay.uid == gameid and replay.isInProgress() :
                    self.__logger.debug("replay found")
                    return replay
           
        return result 
    
    def delete(self, replay, gw = False):
        self.__logger.debug("deleting replay called")
        
        if gw :
            if replay in self.gwreplays :
                self.__logger.info("deleting replay %s" % str(replay.uid))
                self.gwreplays.remove(replay)
                #del replay            
        else :
            if replay in self.replays :
                self.__logger.info("deleting replay %s" % str(replay.uid))
                self.replays.remove(replay)
                #del replay
    
    def checkOldReplays(self):
        ## check if some old replays are still in memory.
        toRemove = []
        for r in self.replays :
            diff = time.time() - r.startTime
            if diff > 14400 :
                 self.__logger.debug("old replay detected")
                 r.forceEnd()
                 toRemove.append(r)
                 
        for replay in toRemove :
            self.delete(replay)
                 
        toRemove = []
        for r in self.gwreplays :
            diff = time.time() - r.startTime
            if diff > 14400 :
                 self.__logger.debug("old replay detected")
                 r.forceEnd()
                 toRemove.append(r)
                 
        for replay in toRemove :
            self.delete(replay, True)


    
    def put (self, replay, gw = False):
        self.checkOldReplays()
        if gw :
            self.gwreplays.append(replay)
        else :
            self.replays.append(replay)
    