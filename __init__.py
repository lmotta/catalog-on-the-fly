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

__author__ = 'Luiz Motta'
__date__ = '2015-04-01'
__copyright__ = '(C) 2015, Luiz Motta'
__revision__ = '$Format:%H$'


import os, stat, sys, re, shutil, filecmp

from qgis.PyQt.QtCore import Qt, QObject, QSettings, QCoreApplication, pyqtSlot
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from qgis.core import Qgis, QgsProject

from .catalogotf import DockWidgetCatalogOTF
from .translate import Translate

def classFactory(iface):
    return CatalogOTFPlugin( iface )

class CatalogOTFPlugin(QObject):
    def __init__(self, iface):
        super().__init__()
        self.iface = iface
        # self.projOTF = ProjectDockWidgetCatalogOTF( iface )
        self.name = u'&Catalog OTF'
        self.dock = None
        self.translate = Translate('catalogotf')

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
        name = 'Catalog OTF'
        about = QCoreApplication.translate('CatalogOTF', 'Adding images from catalog layer')
        icon = QIcon( os.path.join( os.path.dirname(__file__), 'catalogotf.svg' ) )
        self.action = QAction( icon, name, self.iface.mainWindow() )
        self.action.setObjectName( name.replace(' ', '') )
        self.action.setWhatsThis( about )
        self.action.setStatusTip( about )
        self.action.setCheckable( True )
        self.action.triggered.connect( self.run )

        self.iface.addRasterToolBarIcon( self.action )
        self.iface.addPluginToRasterMenu( self.name, self.action )

        #self._connect()

        self.dock = DockWidgetCatalogOTF( self.iface )
        self.iface.addDockWidget( Qt.RightDockWidgetArea , self.dock )
        self.dock.visibilityChanged.connect( self.dockVisibilityChanged )

    def unload(self):
        self.iface.removeRasterToolBarIcon( self.action )
        self.iface.removePluginRasterMenu( self.name, self.action )
        self.dock.close()
        self.dock = None
        # self._connect( False )

    @pyqtSlot()
    def run(self):
        if self.dock.isVisible():
            self.dock.hide()
        else:
            self.dock.show()

    @pyqtSlot(bool)
    def dockVisibilityChanged(self, visible):
        self.action.setChecked( visible )
