#!/usr/bin/env python





from PySide.QtCore import QThread, QObject, SIGNAL, SLOT
from PySide.QtCore import QByteArray, QDataStream, QIODevice, QReadWriteLock
from PySide.QtNetwork import QTcpServer, QTcpSocket, QAbstractSocket, QHostInfo
  
from PySide import QtCore, QtNetwork, QtSql
from PySide.QtSql import *

import uuid
import random
import logging

from liveReplay import liveReplayServer

UNIT16 = 8
REPLAY_SERVER_PORT = 15000

class start(QObject):

    def __init__(self, parent=None):

        super(start, self).__init__(parent)
        self.logger = logging.getLogger('replayServer')

        
        self.replayServer =  liveReplayServer.ReplayServer(REPLAY_SERVER_PORT)
  



logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
    datefmt='%m-%d %H:%M'
    )
x = logging.getLogger("replayServer")
x.setLevel(logging.DEBUG)

h = logging.StreamHandler()

x.addHandler(h)
h1 = logging.FileHandler("replayServer.log")

h1.setLevel(logging.DEBUG)
x.addHandler(h1)


if __name__ == '__main__':
    logger = logging.getLogger("replayServer")
    import sys
    

    try:
        
        app = QtCore.QCoreApplication(sys.argv)
        server = start()
        app.exec_()
    
    except Exception, ex:
        
        logger.exception("Something awful happened!")
        logger.debug("Finishing main")

