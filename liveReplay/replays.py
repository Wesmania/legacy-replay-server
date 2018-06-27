#-------------------------------------------------------------------------------
# Copyright (c) 2014 Gael Honorez.
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the GNU Public License v3.0
# which accompanies this distribution, and is available at
# http://www.gnu.org/licenses/gpl.html
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#-------------------------------------------------------------------------------

from PyQt5 import QtCore
import time
import logging
import os
import json
import zlib
from configobj import ConfigObj
import struct

config = ConfigObj("replayserver.conf")
DELAY = 300  # Delay in seconds. Add "lag" in the data stream for listeners.


def readLine(offset, bin):
    line = ''
    while True:
        char = struct.unpack("s", bin[offset:offset + 1])
        offset = offset + 1
        if char[0] == '\r':
            break
        elif char[0] == '\x00':
            break
        else:
            line = line + char[0]
    return offset, line


def readInt(offset, bin):
    int = struct.unpack("i", bin[offset:offset + 4])[0]
    return offset + 4, int


class replay(object):
    __logger = logging.getLogger(__name__)

    def __init__(self, gameid, db):
        self.startTime = time.time()
        self.replayInfo = {}
        self.replayInfo["uid"] = gameid
        self.replayInfo["featured_mod"] = "faf"

        self.db = db
        self.uid = gameid

        self.listeners = []
        self.writers = []

        self.fileHandle = None

        self.currentWriter = None

    def forceEnd(self):
        self.__logger.debug("forcing ending")
        for listener in self.listeners:
            listener.done()

        for writer in self.writers:
            writer.stop()

    def dataAdded(self):
        for listener in self.listeners:
            listener.sendDatas(True)

    def switchData(self, stream):
        self.fileHandle = stream
        for listener in self.listeners:
            listener.newStream()

    def getReplayData(self):
        return self.fileHandle

    def __len__(self):
        return self.fileHandle.length()

    def addWriter(self, writer):
        self.writers.append(writer)

    def removeWriter(self, writer):
        if writer not in self.writers:
            return

        if len(self.writers) == 1:
            # writer.sendRestOfDatas()
            for listener in self.listeners:
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
        for listener in reversed(self.listeners):
            if listener.getSession() == session:
                listener.done()
                self.listeners.remove(listener)
                break

    def getListeners(self):
        return self.listeners

    def isListened(self):
        if len(self.listeners) != 0:
            return True
        else:
            return False

    def isInProgress(self):
        if len(self.writers) > 0:
            return True
        else:
            return False

    def done(self):
        # writing file
        self.__logger.debug("writing the replay")
        self.__logger.debug(self.uid)

        replay_info = self.db.replay_info(self.uid)
        if replay_info is not None:
            self.replayInfo.update(replay_info)

        # Construct the path where the replay is stored
        path = config['global']['content_path'] + "vault/replay_vault"

        dirsize = 100
        depth = 5
        i = depth
        dirname = path
        while i > 1:
            dirname = dirname + "/" + str((self.uid / (dirsize**(i - 1))) % dirsize)
            i = i - 1

        filename = dirname + "/" + str(self.uid) + ".fafreplay"
        self.__logger.debug("filename: " + filename)

        if not os.path.exists(dirname):
            os.makedirs(dirname)

        writeFile = QtCore.QFile(filename)
        if writeFile.open(QtCore.QIODevice.WriteOnly):
            writeFile.write(json.dumps(self.replayInfo))
            writeFile.write('\n')

            replayData = QtCore.QByteArray()

            replayDataQByte = QtCore.QByteArray()
            replayDataStream = QtCore.QDataStream(replayDataQByte, QtCore.QIODevice.WriteOnly)

            replayStream = QtCore.QDataStream(self.getReplayData(), QtCore.QIODevice.ReadOnly)
            replayStream.device().seek(0)

            while not replayStream.atEnd():
                timePacket = replayStream.readDouble()
                lenData = replayStream.readUInt32()
                datas = replayStream.readRawData(lenData)
                replayData.append(datas)

            replayDataStream.writeUInt32(replayData.size())
            replayDataStream.writeRawData(zlib.compress(replayData.data(), 9))

            writeFile.write(replayDataQByte.toBase64())

        writeFile.close()

        self.db.add_replay_entry(self.uid)
        self.__logger.debug("fafreplay written")


class replayListener(object):
    __logger = logging.getLogger(__name__)

    def __init__(self, replay, session, parent=None):
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

        numSource = struct.unpack("b", bin[offset:offset + 1])[0]
        offset = offset + 1

        for i in range(numSource):
            offset, name = readLine(offset, bin)
            offset = offset + 4

        offset = offset + 1

        numArmies = struct.unpack("b", bin[offset:offset + 1])[0]
        offset = offset + 1

        for i in range(0, numArmies):
            offset, val = readInt(offset, bin)
            offset = offset + val
            b = struct.unpack("b", bin[offset:offset + 1])[0]
            offset = offset + 1
            if b != -1:
                offset = offset + 1

        offset, randomSeed = readInt(offset, bin)
        return bin[offset:]

    def newStream(self):
        try:
            if self.neverSwitch == True:
                self.__logger.debug("We are trying to switch a completed replay")
                return

            self.replaydatas = QtCore.QDataStream(self.replay.getReplayData(), QtCore.QIODevice.ReadOnly)

            if self.replaySent.length() == 0:
                return

            old_replay_sent = self.stripHeader(QtCore.QByteArray(self.replaySent))

            self.replaySent = QtCore.QByteArray()

            while True:
                if self.replaydatas.atEnd():
                    break

                self.replaydatas.readDouble()
                lenData = self.replaydatas.readUInt32()
                data = self.replaydatas.readRawData(lenData)

                self.replaySent.append(data)

                if self.replaySent.contains(old_replay_sent):
                    # we are at a point where the old replay was already sent.
                    # We check if we miss some datas.
                    if old_replay_sent.length() != (self.replaySent.length() - self.replaySent.indexOf(old_replay_sent)):
                        # if the length of the old replay is different than the current one minus the header..
                        self.session.getSocket().write(self.replaySent[self.replaySent.indexOf(old_replay_sent) + old_replay_sent.length():])
                        # we send it !
                        self.__logger.info("Sending left over")

                    # and we stop sending more.
                    break

            self.packetTimeRead = False
        except:
            self.__logger.exception("Something awful happened while switching threads !")

    def sendDatas(self, timeCheck):
        while True:
            if not self.replaydatas:
                return
            if self.replaydatas.atEnd():
                return

            if not self.packetTimeRead:
                # print "read new packet time"
                self.timePacket = self.replaydatas.readDouble()
                self.packetTimeRead = True

            if time.time() - self.timePacket > DELAY or not timeCheck:
                lenData = self.replaydatas.readUInt32()
                datas = self.replaydatas.readRawData(lenData)
                socket = self.session.getSocket()
                if socket is not None:
                    if socket.isValid() and socket.state() == 3:
                        self.session.getSocket().write(datas)
                        self.replaySent.append(datas)
                self.packetTimeRead = False
            else:
                return

    def getSession(self):
        return self.session

    def done(self):
        self.session.removeSocket()
        self.replaydatas = None


class replayWriter(object):
    def __init__(self, replay, parent=None):

        self.parent = parent
        self.replay = replay

        self.readPos = 0
        self.writePos = 0

        self.replay.addWriter(self)

        self.writerStream = QtCore.QByteArray()

        self.stream = QtCore.QDataStream(self.writerStream, QtCore.QIODevice.ReadWrite)

    def stop(self):
        self.replay.removeWriter(self)
        if self.replay.currentWriter == self:
            self.replay.currentWriter = None
        self.writerStream.clear()
        self.writerStream = None
        self.stream = None
        self.parent.inputSocket.abort()

    def write(self, datas):

        if self.replay.currentWriter is None:
            self.replay.switchData(self.writerStream)
            self.replay.currentWriter = self

        if len(datas) > 0:
            curTime = float(time.time())

            self.stream.writeDouble(curTime)
            self.stream.writeUInt32(len(datas))
            self.stream.writeRawData(datas)

            if self.replay.currentWriter == self:
                self.replay.dataAdded()


class replays(object):
    def __init__(self):
        self.replays = []

    def get(self, gameid):
        for replay in self.replays:
            if replay.uid == gameid and replay.isInProgress():
                return replay
        return None

    def delete(self, replay):
        if replay in self.replays:
            self.replays.remove(replay)

    def checkOldReplays(self):
        # check if some old replays are still in memory.
        toRemove = []
        for r in self.replays:
            diff = time.time() - r.startTime
            if diff > 14400:
                r.forceEnd()
                toRemove.append(r)
        for replay in toRemove:
            self.delete(replay)

    def put(self, replay):
        self.checkOldReplays()
        self.replays.append(replay)
