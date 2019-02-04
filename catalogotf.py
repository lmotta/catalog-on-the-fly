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

from qgis.PyQt.QtCore import (
    QObject, Qt, QCoreApplication,
    QVariant, QDate,
    QFileInfo, QDir,
    pyqtSlot, pyqtSignal,
)

from qgis.PyQt.QtGui import QIcon, QFont, QCursor

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
    QgsLayerTreeGroup, QgsLayerTreeNode,
    QgsMapLayer, QgsRasterLayer, QgsRasterTransparency, QgsFeature,
    QgsFeatureRequest, QgsSpatialIndex,
    QgsCoordinateTransform,
)

from qgis.gui import QgsMessageBar

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
        self.process = ProcessCatalogOTF( self, iface )

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
            icon, label = self.getIconLabel( layer )
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
    TEMP_DIR = '/tmp/catalogotf_gdal_wms'
    formatQDate = 'yyyy-MM-dd'

    @staticmethod
    def isUrl(value):
        # Start 'http://' or 'https://' and finished '.xml'
        isUrl = value.find('http://') == 0 or value.find('https://') == 0
        return isUrl and value[-4:] == '.xml'

    @staticmethod
    def existsUrl(url, getResponse=False):
        isOk = True
        try:
            response = urllib.request.urlopen( url )
        except urllib.error.HTTPError:
            isOk, response = False, None
        except urllib.error.URLError:
            isOk, response = False, None
        return isOk if not getResponse else ( isOk, response )

    def __init__(self, widget, iface):
        super().__init__()
        self.widget = widget
        self.msgBar = iface.messageBar()
        self.namePlugin = 'Catalog OTF'
        self.project = QgsProject.instance()
        self.taskManager = QgsApplication.taskManager()
        self.ltgRoot = self.project.layerTreeRoot()
        #
        self.nameCatalog = 'Catalogs OTF'
        TaskCatalogOTF.iface = iface
        self.totalRunning = 0
        self.totalFinish = 0
        self.msgUseDir_gdal_wms = None
        #
        self.widget.runCatalog.connect( self.run )
        self.widget.findCatalog.connect( self.find )
        self.project.layerWillBeRemoved.connect( self.removeLayer )
        self.taskManager.statusChanged.connect( self.statusProcessing )

    @pyqtSlot(str)
    def addTreeGroupTask(self, name ):
        task = self.sender()
        if not isinstance( task.ltgSlot, QgsLayerTreeGroup ):
            task.checkInput = False
            return
        task.checkInput = True
        task.resultSlot = task.ltgSlot.addGroup( name )

    @pyqtSlot()
    def addLayerNoLegendTask(self):
        task = self.sender()
        if not isinstance( task.layerSlot, QgsRasterLayer ):
            task.checkInput = False
            return True
        task.checkInput = True
        task.resultSlot = self.project.addMapLayer( task.layerSlot, addToLegend=False )

    @pyqtSlot()
    def addRasterTreeGroupTask(self):
        task = self.sender()
        if not isinstance( task.ltgSlot, QgsLayerTreeGroup ) or not isinstance( task.layerSlot, QgsRasterLayer ):
            task.checkInput = False
            return
        task.checkInput = True
        ltl = task.ltgSlot.addLayer( task.layerSlot )
        if ltl is None:
            task.resultSlot = False
        else:
            ltl.setExpanded( False )
            task.resultSlot = True

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
            rowTable = layerIdsTable[ task.layer.id() ]
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
        rowTable = layerIdsTable[ task.layer.id() ]
        label = QCoreApplication.translate('CatalogOTF', 'Running...')
        self.widget.setLayerItemProcessing( task.layer, rowTable, label, totalInView )

    @pyqtSlot(str, int)
    def messageStatus(self, message, level ):
        self.msgBar.pushMessage( self.namePlugin , message, level, 4 )

    @pyqtSlot(str, str)
    def messageLog(self, message, tag):
        QgsMessageLog.logMessage( message, tag, Qgis.Warning )

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

            self.widget.enableProcessing( True ) # Set value isProcessing in self.widget
            ltgRootCatalog = getRootCatalog()
            layerIdsTable = self.widget.getLayerIds(True)
            self.totalFinish, self.totalRunning = 0, len( layerIds )
            for layerId in layerIds:
                rowTable = layerIdsTable[ layerId ]
                nameFields = self.widget.getNameFields( rowTable )
                data = {
                    'layer':              self.ltgRoot.findLayer( layerId ).layer(),
                    'ltgCatalog':         ltgRootCatalog.addGroup( self.widget.getNameLayer( rowTable) ),
                    'fieldSource':        nameFields['fieldSource'],
                    'fieldDate':          nameFields['fieldDate'],
                    'addTreeGroup':       self.addTreeGroupTask,
                    'addLayerNoLegend':  self.addLayerNoLegendTask,
                    'addRasterTreeGroup': self.addRasterTreeGroupTask,
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
            self.taskManager.cancelAll() # # Set value isProcessing in 'statusProcessing'(all finished)

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
                    isOk = self.existsUrl( value )
                    if isOk:
                        if not QDir( self.TEMP_DIR ).exists():
                            QDir().mkdir( self.TEMP_DIR )
                            msg = QCoreApplication.translate('CatalogOTF', 'Created diretory {}')
                            self.msgUseDir_gdal_wms = msg.format( self.TEMP_DIR )
                        else:
                            msg = QCoreApplication.translate('CatalogOTF', 'Diretory {} for virtual raster(XML)' )
                            self.msgUseDir_gdal_wms = msg.format( self.TEMP_DIR )

                    return isOk

                # File
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
        self.msgUseDir_gdal_wms = None
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
            if not self.msgUseDir_gdal_wms is None:
                msg = "{}. {}".format( msg, self.msgUseDir_gdal_wms )
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
    iface = None
    messageLog         = pyqtSignal(str, str)
    messageStatus      = pyqtSignal(str, int)
    foundFeatures      = pyqtSignal(int)
    addTreeGroup       = pyqtSignal(str)
    addLayerNoLegend   = pyqtSignal()
    addRasterTreeGroup = pyqtSignal()

    def __init__(self, data ):
         super().__init__('CatalogOTF', QgsTask.CanCancel )
         self.project = QgsProject.instance()
         self.layer = data['layer']
         self.ltgCatalog = data['ltgCatalog']
         self.fieldSource = data['fieldSource']
         self.fieldDate = data['fieldDate']
         self.canvas = self.iface.mapCanvas()
         self.formatError = QCoreApplication.translate('CatalogOTF', "Error '{}'" )
         self.countError = 0
         self.totalFeatures = 0
         self.setDependentLayers( [ self.layer] )

         self.timeWait = {
             'addTreeGroup': 2,
             'addLayerNoLegend': 2,
             'addRasterTreeGroup': 2
         }
         self.layerSlot, self.ltgSlot = None, None
         self.resultSlot, self.checkInput = None, None
         self.addTreeGroup.connect( data['addTreeGroup'] )
         self.addLayerNoLegend.connect( data['addLayerNoLegend'] )
         self.addRasterTreeGroup.connect( data['addRasterTreeGroup'] )

    def emitStatus(self, value, level):
        msg = "{}: {}".format( self.layer.name(), value )
        self.messageStatus.emit( msg, level )
    
    def emitError(self, value):
        msg = self.formatError.format( value )
        msg = "{}: {}".format( self.layer.name(), msg )
        self.countError += 1
        self.messageLog.emit( msg, self.description() )

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

            def getImagesIntersect(fids, rectCarootnvas):
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
                        return { 'isOk': False }
                    if feat.geometry().intersects( rectCanvas ):
                        images.append( getAttributes( feat ) )

                return { 'isOk': True, 'images': images }

            r = getFidsSpatialIndexIntersect()
            fids = r['fids']
            if fids is None:
                return { 'isOk': True, 'images': [] }
            rectCanvas = r['rectCanvas']
            r = getImagesIntersect( fids, rectCanvas )
            if not r['isOk']:
                return { 'isOk': False }
            images = r['images']
            del fids[:]

            return { 'isOk': True, 'images': images }

        def getInfoImages(images):
            def getFileInfo( image ):
                def prepareFileTMS( url_xml ):
                    def createLocalFile():
                        def existsServerUrl(docHtml):
                            def isValueAttribute(node, name, value):
                                atts = node.attributes()
                                if atts.isEmpty() or not atts.contains(name):
                                    return False
                                v = atts.namedItem(name).firstChild().nodeValue()
                                return v.upper() == value.upper()

                            nodesService = docHtml.elementsByTagName('Service')
                            if nodesService.isEmpty():
                                return False
                            nodeService = nodesService.item(0)
                            if not isValueAttribute( nodeService, 'name', 'TMS' ):
                                return False
                            # Check url
                            nodes = nodeService.toElement().elementsByTagName('ServerUrl')
                            if nodes.isEmpty():
                                return False
                            node = nodes.item(0).firstChild()
                            url_tms = node.nodeValue()
                            idx = url_tms.index('/${z}/${x}/${y}')
                            url = url_tms[:idx]
                            return ProcessCatalogOTF.existsUrl( url )

                        def populateLocalFile(docHtml):
                            def setPath(newPath):
                                nodesCache = docHtml.elementsByTagName('Cache')
                                if nodesCache.isEmpty():
                                    nodeGdalWms = docHtml.firstChild()
                                    nodeCache = docHtml.createElement('Cache')
                                    nodeGdalWms.appendChild( nodeCache )
                                else:
                                    nodeCache = nodesCache.item(0)
                                    nodesPath = nodeCache.toElement().elementsByTagName('Path')
                                    if not nodesPath.isEmpty():
                                        nodePath = nodesPath.item(0)
                                        nodeCache.removeChild( nodePath )
                                textNode = docHtml.createTextNode( newPath )
                                nodePath  = docHtml.createElement('Path')
                                nodePath.appendChild( textNode )                               
                                nodeCache.appendChild( nodePath )

                                return docHtml.toString()

                            newPath = "{}.tms".format( localName )
                            html = setPath( newPath  )
                            fw = open( localName, 'w' )
                            fw.write( html)
                            fw.close()

                        isOk, response = ProcessCatalogOTF.existsUrl( url_xml, True )
                        if not isOk:
                            return None
                        html = response.read()
                        response.close()
                        docHtml = QDomDocument()
                        docHtml.setContent( html.decode('utf-8') )
                        if not existsServerUrl( docHtml ):
                            return None
                        populateLocalFile( docHtml )
                        return QFileInfo( localName )

                    localName = "{}/{}".format( ProcessCatalogOTF.TEMP_DIR, basename( url_xml ) )
                    fileInfo = QFileInfo( localName )
                    if not fileInfo.exists():
                        fileInfo = createLocalFile() # If error return None
                    return fileInfo

                source = image['source']
                if ProcessCatalogOTF.isUrl( source ):
                    fi = prepareFileTMS( source ) # If error return None
                else:
                    fi = QFileInfo( source )
                    if not fi.isFile():
                        fi = None
                vReturn = { 'source': source, 'fileinfo': fi    }
                if 'date' in image.keys():
                    vReturn['date'] = image['date']

                return vReturn

            # Sorted images
            key = 'date' if not self.fieldDate is None else 'source'
            f_key = lambda item: item[ key ]    
            l_image_sorted = sorted( images, key=f_key, reverse=True )
            del images[:]
            # infoImages = { 'source', 'fileinfo', 'date' } or { 'source', fileinfo' }
            # - If error when read XML,  'fileinfo'  is None
            infoImages = []
            for image in l_image_sorted:
                if self.isCanceled():
                    del infoImages[:]
                    del l_image_sorted[:]
                    return { 'isOk': False }
                infoImages.append( getFileInfo( image ) )
            del l_image_sorted[:]
            return { 'isOk': True, 'infoImages': infoImages }

        def setNameGroup(layerTreeGroup, isCancel=False):
            name, total = layerTreeGroup.name(), len( layerTreeGroup.children() )
            if isCancel:
                vFormat = QCoreApplication.translate('CatalogOTF', '{} - Cancelled')
                name = vFormat.format( name )
            else:
                vFormat = QCoreApplication.translate('CatalogOTF', '{} ({} Total)')
                name = vFormat.format( name, total )
            layerTreeGroup.setName( name )

        def addImages(infoImages, existsDate):
            def addLayerFunction(infoImages, functionAdd):
                def setTransparence(layerRaster):
                    def getListTTVP():
                        t = QgsRasterTransparency.TransparentThreeValuePixel()
                        t.red = t.green = t.blue = 0.0
                        t.percentTransparent = 100.0
                        return [ t ]
                    
                    l_ttvp = getListTTVP()
                    fileName = layerRaster.source()
                    if not fileName[-4:] == 'xml':
                        layerRaster.renderer().rasterTransparency().setTransparentThreeValuePixelList( l_ttvp )

                for info in infoImages:
                    if self.isCanceled():
                        return False
                    if info['fileinfo'] is None:
                        self.emitError( info['source'] )
                        continue
                    layer = QgsRasterLayer( info['fileinfo'].filePath(), info['fileinfo'].baseName() )
                    if layer is None or not layer.isValid():
                        self.emitError( info['source'] )
                        layer = None
                        continue
                    setTransparence( layer )
                    layer.moveToThread( self.project.thread() )
                    self.checkInput, self.resultSlot = False, None
                    self.layerSlot = layer
                    self.addLayerNoLegend.emit()
                    self.waitForFinished( self.timeWait['addLayerNoLegend'] )
                    if not self.checkInput:
                        self.emitError("addLayerNoLegend (Input) - {}".format( info['source'] ) )
                        continue
                    if not isinstance( self.resultSlot, QgsRasterLayer ):
                        self.emitError("addLayerNoLegend (Output) - {}".format( info['source'] ) )
                        continue
                    layer = self.resultSlot
                    functionAdd( layer, info )
                return True

            def addRastersLegend(infoImages):
                def add( layer, info):
                    self.checkInput, self.resultSlot = False, False
                    self.ltgSlot, self.layerSlot = self.ltgCatalog, layer
                    self.addRasterTreeGroup.emit()
                    self.waitForFinished( self.timeWait['addRasterTreeGroup'] )
                    if not self.checkInput:
                        self.emitError("addRasterTreeGroup (Input) - {}".format( info['source'] ) )
                        return
                    if not self.resultSlot:
                        self.emitError("addRasterTreeGroup (Output) - {}".format( info['source'] ) )
                return addLayerFunction( infoImages, add )

            def addRastersLegendDate(infoImages):
                def getZeroDateLayers():
                    dates = [ info['date'] for info in infoImages ]
                    dates = set( dates )
                    datesLayers = {}
                    for date in dates:
                        if self.isCanceled():
                            return { 'isOk': False }
                        datesLayers[ date ] = []
                    return { 'isOk': True, 'datesLayers': datesLayers }

                r = getZeroDateLayers()
                if not r['isOk']:
                    return False
                datesLayers = r['datesLayers']
                isOk = addLayerFunction( infoImages, lambda layer, info: datesLayers[ info['date'] ].append( layer ) )
                if not isOk:
                    return False
                if self.countError == self.totalFeatures:
                    return True
                for date in sorted( datesLayers.keys(), reverse=True ):
                    if self.isCanceled():
                        return False
                    self.checkInput, self.resultSlot = False, None
                    self.ltgSlot = self.ltgCatalog
                    self.addTreeGroup.emit( date )
                    self.waitForFinished( self.timeWait['addTreeGroup'] )
                    if not self.checkInput:
                        msg = QCoreApplication.translate('CatalogOTF', 'addTreeGroup (Input) - Creating {} group')
                        self.emitError( msg.format( date ) )
                        continue
                    if not isinstance( self.resultSlot, QgsLayerTreeGroup ):
                        msg = QCoreApplication.translate('CatalogOTF', 'addTreeGroup (Output) - Creating {} group')
                        self.emitError( msg.format( date ) )
                        continue
                    ltgDate = self.resultSlot
                    for layer in datesLayers[ date ]:
                        if self.isCanceled():
                            return False
                        self.checkInput, self.resultSlot = False, None
                        self.ltgSlot, self.layerSlot = ltgDate, layer
                        self.addRasterTreeGroup.emit()
                        self.waitForFinished( self.timeWait['addRasterTreeGroup'] )
                        if not self.checkInput:
                            msg = QCoreApplication.translate('CatalogOTF', 'addRasterTreeGroup (Input) - Add {} layer')
                            self.emitError( msg.format( date ) )
                            continue
                        if not self.resultSlot:
                            msg = QCoreApplication.translate('CatalogOTF', 'addRasterTreeGroup (Output) - Add {} layer')
                            self.emitError( msg.format( layer.name() ) )
                            continue
                    ltgDate.setExpanded( False )
                    setNameGroup( ltgDate )
                return True

            addFunc = addRastersLegendDate if existsDate else addRastersLegend
            isOk = addFunc( infoImages )
            if not isOk:
                setNameGroup( self.ltgCatalog, True )
                return False
            else:
                setNameGroup( self.ltgCatalog )
            return True
        
        self.ltgCatalog.setExpanded( False )
        self.ltgCatalog.setItemVisibilityChecked( False )

        self.countError = 0
        r = getImagesByCanvas()
        if not r['isOk']:
            setNameGroup( self.ltgCatalog, True )
            return False
        if len( r['images']) == 0:
            setNameGroup( self.ltgCatalog )
            return True
        r = getInfoImages(r['images'] )
        if not r['isOk']:
            setNameGroup( self.ltgCatalog, True )
            return False
        infoImages = r['infoImages']
        self.totalFeatures = len( infoImages )
        self.foundFeatures.emit( self.totalFeatures )
        return addImages( infoImages, not self.fieldDate is None )
