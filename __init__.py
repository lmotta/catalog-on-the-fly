# -*- coding: utf-8 -*-
"""
/***************************************************************************
Name                 : Catalog on the fly
Description          : Automatically adds  images that are in the catalog layer that intersect with the map area.
Date                 : April, 2015
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

from PyQt4.QtGui import ( QAction, QIcon )
from PyQt4.QtCore import ( Qt, pyqtSlot )

from catalogotf import DockWidgetCatalogOTF

def classFactory(iface):
  return CatalogOTFPlugin( iface )

class CatalogOTFPlugin:

  def __init__(self, iface):
    self.iface = iface
    self.name = u"&Catalog OTF"
    self.dock = None

  def initGui(self):
    import resources_rc # pyrcc4 -o resources_rc.py  resources_rc.qrc
    self.action = QAction( QIcon(":/plugins/catalogotf_plugin/catalogotf.svg"), u"Catalog on the fly", self.iface.mainWindow() )
    self.action.triggered.connect( self.run )
    #
    self.iface.addToolBarIcon( self.action )
    self.iface.addPluginToMenu( self.name, self.action )

  def unload(self):
    self.iface.removePluginMenu( self.name, self.action )
    self.iface.removeToolBarIcon( self.action )
    del self.action
    del self.dock
  
  @pyqtSlot()
  def run(self):
    self.dock = DockWidgetCatalogOTF( self.iface ) 
    self.iface.addDockWidget( Qt.LeftDockWidgetArea , self.dock )
    self.action.setEnabled( False )
    
