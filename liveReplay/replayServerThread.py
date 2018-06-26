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

from PySide import QtCore, QtNetwork, QtGui

from PySide.QtNetwork import QTcpSocket

import time
import os
import logging

import sys

from .replays import replay, replayWriter, session

import logging

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

        if self.inputSocket != None :
            if self.inputSocket.isValid() and self.inputSocket.state() == 3 :
                datas = self.inputSocket.read(self.inputSocket.bytesAvailable())
                datas = str(datas) # Useless in PySide. It's a PyQt4 leftover. I kept lot of them to be sure to not break anything.
                
                # Record locally
                
                if self.init == False :
                    gw = False
                    if datas.startswith("P/") :                 
                        index = datas.find("\x00")
                        replayName = datas[2:index].lower()
                        self.__logger.info("New replay received %s" % replayName)
                        
                        if replayName.endswith(".gwreplay") == True :
                            gw = True
                        
                        if gw == False and replayName.endswith(".scfareplay") == False :
                            self.__logger.warn(("The replay name %s is not valid" % replayName))
                            self.inputSocket.abort()
                            return
        
                        #get the uid
                        gameId = int(replayName.split("/")[0])
        
                        
                        #find if a game with the same uid is running
        
                        self.replay = self.parent.replays.get(gameId, gw)
                        if self.replay == None :
                            self.replay = replay(gameId, replayName, gw, self.parent)
                            self.parent.replays.put(self.replay, gw)
        
                            
                        self.replayWriter = replayWriter(self.replay, self)
                        
                        self.replayWriter.write(datas[index+1:])
                        self.receivingReplay = True
                        self.init = True
                        
            
                    elif datas.startswith("G/") :
                        #This session requests a replay
                         
                        index = datas.find("\x00")
                        replayName = datas[2:index].lower()
                        self.__logger.info("New replay requested %s" % replayName)
        
                        #get the uid
                        gameId = int(replayName.split("/")[0])
                     
                        self.replay = self.parent.replays.get(gameId)
                        if self.replay == None :
                            self.__logger.warn(("The requested replay %i is not valid" % gameId))
                            self.inputSocket.abort()
                            return

                        self.newSession = session(self.inputSocket)
                        self.replay.addListener(self.newSession)
                        self.listeningReplay = True
                        
                        
                else :
                    if self.receivingReplay == True : 
                        self.replayWriter.write(datas)

    def done(self):
      
        if self.replay != None :
            if self.receivingReplay :
                self.replayWriter.stop()
            
            elif self.listeningReplay :
                self.replay.removeListener(self.newSession)
                
            if self.replay.isInProgress() == False and self.replay.isListened() == False :
                self.__logger.debug("closing replay file")
                self.parent.replays.delete(self.replay)

        if self in self.parent.recorders :
            self.parent.removeRecorder(self)        

    def disconnection(self):
        self.__logger.debug("FA disconnected locally")
        self.done()
