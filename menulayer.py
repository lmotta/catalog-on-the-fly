#!/usr/bin/python3
# # -*- coding: utf-8 -*-
"""
/***************************************************************************
Name                 : Menu Layer
Description          : Classes for add Menu in layer
Date                 : February, 2020
copyright            : (C) 2020 by Luiz Motta
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

from qgis.PyQt.QtCore import QObject, pyqtSlot
from qgis.PyQt.QtWidgets import QApplication, QAction

from qgis.core import (
    QgsProject,
    QgsMapLayer,
    QgsGeometry,
    QgsFeature, QgsFeatureRequest
)
import qgis.utils as QgsUtils

from .mapcanvaseffects import MapCanvasGeometry

class MenuTMSXml(QObject):
    def __init__(self):
        def initMenuLayer(menuName):
            self.menuLayer = [
            {
                'menu': u"Zoom",
                'slot': self.zoom,
                'action': None
            },
            ]
            for item in self.menuLayer:
                item['action'] = QAction( item['menu'], None )
                item['action'].triggered.connect( item['slot'] )
                QgsUtils.iface.addCustomActionForLayerType( item['action'], menuName, QgsMapLayer.RasterLayer, False )

        super().__init__()
        initMenuLayer('TMS XML') # self.menuLayer
        self.msgBar = QgsUtils.iface.messageBar()
        self.canvasEffects = MapCanvasGeometry()
        self.project = QgsProject.instance()

    def __del__(self):
        for item in self.menuLayer:
            QgsUtils.iface.removeCustomActionForLayerType( item['action'] )

    def setLayer(self, layer):
        for item in self.menuLayer:
            QgsUtils.iface.addCustomActionForLayer( item['action'],  layer )

    @pyqtSlot(bool)
    def zoom(self, checked):
        layer = QgsUtils.iface.activeLayer()
        wktBBox = layer.customProperty('wktBBox')
        geom = QgsGeometry.fromWkt( wktBBox )
        self.canvasEffects.zoom( [ geom ], layer )
