# -*- coding: utf-8 -*-
"""
/***************************************************************************
Name                 : Sorted list by thread
Description          : Using thread for sorted a list
Date                 : July, 2015
copyright            : (C) 2015 by Luiz Motta
email                : motta.luiz@gmail.com

 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

from PyQt4.QtCore import ( 
     Qt, QObject, QThread, pyqtSignal, pyqtSlot, QEventLoop
)


class WorkerSorted(QObject):

  finished = pyqtSignal( list )

  def __init__(self, lst, key, reverse):

    super(WorkerSorted, self).__init__()
    ( self.lst, self.key, self.reverse )  = ( lst, key, reverse )

  def run(self):
    self.finished.emit( sorted( self.lst, key = self.key, reverse = self.reverse ) )


class SortedListByThread(QObject):
  def __init__(self):
    super(SortedListByThread, self).__init__()
    self.thread = self.worker = None

  def run(self, lst, key, reverse):
    def finished( l_sorted ):
      self.sortedList = l_sorted
      loop.exit()
    
    self.worker = WorkerSorted( lst, key, reverse )
    self.thread = QThread( self )
    loop = QEventLoop()
    self.sortedList = None

    self.worker.moveToThread( self.thread )
    self.thread.started.connect( self.worker.run )
    self.worker.finished.connect( finished )
    self.thread.start()
    loop.exec_()
    self._finishThread()

    return self.sortedList

  def kill(self):
    if not self.thread is None:
      self._finishThread()

  def _finishThread(self):
    self.thread.quit()
    self.thread.wait()
    self.thread.deleteLater()
    self.thread = self.worker = None
