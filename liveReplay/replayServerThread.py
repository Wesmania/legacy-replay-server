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

from PyQt5 import QtCore, QtNetwork
import logging
from .replays import replay, replayWriter, session


class session(object):
    def __init__(self, socket):
        self.socket = socket

    def getSocket(self):
        return self.socket

    def removeSocket(self):
        if self.socket is not None:
            self.socket.abort()


class ReplayThread(QtCore.QObject):
    '''
    This is a simple class that takes all the FA replay data input from its inputSocket, writes it to a file, 
    and relays it to an internet server via its relaySocket.
    '''
    __logger = logging.getLogger(__name__)

    def __init__(self, parent, local_socket, *args, **kwargs):
        QtCore.QObject.__init__(self, *args, **kwargs)

        self.parent = parent

        self.inputSocket = QtNetwork.QTcpSocket(self)
        self.inputSocket.setSocketDescriptor(local_socket)

        self.inputSocket.readyRead.connect(self.readDatas)
        self.inputSocket.disconnected.connect(self.disconnection)

        self.replay = None
        self.replayWriter = None
        self.receivingReplay = False
        self.init = False
        self.listeningReplay = True
        self.newSession = None

    def readDatas(self):
        if self.inputSocket is None:
            return
        if not self.inputSocket.isValid():
            return
        if self.inputSocket.state() != QtNetwork.QAbstractSocket.ConnectedState:
            return

        datas = self.inputSocket.read(self.inputSocket.bytesAvailable())

        if not self.init:
            if datas.startswith(b"P/"):
                index = datas.find(b"\x00")
                replayName = datas[2:index].decode('UTF-8').lower()
                self.__logger.info("New replay received {}".format(replayName))
                if not replayName.endswith(".scfareplay"):
                    self.__logger.warn(("The replay name %s is not valid" % replayName))
                    self.inputSocket.abort()
                    return

                # get the uid
                gameId = int(replayName.split("/")[0])

                # find if a game with the same uid is running
                self.replay = self.parent.replays.get(gameId)
                if self.replay is None:
                    self.replay = replay(gameId, self.parent.db)
                    self.parent.replays.put(self.replay)

                self.replayWriter = replayWriter(self.replay, self)
                self.replayWriter.write(datas[index + 1:])
                self.receivingReplay = True
                self.init = True

            elif datas.startswith("G/"):
                # This session requests a replay

                index = datas.find("\x00")
                replayName = datas[2:index].lower()
                self.__logger.info("New replay requested %s" % replayName)

                # get the uid
                gameId = int(replayName.split("/")[0])

                self.replay = self.parent.replays.get(gameId)
                if self.replay is None:
                    self.__logger.warn(("The requested replay %i is not valid" % gameId))
                    self.inputSocket.abort()
                    return

                self.newSession = session(self.inputSocket)
                self.replay.addListener(self.newSession)
                self.listeningReplay = True

        else:
            if self.receivingReplay:
                self.replayWriter.write(datas)

    def done(self):
        if self.replay is not None:
            if self.receivingReplay:
                self.replayWriter.stop()

            elif self.listeningReplay:
                self.replay.removeListener(self.newSession)

            if not self.replay.isInProgress() and not self.replay.isListened():
                self.__logger.debug("closing replay file")
                self.parent.replays.delete(self.replay)

        if self in self.parent.recorders:
            self.parent.removeRecorder(self)

    def disconnection(self):
        self.__logger.debug("FA disconnected locally")
        self.done()
