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

from PySide import QtCore, QtNetwork, QtGui, QtSql

import time
import os
import logging
import sys

DB_HOSTNAME = "localhost"
DB_PORT     = 3306
DB_DATABASE = "faf_lobby"
DB_LOGIN    = "login"
DB_PASSWORD = "password"

from faPackets import Packet
UNIT16 = 8

from replayServerThread import ReplayThread
from replays import *

class ReplayServer(QtNetwork.QTcpServer):
    ''' 
    This is a local listening server that FA can send its replay data to.
    It will instantiate a fresh ReplayThread for each FA instance that launches.
    '''
    __logger = logging.getLogger("faf.replays.server")
    __logger.setLevel(logging.DEBUG)

    def __init__(self, local_port, *args, **kwargs):
        QtNetwork.QTcpServer.__init__(self, *args, **kwargs)
 
        self.db= QtSql.QSqlDatabase.addDatabase("QMYSQL")  
        self.db.setHostName(DB_HOSTNAME)  
        self.db.setPort(DB_PORT)
        self.setMaxPendingConnections(1)
        self.db.setDatabaseName(DB_DATABASE)  
        self.db.setUserName(DB_LOGIN)  
        self.db.setPassword(PASSWORD_DB)
        
        self.recorders = []
           
        self.replays = replays()
        self.__logger.debug("initializing...")
        #self.newConnection.connect(self.acceptConnection)
        while not self.isListening():
            self.listen(QtNetwork.QHostAddress.Any, local_port)
            if (self.isListening()):
                self.__logger.debug("listening on address " + self.serverAddress().toString() + ":" + str(self.serverPort()))
            else:
                self.__logger.error("cannot listen, port probably used by another application: " + str(local_port))
                answer = QtGui.QMessageBox.question(None, "Port Occupied", "FAF couldn't start its local replay server, which is needed to play Forged Alliance online. Possible reasons:<ul><li><b>FAF is already running</b> (most likely)</li><li>another program is listening on port {port}</li></ul>".format(port=local_port), QtGui.QMessageBox.Retry, QtGui.QMessageBox.Abort)
                if answer == QtGui.QMessageBox.Abort:
                    sys.exit()
              
    def removeRecorder(self, recorder):
        if recorder in self.recorders:
            self.recorders.remove(recorder)
            recorder.deleteLater()


    def incomingConnection(self, socketId):
        self.recorders.append(ReplayThread(self, socketId))
             
            
