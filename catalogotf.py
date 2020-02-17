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


import urllib.request
import urllib.error

from os.path import basename, dirname, join as joinPath
from enum import Enum

from qgis.PyQt.QtCore import (
    QObject, Qt, QCoreApplication,
    QVariant, QDate,
    QFileInfo, QDir, QStandardPaths,
    pyqtSlot, pyqtSignal,
)

from qgis.PyQt.QtGui import QIcon, QCursor

from qgis.PyQt.QtXml import QDomDocument

from qgis.PyQt.QtWidgets import (
    QWidget, QDockWidget,
    QTableWidget, QTableWidgetItem,
    QVBoxLayout, QHBoxLayout,
    QPushButton,
    QApplication
)

from qgis.core import (
    Qgis, QgsWkbTypes,
    QgsMessageLog,
    QgsApplication, QgsTask, QgsProject,
    QgsLayerTreeNode,
    QgsMapLayerType,
    QgsMapLayer, QgsRasterLayer, QgsFeature,
    QgsFeatureRequest, QgsSpatialIndex,
    QgsCoordinateTransform
)

from qgis import utils as QgsUtils

from .transparencylayer import RasterTransparency
from .menulayer import MenuTMSXml

class TypeLayerTreeGroup(Enum):
    CATALOG = 1
    DATE = 2

class TypeSufixLayerTreeGroup(Enum):
    CANCELLED = 1
    TOTAL = 2

class TypeStatusProcessing(Enum):
    COMPLETE = 1
    CANCELLED = 2

class DockWidgetCatalogOTF(QDockWidget):
    runCatalog  = pyqtSignal(bool, list)
    findCatalog = pyqtSignal()
    def __init__(self, iface):
        def setupUi():
            self.setObjectName('catalogotf_dockwidget')
            wgt = QWidget( self )
            wgt.setAttribute(Qt.WA_DeleteOnClose)
            #
            self.table = QTableWidget(wgt)
            self.table.setSortingEnabled( False )
            self.table.setColumnCount( 1 )
            self.table.itemSelectionChanged.connect( self.selectionChangedTable )
            #
            self.headerTable = QCoreApplication.translate('CatalogOTF', 'Layers({}) - Features')
            self.labelRun = QCoreApplication.translate('CatalogOTF', 'Run({} selected)')
            self.labelCancel = QCoreApplication.translate('CatalogOTF', 'Cancel({} selected)')
            self.tooltipRow = QCoreApplication.translate('CatalogOTF', 'Fields: Source({}) and Date({})')
            labelFind = QCoreApplication.translate('CatalogOTF', 'Find catalog')
            #
            self.table.setHorizontalHeaderLabels( [ self.headerTable.format( 0 ) ] )
            label = QCoreApplication.translate('CatalogOTF', 'Click select all / CTRL+Click unselect all')
            self.table.horizontalHeaderItem(0).setData( Qt.ToolTipRole, label )
            self.table.resizeColumnsToContents()
            #
            label = self.labelRun.format( 0 )
            self.btnRunCancel = QPushButton( label, wgt )
            self.btnRunCancel.setEnabled( False )
            self.btnRunCancel.clicked.connect( self.run )
            #
            self.btnFind = QPushButton( labelFind, wgt )
            self.btnFind.clicked.connect( self.find )
            #
            mainLayout = QVBoxLayout()
            mainLayout.addWidget( self.table )
            lyt = QHBoxLayout()
            lyt.addWidget( self.btnRunCancel )
            lyt.addWidget( self.btnFind )
            mainLayout.addItem( lyt )
            wgt.setLayout( mainLayout )
            #
            self.setWidget( wgt )
            self.isProcessing = False #  Change in 'enableProcessing'

        super().__init__('Catalog OTF', iface.mainWindow() )
        setupUi()
        self.process = ProcessCatalogOTF( self )

    def __del__(self):
        del self.process

    def getLayerIds(self, selected=False):
        rows = map( lambda item: item.row(), self.table.selectedItems() ) if selected else \
               range( self.table.rowCount() )
        vreturn = {}
        for row in rows:
            layerId = self.table.verticalHeaderItem( row ).data( Qt.UserRole )['layerId']
            vreturn[ layerId ] = row
        return vreturn

    def getNameLayer(self, row):
        return self.table.verticalHeaderItem( row ).text()

    def setNameLayer(self, row, name):
        item = self.table.verticalHeaderItem( row )
        item.setText( name  )
        self.table.setVerticalHeaderItem( row, item )

    def getNameFields(self, row):
        return {
            'fieldSource': self.table.verticalHeaderItem( row ).data( Qt.UserRole )['fieldSource'],
            'fieldDate': self.table.verticalHeaderItem( row ).data( Qt.UserRole )['fieldDate'],
        }

    def setFontItem(self, item, isProcessing=False):
        font = item.font()
        font.setItalic( isProcessing )
        font.setBold( isProcessing )
        item.setFont( font )

    def getIconLabel(self, layer):
        if layer.selectedFeatureCount() > 0:
            icon = 'check_yellow.svg'
            label = QCoreApplication.translate('CatalogOTF', '{} Selected')
            label = label.format( layer.selectedFeatureCount() )
        else:
            icon = 'check_green.svg'
            label = QCoreApplication.translate('CatalogOTF', '{} Total')
            label = label.format( layer.featureCount() )
        return icon, label

    def setLayerItem(self, layer, row):
        icon, label = self.getIconLabel( layer )
        icon = QIcon( joinPath( dirname(__file__), icon ) )
        item = self.table.verticalHeaderItem( row )
        self.setFontItem( item )
        item.setIcon( icon )
        #
        item = self.table.item( row, 0 ) # idCol = 0
        self.setFontItem( item )
        item.setText( label )
        self.table.resizeColumnsToContents()

    def setLayerItemProcessing(self, layer, row, labelStatus, totalInView=None):
        item = self.table.verticalHeaderItem( row )
        self.setFontItem( item, True )
        if totalInView is None:
            _icon, label = self.getIconLabel( layer )
            label = "{} - {}".format( label, labelStatus )
        else:
            label = QCoreApplication.translate('CatalogOTF', '{} in View - Running...')
            label = label.format( totalInView )
        item = self.table.item( row, 0 ) # idCol = 0
        self.setFontItem( item, True )
        item.setText( label )
        self.table.resizeColumnsToContents()

    def insertLayer(self, layer, fieldSource, fieldDate):
        row = self.table.rowCount()
        self.table.insertRow( row )
        # Header Column
        self.table.setHorizontalHeaderLabels( [ self.headerTable.format( self.table.rowCount() ) ] )
        # Header Line
        item = QTableWidgetItem( layer.name() )
        item.setFlags( Qt.ItemIsEnabled )
        data = { 'layerId': layer.id(), 'fieldSource': fieldSource, 'fieldDate': fieldDate }
        item.setData( Qt.UserRole, data )
        label = self.tooltipRow.format( fieldSource, fieldDate )
        item.setData( Qt.ToolTipRole, label )
        self.table.setVerticalHeaderItem( row, item )
        # Total
        item = QTableWidgetItem()
        item.setFlags( Qt.ItemIsSelectable | Qt.ItemIsEnabled )
        self.table.setItem( row, 0, item ) # idCol = 0
        # Layer(name and total)
        self.setLayerItem( layer, row )

    def removeLayers(self, rows):
        rows.sort(reverse=True)
        for row in rows:
            self.table.removeRow( row  )
        self.table.setHorizontalHeaderLabels( [ self.headerTable.format( self.table.rowCount() ) ] )

    def enableProcessing(self, isProcessing):
        label = self.labelCancel if isProcessing else self.labelRun
        total = len( self.table.selectedItems() )
        label = label.format( total )
        self.btnRunCancel.setText( label )
        self.btnFind.setEnabled( not isProcessing )
        self.table.setEnabled( not isProcessing )
        self.isProcessing = isProcessing

    @pyqtSlot()
    def selectionChangedTable(self):
        total = len( self.table.selectedItems() )
        if self.isProcessing:
            label = self.labelCancel.format( total )
        else:
            label = self.labelRun.format( total )
            self.btnRunCancel.setEnabled( total > 0 )
        self.btnRunCancel.setText( label )

    @pyqtSlot( bool )
    def run(self, checked):
        if not self.isProcessing:
            items = self.table.selectedItems()
            if len( items) == 0:
                return
            f = lambda item: self.table.verticalHeaderItem( item.row() ).data( Qt.UserRole )['layerId']
            layerIds = [ f( item ) for item in items ]
        else:
           layerIds = [] 
        self.runCatalog.emit( self.isProcessing, layerIds  )

    @pyqtSlot( bool )
    def find(self, checked):
        self.findCatalog.emit()

class ProcessCatalogOTF(QObject):
    formatQDate = 'yyyy-MM-dd'
    namePlugin = 'Catalog_OTF'
    msgBar = QgsUtils.iface.messageBar()
    formatError = QCoreApplication.translate('CatalogOTF', "Error '{}'" )

    @staticmethod
    def isUrl(value):
        # Start 'http://' or 'https://' and finished '.xml'
        isUrl = value.find('http://') == 0 or value.find('https://') == 0
        return isUrl and value[-4:] == '.xml'

    @staticmethod
    def existsUrl(url, getResponse=False):
        timeout = 8
        isOk = True
        try:
            response = urllib.request.urlopen( url, timeout=timeout )
        except ( urllib.error.HTTPError, urllib.error.URLError ):
            isOk, response = False, None
        except ( ConnectionResetError, urllib.request.socket.timeout ):
            isOk, response = False, None
        return isOk if not getResponse else ( isOk, response )

    def __init__(self, widget ):
        super().__init__()
        self.widget = widget
        self.project = QgsProject.instance()
        self.taskManager = QgsApplication.taskManager()
        self.taskLayerTreeGroup = {} # Set in 'run()' layer_catalog_id' : { TypeLayerTreeGroup.CATALOG: , TypeLayerTreeGroup.DATE: }
        self.ltgRoot = self.project.layerTreeRoot()
        #
        self.nameCatalog = 'Catalogs OTF'
        self.menuLayer = MenuTMSXml()
        self.totalRunning = 0
        self.totalFinish = 0
        #
        self.widget.runCatalog.connect( self.run )
        self.widget.findCatalog.connect( self.find )
        self.project.layerWillBeRemoved.connect( self.removeLayer )
        self.project.layerWasAdded.connect( self.addedLayer )
        self.taskManager.statusChanged.connect( self.statusProcessing )

    @pyqtSlot(str, str)
    def addDateTreeGroupTask(self, layerId, nameDate ):
        ltg = self.taskLayerTreeGroup[ layerId ][ TypeLayerTreeGroup.CATALOG ]
        self.taskLayerTreeGroup[ layerId ][ TypeLayerTreeGroup.DATE ] = ltg.addGroup( nameDate )

    @pyqtSlot(str, TypeLayerTreeGroup, dict)
    def addRasterTreeGroupTask(self, layerId, typeGroup, image):
        layer = QgsRasterLayer( image['filePath'], image['baseName'] )
        if layer is None or not layer.isValid():
            task = self.sender()
            msg = self.formatError.format( image['source'] )
            msg = "{}: {}".format( task.layer.name(), msg )
            task.countError += 1
            self.messageLog( msg )
            return

        if not image['filePath'][-4:] == 'xml':
            RasterTransparency.setTransparency( layer )
        if 'wktBBox' in image:
            layer.setCustomProperty('wktBBox', image['wktBBox'] )
            #self.menuLayer.setLayer( layer )
        self.project.addMapLayer( layer, addToLegend=False )
        ltg = self.taskLayerTreeGroup[ layerId ][ typeGroup ]
        ltl = ltg.addLayer( layer )
        ltl.setExpanded( False )

    @pyqtSlot(str, TypeLayerTreeGroup, TypeSufixLayerTreeGroup)
    def setNameGroupTask(self, layerId, typeGroup, typeSufix):
        ltg = self.taskLayerTreeGroup[ layerId ][ typeGroup ]
        name, total = ltg.name(), len( ltg.children() )
        if typeSufix == TypeSufixLayerTreeGroup.CANCELLED:
            msg = QCoreApplication.translate('CatalogOTF', '{} - Cancelled')
            name = msg.format( name )
        else:
            msg = QCoreApplication.translate('CatalogOTF', '{} ({} Total)')
            name = msg.format( name, total )
        ltg.setName( name )
        ltg.setExpanded( False )

    @pyqtSlot('long', int)
    def statusProcessing(self, taskid, status):
        def getLabelStatus():
            if status in ( QgsTask.Queued, QgsTask.OnHold ):
                label = QCoreApplication.translate('CatalogOTF', 'Waiting...')
            elif status == QgsTask.Running:
                label = QCoreApplication.translate('CatalogOTF', 'Running...')
            elif status == QgsTask.Complete:
                label = QCoreApplication.translate('CatalogOTF', 'Finished.')
                self.totalFinish += 1
            elif status == QgsTask.Terminated:
                label = QCoreApplication.translate('CatalogOTF', 'Canceled')
                self.totalFinish += 1
            else:
                label = 'Not status'
            return label

        def setLabelProcessing(label):
            rowTable = layerIdsTable[ task.layerId ]
            self.widget.setLayerItemProcessing( task.layer, rowTable, label)

        def setLabelFinishAll():
            for layerId in layerIdsTable.keys():
                layer = self.ltgRoot.findLayer( layerId ).layer()
                rowTable = layerIdsTable[ layerId ]
                self.widget.setLayerItem( layer, rowTable )

        task = self.taskManager.task( taskid )
        if not type(task) is TaskCatalogOTF:
            return
        if status == QgsTask.Complete and task.countError > 0:
            msg = QCoreApplication.translate('CatalogOTF', '{} - Total of errors: {}')
            msg = msg.format( task.layer.name(), task.countError )
            self.msgBar.pushMessage( self.namePlugin , msg, Qgis.Warning, 4 )
        label = getLabelStatus() # Count totalFinish
        layerIdsTable = self.widget.getLayerIds(True)
        if self.totalFinish == self.totalRunning:
            setLabelFinishAll()
            self.widget.enableProcessing(False)
        else:
            setLabelProcessing( label )

    @pyqtSlot(int)
    def statusFoundFeatures(self, totalInView):
        task = self.sender()
        layerIdsTable = self.widget.getLayerIds(True)
        rowTable = layerIdsTable[ task.layerId ]
        label = QCoreApplication.translate('CatalogOTF', 'Running...')
        self.widget.setLayerItemProcessing( task.layer, rowTable, label, totalInView )

    @pyqtSlot(str, int)
    def messageStatus(self, message, level ):
        self.msgBar.pushMessage( self.namePlugin , message, level, 4 )

    @pyqtSlot(str)
    def messageLog(self, message):
        QgsMessageLog.logMessage( message, self.namePlugin, Qgis.Warning )

    @pyqtSlot(bool, list)
    def run(self, isProcessing, layerIds):
        def _run():
            def getRootCatalog():
                ltgRootCatalog = self.ltgRoot.findGroup( self.nameCatalog )
                if ltgRootCatalog is None:
                    ltgRootCatalog = self.ltgRoot.addGroup( self.nameCatalog )
                else:
                    ltgRootCatalog.removeAllChildren()
                return ltgRootCatalog

            def setLayerTreeGroupCatalog(layerId, rowTable):
                ltgCatalog = ltgRootCatalog.addGroup( self.widget.getNameLayer( rowTable) )
                ltgCatalog.setExpanded( False )
                ltgCatalog.setItemVisibilityChecked( False )
                self.taskLayerTreeGroup[ layerId ] = { TypeLayerTreeGroup.CATALOG: ltgCatalog, TypeLayerTreeGroup.DATE: None }

            self.taskLayerTreeGroup.clear()
            self.widget.enableProcessing( True ) # Set value isProcessing in self.widget
            ltgRootCatalog = getRootCatalog()
            layerIdsTable = self.widget.getLayerIds(True)
            self.totalFinish, self.totalRunning = 0, len( layerIds )
            for layerId in layerIds:
                rowTable = layerIdsTable[ layerId ]
                setLayerTreeGroupCatalog( layerId, rowTable )
                nameFields = self.widget.getNameFields( rowTable )
                data = {
                    'layer':       self.ltgRoot.findLayer( layerId ).layer(),
                    'fieldSource': nameFields['fieldSource'],
                    'fieldDate':   nameFields['fieldDate'],
                    'addDateTreeGroupTask':   self.addDateTreeGroupTask,
                    'addRasterTreeGroupTask': self.addRasterTreeGroupTask,
                    'setNameGroupTask':       self.setNameGroupTask,
                }
                task = TaskCatalogOTF( data )
                task.messageLog.connect( self.messageLog )
                task.messageStatus.connect( self.messageStatus )
                task.foundFeatures.connect( self.statusFoundFeatures )
                self.taskManager.addTask( task )

        def _stop():
            msg = QCoreApplication.translate('CatalogOTF', 'Cancelled by user')
            self.msgBar.clearWidgets()
            self.msgBar.pushMessage( self.namePlugin , msg, Qgis.Warning, 4 )
            self.taskManager.cancelAll() # Set value isProcessing in 'statusProcessing'(all finished)

        _stop() if isProcessing else _run()

    @pyqtSlot()
    def find(self):
        def overrideCursor():
            cursor = QApplication.overrideCursor()
            if cursor is None or cursor == 0:
                QApplication.setOverrideCursor( QCursor( Qt.WaitCursor ) )
            elif cursor.shape() != Qt.WaitCursor:
                QApplication.setOverrideCursor( QCursor( Qt.WaitCursor ) )

        def getNameFieldsCatalog(Layer):
            def getFirstFeature():
                f = QgsFeature()
                #
                it = layer.getFeatures() # First FID can be 0 or 1 depend of provider type
                isOk = it.nextFeature( f )
                it.close()
                #
                if not isOk or not f.isValid():
                    del f
                    return { 'isOk': False }
                else:
                    return { 'isOk': True, 'feature': f }

            def existsSource(value):
                if self.isUrl( value ):
                    return self.existsUrl( value )
                fileInfo = QFileInfo( value )
                return fileInfo.isFile()

            def existsDate(value):
                date = value if type( value ) is QDate else QDate.fromString( value, self.formatQDate )
                return True if date.isValid() else False

            fieldSource, fieldDate = None, None
            vreturn = getFirstFeature()
            if not vreturn['isOk']:
                return { 'fieldSource': fieldSource, 'fieldDate': fieldDate }

            feat = vreturn['feature']
            for item in layer.fields().toList():
                nameField = item.name()
                value = feat.attribute( nameField )
                if value is None or ( type(value) == QVariant and value.isNull() ):
                    continue
                if item.type() == QVariant.String:
                    if fieldSource is None and existsSource( value ):
                        fieldSource = nameField
                    elif fieldDate is None and existsDate( value ):
                        fieldDate = nameField
                elif item.type() == QVariant.Date:
                    if fieldDate is None and existsDate( value ):
                        fieldDate = nameField
            #
            return { 'fieldSource': fieldSource, 'fieldDate': fieldDate }

        overrideCursor()
        total = 0
        layerIds = self.widget.getLayerIds().keys()
        f = lambda layer: \
            not layer.id() in layerIds and \
            layer.type() == QgsMapLayer.VectorLayer and \
            layer.geometryType() == QgsWkbTypes.PolygonGeometry
        layers = [ ltl.layer() for ltl in self.ltgRoot.findLayers() ]
        for layer in filter( f, layers ):
            r = getNameFieldsCatalog( layer )
            if r['fieldSource'] is None:
                continue
            self.widget.insertLayer( layer, r['fieldSource'], r['fieldDate'] )
            layer.selectionChanged.connect( self.selectionChangedLayer )
            self.ltgRoot.findLayer( layer.id() ).nameChanged.connect( self.nameChanged )
            total += 1

        QApplication.restoreOverrideCursor()
        self.msgBar.clearWidgets()
        if total > 0:
            msg = QCoreApplication.translate('CatalogOTF', 'Added {} layer(s)')
            msg = msg.format( total )
            self.msgBar.pushMessage( self.namePlugin , msg, Qgis.Info, 4 )
        else:
            msg = QCoreApplication.translate('CatalogOTF', 'Not found a new catalog layer')
            self.msgBar.pushMessage( self.namePlugin , msg, Qgis.Warning, 4 )

    @pyqtSlot('QString')
    def removeLayer(self, layerId):
        layerIdsTable = self.widget.getLayerIds()
        if not layerId in layerIdsTable.keys():
            return
        row = layerIdsTable[ layerId ]
        self.widget.removeLayers( [ row ] )

    @pyqtSlot(QgsMapLayer)
    def addedLayer(self, layer):
        wktBBox = layer.customProperty('wktBBox', None)
        if not wktBBox is None:
            self.menuLayer.setLayer( layer )

    @pyqtSlot('QgsFeatureIds', 'QgsFeatureIds', bool)
    def selectionChangedLayer(self, selected, deselected, clearAndSelect):
        if self.widget.isProcessing:
            return
        layer = self.sender()
        layerId = layer.id()
        layerIdsTable = self.widget.getLayerIds()
        if layerId in layerIdsTable.keys():
            self.widget.setLayerItem( layer, layerIdsTable[ layerId ] )
   
    @pyqtSlot('QgsLayerTreeNode*', 'QString')
    def nameChanged(self, node, name):
        # Change name layer in Table
        if self.widget.isProcessing:
            return
        if node is None or not node.nodeType() == QgsLayerTreeNode.NodeLayer:
            return
        layerId = node.layer().id()
        if layerId in self.widget.getLayerIds().keys():
            layerIdsTable = self.widget.getLayerIds()
            nameTable = self.widget.getNameLayer( layerIdsTable[ layerId ] )
            if name != nameTable:
                self.widget.setNameLayer( layerIdsTable[ layerId ], name )

class TaskCatalogOTF(QgsTask):
    messageLog         = pyqtSignal(str)
    messageStatus      = pyqtSignal(str, int)
    foundFeatures      = pyqtSignal(int)
    addDateTreeGroup   = pyqtSignal(str, str)
    addRasterTreeGroup = pyqtSignal(str, TypeLayerTreeGroup, dict)
    setNameGroup       = pyqtSignal(str, TypeLayerTreeGroup, TypeSufixLayerTreeGroup)

    def __init__(self, data ):
         super().__init__('CatalogOTF', QgsTask.CanCancel )
         self.project = QgsProject.instance()
         self.layer = data['layer']
         self.layerId = self.layer.id()
         self.fieldSource = data['fieldSource']
         self.fieldDate = data['fieldDate']
         self.canvas = QgsUtils.iface.mapCanvas()
         self.countError = 0
         self.totalFeatures = 0
         self.setDependentLayers( [ self.layer] )

         self.timeWait = 2
         self.addDateTreeGroup.connect( data['addDateTreeGroupTask'] )
         self.addRasterTreeGroup.connect( data['addRasterTreeGroupTask'] )
         self.setNameGroup.connect( data['setNameGroupTask'] )

    def emitStatus(self, value, level):
        msg = "{}: {}".format( self.layer.name(), value )
        self.messageStatus.emit( msg, level )
    
    def emitError(self, value):
        msg = ProcessCatalogOTF.formatError.format( value )
        msg = "{}: {}".format( self.layer.name(), msg )
        self.countError += 1
        self.messageLog.emit( msg )

    def run(self):
        def getImagesByCanvas():
            def getFidsSpatialIndexIntersect():
                isSelected = self.layer.selectedFeatureCount() > 0
                rectLayer = self.layer.extent() if not isSelected else self.layer.boundingBoxOfSelected()
                crsLayer = self.layer.crs()

                crsCanvas = self.canvas.mapSettings().destinationCrs()
                ct = QgsCoordinateTransform( crsCanvas, crsLayer, self.project )
                rectCanvas = self.canvas.extent() if crsCanvas == crsLayer else ct.transform( self.canvas.extent() )

                if not rectLayer.intersects( rectCanvas ):
                    return { 'fids': None }

                fr = QgsFeatureRequest()
                if isSelected:
                    fr.setFilterFids( self.layer.selectedFeatureIds() )
                index = QgsSpatialIndex( self.layer.getFeatures( fr ) )
                fids = index.intersects( rectCanvas )
                del fr
                del index
                return { 'fids': fids, 'rectCanvas': rectCanvas }

            def getImagesIntersect(fids, rectCanvas):
                nfS, nfD = self.fieldSource, self.fieldDate
                
                if not self.fieldDate is None:
                    getSourceDate = lambda feat: { 'source': feat[ nfS ], 'date': feat[ nfD ] }
                    if self.layer.fields().field( nfD ).type() == QVariant.Date:
                        getSourceDate = lambda feat: { 'source': feat[ nfS ], 'date': feat[ nfD ].toString( ProcessCatalogOTF.formatQDate ) }
                getSource = lambda feat: { 'source': feat[ nfS ] }
                
                fr = QgsFeatureRequest()
                fr.setFilterFids ( fids )
                it = self.layer.getFeatures( fr ) 
                feat = QgsFeature()
                getAttributes = getSourceDate if not nfD is None else getSource
                images = []
                while it.nextFeature( feat ):
                    if self.isCanceled():
                        return { 'status': TypeStatusProcessing.CANCELLED }
                    if feat.geometry().intersects( rectCanvas ):
                        images.append( getAttributes( feat ) )

                return { 'status': TypeStatusProcessing.COMPLETE, 'images': images }

            r = getFidsSpatialIndexIntersect()
            fids = r['fids']
            if fids is None:
                return { 'status': TypeStatusProcessing.COMPLETE, 'images': [] }
            rectCanvas = r['rectCanvas']
            r = getImagesIntersect( fids, rectCanvas )
            del fids[:]
            return r

        def setSortReverseImages(images):
            """
            images: List of { 'source' } or { 'source', 'date' }

            Return: TypeStatusProcessing.COMPLETE or 
                    TypeStatusProcessing.CANCELLED

            Process: Sorted(reverse) the 'images' by date(if have) or source
                     and set images with:  { 'isOk', 'source', 'wktBBox' }
                'isOk': True if source exist. For Http/XML check URL and the '<ServerUrl>'
                'source': If Http/XML is OK, change for '/vsicurl/[source]'
                'wktBBox': It will add if have '<TargetWindow>' in Http/XML
            """
            def setImage(image):
                def getValueTag(nodeRoot, tag):
                    nodes = nodeRoot.toElement().elementsByTagName( tag )
                    if nodes.isEmpty():
                        return None
                    node = nodes.item(0).firstChild()
                    return node.nodeValue()

                def isValidXml(doc):
                    def hasValueAttribute(node, name, value):
                        atts = node.attributes()
                        if atts.isEmpty() or not atts.contains(name):
                            return False
                        v = atts.namedItem(name).firstChild().nodeValue()
                        return v.upper() == value.upper()

                    def existsServerUrl(url_tms):
                        idx = url_tms.index('/${z}/${x}/${y}')
                        url = url_tms[:idx]
                        return ProcessCatalogOTF.existsUrl( url )

                    nodesService = doc.elementsByTagName('Service')
                    if nodesService.isEmpty():
                        return False

                    nodeService = nodesService.item(0)
                    if not hasValueAttribute( nodeService, 'name', 'TMS' ):
                        return False
                    # Check url
                    url_tms = getValueTag( nodeService, 'ServerUrl' )
                    if url_tms is None:
                        return False

                    return existsServerUrl(url_tms)

                def getWktBBox(doc):
                    nodesTargetWindow = doc.elementsByTagName('TargetWindow')
                    if nodesTargetWindow.isEmpty():
                        return None

                    nodeTargetWindow = nodesTargetWindow.item(0)
                    coords = []
                    for tag in ( 'UpperLeftX', 'UpperLeftY', 'LowerRightX', 'LowerRightY' ):
                        v = getValueTag( nodeTargetWindow, tag )
                        if v is None:
                            return None
                        coords.append( float( v ) )
                    [ ulX, ulY, lrX, lrY ] = coords
                    #
                    wkt = f"POLYGON(({ulX} {ulY}, {lrX} {ulY}, {lrX} {lrY}, {ulX} {lrY}, {ulX} {ulY}))"
                    return wkt
                
                if not ProcessCatalogOTF.isUrl( image['source'] ):
                    fileInfo = QFileInfo( image['source'] )
                    isOk = fileInfo.isFile()
                    image['isOk'] = isOk
                    return
                # Http/XML
                isOk, response = ProcessCatalogOTF.existsUrl( image['source'], True )
                if not isOk:
                    image['isOk'] = False
                    return
                #
                xml = response.read()
                response.close()
                doc = QDomDocument()
                doc.setContent( xml.decode('utf-8') )
                if not isValidXml( doc ):
                    image['isOk'] = False
                    return

                image['isOk'] = True
                image['source'] = f"/vsicurl/{image['source']}"
                wkt = getWktBBox( doc )
                if not wkt is None:
                    image['wktBBox'] = wkt

            # Sorted images
            key = 'date' if not self.fieldDate is None else 'source'
            images.sort( key=lambda item: item[ key ], reverse=True )
            for image in images:
                if self.isCanceled():
                    return TypeStatusProcessing.CANCELLED
                setImage( image )
            
            return TypeStatusProcessing.COMPLETE

        def addImages(images, existsDate):
            """
            images: List of 
            """
            def addLayerFunction(images, functionAdd):
                info = QFileInfo()
                for image in images:
                    if self.isCanceled():
                        return { 'status': TypeStatusProcessing.CANCELLED }
                    if not image['isOk']:
                        self.emitError( image['source'] )
                        continue
                    info.setFile( image['source'] )
                    filePath = info.filePath()
                    baseName = info.completeBaseName()
                    image['filePath'] = filePath
                    image['baseName'] = baseName
                    del image['source']
                    del image['isOk']
                    functionAdd( image )
                return { 'status': TypeStatusProcessing.COMPLETE }

            def addRastersLegend(images):
                def add( image):
                    self.addRasterTreeGroup.emit( self.layerId, TypeLayerTreeGroup.CATALOG, image )

                return addLayerFunction( images, add )

            def addRastersLegendDate(images):
                def getZeroDateLayers():
                    dates = [ img['date'] for img in images ]
                    dates = set( dates )
                    datesLayers = {}
                    for date in dates:
                        if self.isCanceled():
                            return { 'status': TypeStatusProcessing.CANCELLED }
                        datesLayers[ date ] = []
                    return { 'status': TypeStatusProcessing.COMPLETE, 'datesLayers': datesLayers }

                r = getZeroDateLayers()
                if r['status'] == TypeStatusProcessing.CANCELLED:
                    return r
                datesLayers = r['datesLayers']
                r = addLayerFunction( images, lambda image: datesLayers[ image['date'] ].append( image ) )
                if r['status'] == TypeStatusProcessing.CANCELLED:
                    del datesLayers[:]
                    return r
                if self.countError == self.totalFeatures:
                    return { 'status': TypeStatusProcessing.COMPLETE }
                for date in sorted( datesLayers.keys(), reverse=True ):
                    if self.isCanceled():
                        return { 'status': TypeStatusProcessing.CANCELLED }
                    self.addDateTreeGroup.emit( self.layerId, date )
                    self.waitForFinished( self.timeWait )
                    for image in datesLayers[ date ]:
                        if r['status'] == TypeStatusProcessing.CANCELLED:
                            return { 'status': TypeStatusProcessing.CANCELLED }
                        self.addRasterTreeGroup.emit( self.layerId, TypeLayerTreeGroup.DATE, image )
                    self.setNameGroup.emit(  self.layerId, TypeLayerTreeGroup.DATE, TypeSufixLayerTreeGroup.TOTAL )
                return { 'status': TypeStatusProcessing.COMPLETE }

            addFunc = addRastersLegendDate if existsDate else addRastersLegend
            r = addFunc( images )
            if r['status'] == TypeStatusProcessing.CANCELLED:
                self.setNameGroup.emit( self.layerId, TypeLayerTreeGroup.CATALOG, TypeSufixLayerTreeGroup.CANCELLED )
            else:
                self.setNameGroup.emit( self.layerId, TypeLayerTreeGroup.CATALOG, TypeSufixLayerTreeGroup.TOTAL )
            return r
        
        self.countError = 0
        r = getImagesByCanvas()
        if r['status'] == TypeStatusProcessing.CANCELLED:
            self.setNameGroup.emit( self.layerId, TypeLayerTreeGroup.CATALOG, TypeSufixLayerTreeGroup.CANCELLED )
            return False
        images = r['images']
        if len(images ) == 0:
            self.setNameGroup.emit( self.layerId, TypeLayerTreeGroup.CATALOG, TypeSufixLayerTreeGroup.TOTAL )
            return True
        status = setSortReverseImages( images )
        if status == TypeStatusProcessing.CANCELLED:
            self.setNameGroup.emit( self.layerId, TypeLayerTreeGroup.CATALOG, TypeSufixLayerTreeGroup.CANCELLED )
            return False
        self.totalFeatures = len( images )
        self.foundFeatures.emit( self.totalFeatures )
        r = addImages( images, not self.fieldDate is None )
        return True if r['status'] == TypeStatusProcessing.COMPLETE else False
