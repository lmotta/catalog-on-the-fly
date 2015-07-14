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

import os.path

from PyQt4.QtGui import ( QAction, QIcon )
from PyQt4.QtCore import ( Qt, QSettings, QTranslator, QCoreApplication, qVersion, pyqtSlot )

from qgis.core import ( QgsProject, QgsMapLayerRegistry )

from catalogotf import ( ProjectDockWidgetCatalogOTF, DockWidgetCatalogOTF )

def classFactory(iface):
  return CatalogOTFPlugin( iface )

class CatalogOTFPlugin:

  def __init__(self, iface):

    def translate():
      #
      # For create file 'qm'
      # 1) Define that files need for translation: catalogotf.pro
      # 2) Create 'ts': pylupdate4 -verbose catalogotf.pro
      # 3) Edit your translation: QtLinquist
      # 4) Create 'qm': lrelease catalogotf_pt_BR.ts
      #
      dirname = os.path.dirname( os.path.abspath(__file__) )
      locale = QSettings().value("locale/userLocale")
      localePath = os.path.join( dirname, "i18n", "%s_%s.qm" % ( name_src, locale ) )
      if os.path.exists(localePath):
        self.translator = QTranslator()
        self.translator.load(localePath)
        if qVersion() > '4.3.3':
          QCoreApplication.installTranslator(self.translator)      

    self.iface = iface
    self.projOTF = ProjectDockWidgetCatalogOTF( iface )
    self.name = u"&Catalog OTF"
    self.dock = None
    name_src = "catalogotf"
    translate()

  def _connect(self, isConnect = True):
    signal_slot = (
      { 'signal': QgsProject.instance().readProject, 'slot': self.projOTF.onReadProject },
      { 'signal': QgsProject.instance().writeProject, 'slot': self.projOTF.onWriteProject }
    )
    if isConnect:
      for item in signal_slot:
        item['signal'].connect( item['slot'] )
    else:
      for item in signal_slot:
        item['signal'].disconnect( item['slot'] )

  def initGui(self):
    msgtrans = QCoreApplication.translate("CatalogOTF", "Catalog on the fly")
    icon = QIcon( os.path.join( os.path.dirname(__file__), 'catalogotf.svg' ) )
    self.action = QAction( icon, msgtrans, self.iface.mainWindow() )
    self.action.setObjectName("CatalogOTF")
    self.action.setWhatsThis( msgtrans )
    self.action.setStatusTip( msgtrans )
    self.action.triggered.connect( self.run )

    self.iface.addToolBarIcon( self.action )
    self.iface.addPluginToRasterMenu( self.name, self.action )

    self._connect()

  def unload(self):
    self.iface.removePluginMenu( self.name, self.action )
    self.iface.removeToolBarIcon( self.action )
    del self.action
    del self.dock
    self._connect( False )
  
  @pyqtSlot()
  def run(self):
    self.dock = DockWidgetCatalogOTF( self.iface ) 
    self.iface.addDockWidget( Qt.LeftDockWidgetArea , self.dock )
    self.action.setEnabled( False )
    
