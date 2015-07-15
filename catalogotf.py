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

import urllib2
from datetime import datetime
from os.path import ( basename, dirname, sep as sepPath, isdir, join as joinPath )
from os import makedirs

import json

from PyQt4.QtCore import ( 
     Qt, QObject, QThread, QFileInfo, QDir, QVariant, QCoreApplication,
     QPyNullVariant, pyqtSignal, pyqtSlot
)
from PyQt4.QtGui  import (
     QAction,
     QApplication,  QCursor, QColor, QIcon,
     QTableWidget, QTableWidgetItem,
     QPushButton, QGridLayout, QProgressBar, QDockWidget, QWidget
)
from PyQt4.QtXml import QDomDocument

import qgis
from qgis.gui import ( QgsMessageBar ) 
from qgis.core import (
  QgsProject, QGis,
  QgsMapLayerRegistry, QgsMapLayer,
  QgsFeature, QgsFeatureRequest, QgsGeometry, QgsRectangle,  QgsSpatialIndex,
  QgsCoordinateTransform,
  QgsRasterLayer, QgsRasterTransparency,
  QgsLayerTreeNode
)

from legendlayer import ( LegendRaster, LegendTMS )

NAME_PLUGIN = "Catalog On The Fly"

class WorkerPopulateGroup(QObject):

  # Static
  TEMP_DIR = "/tmp"
  
  # Signals 
  finished = pyqtSignal( bool )
  messageStatus = pyqtSignal( str )
  messageError = pyqtSignal( str )

  def __init__(self, addLegendLayer):
    
    super(WorkerPopulateGroup, self).__init__()
    self.killed = False
    #
    self.canvas = qgis.utils.iface.mapCanvas()
    self.addLegendLayer = addLegendLayer
    self.nameFieldSource = self.layer = self.ltgCatalog = None

  def setData(self, data):
    self.nameFieldSource = data[ 'nameFieldSource' ]
    self.nameFieldDate = data[ 'nameFieldDate' ]
    self.layer = data[ 'layer' ]
    self.ltgCatalog = data[ 'ltgCatalog' ]

  @pyqtSlot()
  def run(self):

    def getImagesByCanvas():
      def getSourceDate(feat):
        return { 'source': feat[ self.nameFieldSource ], 'date': feat[ self.nameFieldDate ] } 

      def getSource(feat):
        return { 'source': feat[ self.nameFieldSource ] }

      images = []

      selectedImage = self.layer.selectedFeatureCount() > 0
      rectLayer = self.layer.extent() if not selectedImage else self.layer.boundingBoxOfSelected()
      crsLayer = self.layer.crs()

      crsCanvas = self.canvas.mapSettings().destinationCrs()
      ct = QgsCoordinateTransform( crsCanvas, crsLayer )
      rectCanvas = self.canvas.extent() if crsCanvas == crsLayer else ct.transform( self.canvas.extent() )

      if not rectLayer.intersects( rectCanvas ):
        return [] 

      fr = QgsFeatureRequest()
      if selectedImage:
        fr.setFilterFids( self.layer.selectedFeaturesIds() )
      index = QgsSpatialIndex( self.layer.getFeatures( fr ) )
      fids = index.intersects( rectCanvas )

      del fr
      del index

      fr = QgsFeatureRequest()
      fr.setFilterFids ( fids )
      it = self.layer.getFeatures( fr ) 
      f = QgsFeature()
      getF = getSourceDate if not self.nameFieldDate  is None else  getSource
      while it.nextFeature( f ):
        if f.geometry().intersects( rectCanvas ):
          images.append( getF( f ) )

      del fids[:]
      #
      return images

    def addImages():

      def getFileInfoDate( image ):

        def prepareFileTMS( url_tms ):

          def createLocalFile():
            response = urllib2.urlopen( url_tms )
            html = response.read()
            response.close()

            fw = open( localName, 'w' )
            fw.write( html )
            fw.close()

          localName = "%s/%s" % ( self.TEMP_DIR, basename( url_tms ) )
          fileInfo = QFileInfo( localName )

          if not fileInfo.exists():
            createLocalFile()
            fileInfo = QFileInfo( localName )

          return fileInfo

        source = image[ 'source' ]
        isUrl = source.find('http://') == 0 or source.find('https://') == 0
        lenSource = len( source)
        isUrl = isUrl and source.rfind( 'xml', lenSource - len( 'xml' ) ) == lenSource - len( 'xml' )   
        fi = prepareFileTMS( source ) if isUrl else QFileInfo( source )

        return { 'fileinfo': fi, 'date': image[ 'date' ] }

      def getFileInfo( image ):

        def prepareFileTMS( url_tms ):

          def createLocalFile():
            response = urllib2.urlopen( url_tms )
            html = response.read()
            response.close()

            fw = open( localName, 'w' )
            fw.write( html )
            fw.close()

          localName = "%s/%s" % ( self.TEMP_DIR, basename( url_tms ) )
          fileInfo = QFileInfo( localName )

          if not fileInfo.exists():
            createLocalFile()
            fileInfo = QFileInfo( localName )

          return fileInfo

        source = image[ 'source' ]
        isUrl = source.find('http://') == 0 or source.find('https://') == 0
        lenSource = len( source)
        isUrl = isUrl and source.rfind( 'xml', lenSource - len( 'xml' ) ) == lenSource - len( 'xml' )   
        fi = prepareFileTMS( source ) if isUrl else QFileInfo( source )

        return { 'fileinfo': fi  }

      def getNameLayerDate(id):
        vdate = l_fileinfo[ id ]['date'].toString( "yyyy-MM-dd" )
        name = l_layer[ id ].name()
        return "%s (%s)" % ( vdate, name )

      def getNameLayer(id):
        return l_layer[ id ].name()

      def setTransparence():

        def getListTTVP():
          t = QgsRasterTransparency.TransparentThreeValuePixel()
          t.red = t.green = t.blue = 0.0
          t.percentTransparent = 100.0
          return [ t ]
        
        extension = ".xml"
        l_ttvp = getListTTVP()
        #
        for id in range( 0, len( l_raster ) ):
          if self.isKilled:
            return
          fileName = l_fileinfo[ id ]['fileinfo'].fileName()
          idExt = fileName.rfind( extension )
          if idExt == -1 or len( fileName ) != ( idExt + len ( extension ) ):
            l_raster[ id ].renderer().rasterTransparency().setTransparentThreeValuePixelList( l_ttvp )

      def cleanLists( lsts ):
        for item in lsts:
          del item[:]
      
      # Sorted images
      if not self.nameFieldDate  is None:
        l_image_sorted = sorted( images, key = lambda item: item['date'], reverse = True )
        l_fileinfo = map( getFileInfoDate, l_image_sorted )
      else:
        l_image_sorted = sorted( images, key = lambda item: item['source'], reverse = True )
        l_fileinfo = map( getFileInfo, l_image_sorted )
      
      del l_image_sorted[:]

      totalRaster = -1 # isKilled
      if self.isKilled:
        del l_fileinfo[:]
        return totalRaster

      l_raster = map( lambda item: 
                        QgsRasterLayer( item['fileinfo'].filePath(), item['fileinfo'].baseName() ),
                        l_fileinfo )

      # l_fileinfo, l_raster

      # Invalid raster
      l_id_error = []
      for id in range( 0, len( l_raster ) ):
        if self.isKilled:
          break
        if not l_raster[ id ].isValid():
          l_id_error.append( id )
      if self.isKilled:
        cleanLists( [ l_fileinfo, l_raster, l_id_error ] )
        return totalRaster

      # l_fileinfo, l_raster, l_id_error

      l_error = None
      l_id_error.reverse()
      if len( l_id_error ) > 0:
        l_error = map( lambda item: item.source(), l_raster )
        l_removes = [ l_fileinfo, l_raster ]
        for id in l_id_error:
          if self.isKilled:
            break
          for item in l_removes:
            item.remove( item[ id ] )
        del l_id_error[:]
        del l_removes[:]
        if self.isKilled:
          cleanLists( [ l_fileinfo, l_raster, l_error ] )
          return totalRaster

      del l_id_error[:]
      # l_fileinfo, l_raster, l_error

      totalRaster = len( l_raster ) 
      # Add raster
      if totalRaster > 0:
        setTransparence()
        l_layer = []
        for item in l_raster:
          if self.isKilled:
            break
          l_layer.append( QgsMapLayerRegistry.instance().addMapLayer( item, addToLegend=False ) )
        if self.isKilled:
          cleanLists( [ l_fileinfo, l_error, l_layer ] )
          return -1

        # l_fileinfo, l_error, l_layer
        getN = getNameLayerDate if not self.nameFieldDate  is None else getNameLayer
        for id in range( 0, len( l_layer ) ):
          if self.isKilled:
            break
          ltl = self.ltgCatalog.addLayer( l_layer[ id ] )
          ltl.setVisible( Qt.Unchecked )
          name = getN( id )
          ltl.setLayerName( name )
          self.addLegendLayer( l_layer[ id ] )
        cleanLists( [ l_fileinfo, l_layer ] )
        if self.isKilled:
          return -1

      # Message Error
      if not l_error is None:
        msgtrans = QCoreApplication.translate("CatalogOTF", "Images invalid:\n%s")
        self.messageError.emit( msgtrans % "\n" .join( l_error ) )
        del l_error[:]

      return totalRaster

    self.isKilled = False
    images = getImagesByCanvas()
    msgtrans = QCoreApplication.translate("CatalogOTF", "Processing %d")
    self.messageStatus.emit( msgtrans %  len( images ) )
    totalRaster = addImages()
    msg = "" if totalRaster == -1 else str( totalRaster ) 
    self.messageStatus.emit( msg )

    del images[:]
    self.finished.emit( self.isKilled )

  def kill(self):
    self.isKilled = True


class CatalogOTF(QObject):
  
  # Signals 
  settedLayer = pyqtSignal( "QgsVectorLayer")
  removedLayer = pyqtSignal( str )
  killed = pyqtSignal( str )
  changedNameLayer = pyqtSignal( str, str )
  changedTotal = pyqtSignal( str, str )
  changedIconRun = pyqtSignal( str, bool )

  def __init__(self, iface, tableCOTF):
    
    def connecTableCOTF():
      self.settedLayer.connect( tableCOTF.insertRow )
      self.removedLayer.connect( tableCOTF.removeRow )
      self.changedNameLayer.connect( tableCOTF.changedNameLayer )
      self.changedTotal.connect( tableCOTF.changedTotal )
      self.changedIconRun.connect( tableCOTF.changedIconRun )
      self.killed.connect( tableCOTF.killed )

    super(CatalogOTF, self).__init__()
    self.iface = iface
    self.canvas = iface.mapCanvas()
    self.ltv = iface.layerTreeView()
    self.model = self.ltv.layerTreeModel()
    self.ltgRoot = QgsProject.instance().layerTreeRoot()
    self.msgBar = iface.messageBar()
    self.legendTMS = LegendTMS( 'Catalog OTF')
    self.legendRaster = LegendRaster( 'Catalog OTF')

    self._initThread()

    connecTableCOTF()
    self.model.dataChanged.connect( self.dataChanged )
    QgsMapLayerRegistry.instance().layersWillBeRemoved.connect( self.layersWillBeRemoved ) # Catalog layer removed

    self.layer = self.layerName = self.nameFieldSource = self.nameFieldDate = None
    self.ltgCatalog = self.ltgCatalogName = self.hasCanceled = None
    self.currentStatusLC = None

  def __del__(self):
    self._finishThread()
    del self.legendTMS
    del self.legendRaster
    QgsMapLayerRegistry.instance().layersWillBeRemoved.disconnect( self.layersWillBeRemoved ) # Catalog layer removed

  def _initThread(self):
    self.thread = QThread( self )
    self.thread.setObjectName( "QGIS_Plugin_%s" % NAME_PLUGIN.replace( ' ', '_' ) )
    self.worker = WorkerPopulateGroup( self.addLegendLayerWorker )
    self.worker.moveToThread( self.thread )
    self._connectWorker()

  def _finishThread(self):
    self._connectWorker( False )
    self.worker.deleteLater()
    self.thread.wait()
    self.thread.deleteLater()
    self.thread = self.worker = None

  def _connectWorker(self, isConnect = True):
    ss = [
      { 'signal': self.thread.started, 'slot': self.worker.run },
      { 'signal': self.worker.finished, 'slot': self.finishedPG },
      { 'signal': self.worker.messageStatus, 'slot': self.messageStatusPG },
      { 'signal': self.worker.messageError, 'slot': self.messageErrorPG }
    ]
    if isConnect:
      for item in ss:
        item['signal'].connect( item['slot'] )  
    else:
      for item in ss:
        item['signal'].disconnect( item['slot'] )

  def addLegendLayerWorker(self, layer):
    if layer.type() == QgsMapLayer.RasterLayer:  
      metadata = layer.metadata()
      if metadata.find( "GDAL provider" ) != -1:
        if  metadata.find( "OGC Web Map Service" ) != -1:
          if self.legendTMS.hasTargetWindows( layer ):
            self.legendTMS.setLayer( layer )
        else:
          self.legendRaster.setLayer( layer )

  def run(self):
    self.hasCanceled = False # Check in finishedPG

    if self.thread.isRunning():
      self.worker.kill()
      self.hasCanceled = True
      msgtrans = QCoreApplication.translate("CatalogOTF", "Canceled search for image from layer ")
      msgtrans += self.layerName 
      self.msgBar.pushMessage( NAME_PLUGIN, msgtrans, QgsMessageBar.WARNING, 2 )
      self.changedTotal.emit( self.layer.id(), "Canceling processing")
      self.killed.emit( self.layer.id() )
      return

    if self.layer is None:
      msgtrans = QCoreApplication.translate("CatalogOTF", "Need define layer catalog")
      self.msgBar.pushMessage( NAME_PLUGIN, msgtrans, QgsMessageBar.WARNING, 2 )
      return

    self._setGroupCatalog()
    self.ltgCatalogName = self.ltgCatalog.name()

    renderFlag = self.canvas.renderFlag()
    if renderFlag:
      self.canvas.setRenderFlag( False )
      self.canvas.stopRendering()

    self._populateGroupCatalog()

    if renderFlag:
      self.canvas.setRenderFlag( True )
      self.canvas.refresh()

  def _populateGroupCatalog(self):

    def getCurrentStatusLayerCatalog():
      node = self.ltv.currentNode()
      if node is None or not node.nodeType() == QgsLayerTreeNode.NodeLayer:
        return None
      #
      ltlCurrent = self.ltgCatalog.findLayer( node.layerId() )
      if ltlCurrent is None:
        return None
      #
      return { 'source': node.layer().source(), 'visible': node.isVisible() }

    def runWorker():
      data = {}
      data['nameFieldDate'] = self.nameFieldDate
      data['nameFieldSource'] = self.nameFieldSource
      data['layer'] = self.layer
      data['ltgCatalog'] = self.ltgCatalog
      self.worker.setData( data )
      self.thread.start()
      #self.worker.run() # DEBUG

    self.currentStatusLC = getCurrentStatusLayerCatalog()
    self.ltgCatalog.removeAllChildren()
    #
    runWorker() # See finishPG

  def _setGroupCatalog(self):
    self.ltgCatalogName = "%s - Catalog" % self.layer.name()
    self.ltgCatalog = self.ltgRoot.findGroup( self.ltgCatalogName  )
    if self.ltgCatalog is None:
      self.ltgCatalog = self.ltgRoot.addGroup( self.ltgCatalogName )

  @pyqtSlot( bool )
  def finishedPG(self, isKilled ):
    self.thread.quit()
    self.changedIconRun.emit( self.layer.id(), self.layer.selectedFeatureCount() > 0 )
    if self.hasCanceled:
      self.changedTotal.emit( self.layer.id(), '0')

  @pyqtSlot( str )
  def messageStatusPG(self, msg):
    self.changedTotal.emit( self.layer.id(), msg  )

  @pyqtSlot( str )
  def messageErrorPG(self, msg):
    self.msgBar.pushMessage( NAME_PLUGIN, msg, QgsMessageBar.CRITICAL, 8 )

  @pyqtSlot( 'QModelIndex', 'QModelIndex' )
  def dataChanged(self, idTL, idBR):
    if idTL != idBR:
      return

    if not self.ltgCatalog is None and self.ltgCatalog == self.model.index2node( idBR ):
      name = self.ltgCatalog.name()
      if self.ltgCatalogName != name:
        self.ltgCatalogName = name
        return

    if not self.layer is None and self.ltgRoot.findLayer( self.layer.id() ) == self.model.index2node( idBR ):
      name = self.layer.name()
      if self.layerName != name:
        self.changedNameLayer.emit( self.layer.id(), name )
        self.layerName = name

  @pyqtSlot( list )
  def layersWillBeRemoved(self, layerIds):
    if self.layer is None:
      return
    if self.layer.id() in layerIds:
      self.removedLayer.emit( self.layer.id() )
      self.removeLayerCatalog()

  @staticmethod
  def getNameFieldsCatalog(layer):

    def getFirstFeature():
      f = QgsFeature()
      #
      fr = QgsFeatureRequest() # First FID can be 0 or 1 depend of provider type
      it = layer.getFeatures( fr )
      isOk = it.nextFeature( f )
      it.close()
      #
      if not isOk or not f.isValid():
        del f
        return None
      else:
        return f

    def hasAddress(feature, idField):

      def asValidUrl( url):
        isOk = True
        try:
          urllib2.urlopen(url)
        except urllib2.HTTPError, e:
          isOk = False
        except urllib2.URLError, e:
          isOk = False
        #
        return isOk  

      value = feature.attributes()[ idField ]
      if value is None or type(value) == QPyNullVariant:
        return False

      isUrl = value.find('http://') == 0 or value.find('https://') == 0
      lenSource = len( value )
      isUrl = isUrl and value.rfind( 'xml', lenSource - len( 'xml' ) ) == lenSource - len( 'xml' )   
      if isUrl:
        return asValidUrl( value )
      #
      fileInfo = QFileInfo( value )
      return fileInfo.isFile()

    def hasDate(feature, idField):
      value = feature.attributes()[ idField ]
      if value is None or type(value) == QPyNullVariant:
        return False
      #          
      return True if value.isValid() else False

    if layer is None or layer.type() != QgsMapLayer.VectorLayer or layer.geometryType() != QGis.Polygon:
      return None
    #
    firstFeature = getFirstFeature()
    if firstFeature is None:
      return None
    #
    fieldSource = None
    fieldDate = None
    isOk = False
    for item in layer.pendingFields().toList():
      if item.type() == QVariant.String:
        if fieldSource is None and hasAddress( firstFeature, layer.fieldNameIndex( item.name() ) ):
          fieldSource = item.name()
      elif item.type() == QVariant.Date:
        if fieldDate is None and hasDate( firstFeature, layer.fieldNameIndex( item.name() ) ):
          fieldDate = item.name()
      if not fieldSource is None:
        isOk = True
        break
    #
    return { 'nameSource': fieldSource, 'nameDate': fieldDate } if isOk else None 

  def setLayerCatalog(self, layer, nameFiedlsCatalog):
    self.layer = layer
    self.layerName = layer.name()
    self.nameFieldSource = nameFiedlsCatalog[ 'nameSource' ]
    self.nameFieldDate = nameFiedlsCatalog[ 'nameDate' ]
    self.settedLayer.emit( self.layer )

  def removeLayerCatalog(self):
    self.ltgRoot.removeChildNode( self.ltgCatalog )
    self.ltgCatalog = None
    self.layer = self.nameFieldSource = self.nameFieldDate =  None


class TableCatalogOTF(QObject):

  runCatalog = pyqtSignal( str )

  def __init__(self):
    def initGui():
      self.tableWidget.setWindowTitle("Catalog OTF")
      self.tableWidget.setSortingEnabled( False )
      msgtrans = QCoreApplication.translate("CatalogOTF", "Layer,Total")
      headers = msgtrans.split(',')
      self.tableWidget.setColumnCount( len( headers ) )
      self.tableWidget.setHorizontalHeaderLabels( headers )
      self.tableWidget.resizeColumnsToContents()

    super( TableCatalogOTF, self ).__init__()
    self.tableWidget = QTableWidget()
    initGui()

  def _getRowLayerID(self, layerID):
    for row in range( self.tableWidget.rowCount() ):
      if layerID == self.tableWidget.cellWidget( row, 0 ).objectName():
        return row
    return -1

  def _changedText(self, layerID, name, column):
    row = self._getRowLayerID( layerID )
    if row != -1:
      wgt = self.tableWidget.cellWidget( row, column ) if column == 0 else self.tableWidget.item( row, column )
      wgt.setText( name )
      wgt.setToolTip( name )
      self.tableWidget.resizeColumnsToContents()

  @pyqtSlot()
  def _onRunCatalog(self):
    btn = self.sender()
    icon = QIcon( joinPath( dirname(__file__), 'cancel_red.svg' ) )
    btn.setIcon( icon )
    layerID = btn.objectName() 
    self.runCatalog.emit( layerID )

  @pyqtSlot()  
  def _onSelectionChanged(self):
    layer = self.sender()
    row = self._getRowLayerID( layer.id() )
    if row != -1:
      wgt = self.tableWidget.cellWidget( row, 0 )
      nameIcon = 'check_green.svg' if layer.selectedFeatureCount() == 0 else 'check_yellow.svg'
      icon = QIcon( joinPath( dirname(__file__), nameIcon ) )
      wgt.setIcon( icon )

  @pyqtSlot( "QgsVectorLayer")
  def insertRow(self, layer):
    row = self.tableWidget.rowCount()
    self.tableWidget.insertRow( row )

    column = 0 # Layer
    layerName = layer.name()
    nameIcon = 'check_green.svg' if layer.selectedFeatureCount() == 0 else 'check_yellow.svg'
    icon = QIcon( joinPath( dirname(__file__), nameIcon ) )
    btn = QPushButton( icon, layerName, self.tableWidget )
    btn.setObjectName( layer.id() )
    btn.setToolTip( layerName )
    btn.clicked.connect( self._onRunCatalog )
    layer.selectionChanged.connect( self._onSelectionChanged )
    self.tableWidget.setCellWidget( row, column, btn )

    column = 1 # Total
    item = QTableWidgetItem("None")
    item.setFlags( Qt.ItemIsSelectable | Qt.ItemIsEnabled )
    self.tableWidget.setItem( row, column, item )

    self.tableWidget.resizeColumnsToContents()

  @pyqtSlot( str )
  def removeRow(self, layerID):
    row = self._getRowLayerID( layerID )
    if row != -1:
      self.tableWidget.removeRow( row )

  @pyqtSlot( str, str )
  def changedNameLayer(self, layerID, name):
    self._changedText( layerID, name, 0 )

  @pyqtSlot( str, str )
  def changedTotal(self, layerID, value):
    self._changedText( layerID, value, 1 )

  @pyqtSlot( str, bool )
  def changedIconRun(self, layerID, selected):
    row = self._getRowLayerID( layerID )
    if row != -1:
      btn = self.tableWidget.cellWidget( row, 0 )
      nameIcon = 'check_green.svg' if not selected else 'check_yellow.svg'
      icon = QIcon( joinPath( dirname(__file__), nameIcon ) )
      btn.setIcon( icon )
      btn.setEnabled( True )

  @pyqtSlot( str )
  def killed(self, layerID):
    row = self._getRowLayerID( layerID )
    if row != -1:
      btn = self.tableWidget.cellWidget( row, 0 )
      btn.setEnabled( False )

  def widget(self):
    return self.tableWidget


class DockWidgetCatalogOTF(QDockWidget):

  def __init__(self, iface):

    def setupUi():
      self.setObjectName( "catalogotf_dockwidget" )
      wgt = QWidget( self )
      wgt.setAttribute(Qt.WA_DeleteOnClose)
      #
      gridLayout = QGridLayout( wgt )
      gridLayout.setContentsMargins( 0, 0, gridLayout.verticalSpacing(), gridLayout.verticalSpacing() )
      #
      tbl = self.tbl_cotf.widget()
      ( iniY, iniX, spanY, spanX ) = ( 0, 0, 1, 2 )
      gridLayout.addWidget( tbl, iniY, iniX, spanY, spanX )
      #
      msgtrans = QCoreApplication.translate("CatalogOTF", "Find catalog")
      btnFindCatalogs = QPushButton( msgtrans, wgt )
      btnFindCatalogs.clicked.connect( self.findCatalogs )
      ( iniY, iniX, spanY, spanX ) = ( 1, 0, 1, 1 )
      gridLayout.addWidget( btnFindCatalogs, iniY, iniX, spanY, spanX )
      #
      wgt.setLayout( gridLayout )
      self.setWidget( wgt )

    super( DockWidgetCatalogOTF, self ).__init__( "Catalog On The Fly", iface.mainWindow() )
    #
    self.iface = iface
    self.cotf = {} 
    self.tbl_cotf = TableCatalogOTF()
    self.tbl_cotf.runCatalog.connect( self._onRunCatalog )
    #
    setupUi()

  @pyqtSlot( str )
  def _onRunCatalog(self, layerID):
    if layerID in self.cotf.keys(): # Maybe Never happend
      self.cotf[ layerID ].run()
  
  @pyqtSlot( str )
  def removeLayer(self, layerID):
    del self.cotf[ layerID ]

  @pyqtSlot()
  def findCatalogs(self):
    def addLegendImages(layer):
     name = "%s - Catalog" % layer.name()
     ltgCatalog = QgsProject.instance().layerTreeRoot().findGroup( name  )
     if not ltgCatalog is None:
      for item in map( lambda item: item.layer(), ltgCatalog.findLayers() ):
        self.cotf[ layerID ].addLegendLayerWorker( item )

    def checkTempDir():
      tempDir = QDir( WorkerPopulateGroup.TEMP_DIR )
      if not tempDir.exists():
        msgtrans1 = QCoreApplication.translate("CatalogOTF", "Created temporary directory '%s' for TMS")
        msgtrans2 = QCoreApplication.translate("CatalogOTF", "Not possible create temporary directory '%s' for TMS")
        isOk = tempDir.mkpath( WorkerPopulateGroup.TEMP_DIR )
        msgtrans = msgtrans1 if isOk else msgtrans2
        tempDir.setPath( WorkerPopulateGroup.TEMP_DIR )
        msg = msgtrans % tempDir.absolutePath()
        msgBar.pushMessage( NAME_PLUGIN, msg, QpluginNamegsMessageBar.CRITICAL, 5 )

    def overrideCursor():
      cursor = QApplication.overrideCursor()
      if cursor is None or cursor == 0:
          QApplication.setOverrideCursor( QCursor( Qt.WaitCursor ) )
      elif cursor.shape() != Qt.WaitCursor:
          QApplication.setOverrideCursor( QCursor( Qt.WaitCursor ) )

    overrideCursor()
    find = False
    f = lambda item: \
        item.type() == QgsMapLayer.VectorLayer and \
        item.geometryType() == QGis.Polygon and \
        not item.id() in self.cotf.keys()
    for item in filter( f, self.iface.legendInterface().layers() ):
      nameFiedlsCatalog = CatalogOTF.getNameFieldsCatalog( item )
      if not nameFiedlsCatalog is None:
        layerID = item.id()
        self.cotf[ layerID ] = CatalogOTF( self.iface, self.tbl_cotf )
        self.cotf[ layerID ].removedLayer.connect( self.removeLayer )
        self.cotf[ layerID ].setLayerCatalog( item, nameFiedlsCatalog ) # Insert table
        addLegendImages( item )
        find = True
    #
    msgBar = self.iface.messageBar()
    if not find:
      f = lambda item: \
          item.type() == QgsMapLayer.VectorLayer and \
          item.geometryType() == QGis.Polygon
      totalLayers = len( filter( f, self.iface.legendInterface().layers() ) )
      msgtrans = QCoreApplication.translate("CatalogOTF", "Did not find a new catalog. Catalog layers %d of %d(polygon layers)")
      msg = msgtrans % ( len( self.cotf ), totalLayers ) 
      msgBar.pushMessage( NAME_PLUGIN, msg, QgsMessageBar.INFO, 3 )
    else:
      checkTempDir()

    QApplication.restoreOverrideCursor()


class ProjectDockWidgetCatalogOTF():

  pluginName = "Plugin_DockWidget_Catalog_OTF"
  pluginSetting = "/images_wms"
  nameTmpDir = "tmp"

  def __init__(self, iface):
    self.iface = iface

  @pyqtSlot("QDomDocument")
  def onReadProject(self, document):
    def createTmpDir():
      tmpDir = "%s%s" % ( sepPath, self.nameTmpDir )
      if not isdir( tmpDir ):
        makedirs( tmpDir )

    proj = QgsProject.instance()
    value, ok = proj.readEntry( self.pluginName, self.pluginSetting )
    if ok and bool( value ):
      createTmpDir()
      newImages = 0
      for item in json.loads( value ):
        source = item['source']
        if not QFileInfo( source ).exists():
          fw = open( source, 'w' )
          fw.write( item[ 'wms' ] )
          fw.close()
          newImages += 1
      if newImages > 0:
        msg = "Please reopen project - DON'T SAVE. The WMS images were regenerated (%d images)" % newImages
        self.iface.messageBar().pushMessage( NAME_PLUGIN, msg, QgsMessageBar.WARNING, 8 )

  @pyqtSlot("QDomDocument")
  def onWriteProject(self, document):
    def getContentFile( source ):
      with open( source, 'r' ) as content_file:
        content = content_file.read()
      return content

    def filter_wms_tmp( layer ):
      if not layer.type() == QgsMapLayer.RasterLayer:
        return False

      metadata = layer.metadata()
      if not ( metadata.find( "GDAL provider" ) != -1 and metadata.find( "OGC Web Map Service" ) != -1  ):
        return False

      lstDir = dirname( layer.source() ).split( sepPath)
      if not ( len( lstDir) == 2 and lstDir[1] == self.nameTmpDir ):
        return False
      
      return True

    layers = map ( lambda item: item.layer(), self.iface.layerTreeView().layerTreeModel().rootGroup().findLayers() )
    layers_wms_tmp = filter( filter_wms_tmp, layers )
    images_wms = []
    for item in layers_wms_tmp:
      source = item.source()
      images_wms.append( { 'source': source, 'wms': getContentFile( source) } )
    proj = QgsProject.instance()
    if len( images_wms ) == 0:
      proj.removeEntry( self.pluginName, self.pluginSetting )
    else:
      proj.writeEntry( self.pluginName, self.pluginSetting, json.dumps( images_wms ) )
