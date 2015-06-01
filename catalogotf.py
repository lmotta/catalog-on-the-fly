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
from os.path import basename

from PyQt4.QtCore import ( 
     Qt, QObject, QTimer, QThread, QFileInfo, QDir, QVariant, QCoreApplication,
     QPyNullVariant, pyqtSignal, pyqtSlot
)

from PyQt4.QtGui  import (
     QApplication,  QCursor,
     QTableWidget, QTableWidgetItem,
     QPushButton, QGridLayout, QProgressBar, QDockWidget, QWidget
)

from qgis.gui import ( QgsHighlight, QgsMessageBar ) 
from qgis.core import (
  QgsProject, QGis,
  QgsMapLayerRegistry, QgsMapLayer,
  QgsFeature, QgsFeatureRequest, QgsGeometry, QgsSpatialIndex,
  QgsCoordinateTransform,
  QgsRasterLayer, QgsRasterTransparency,
  QgsLayerTreeNode
)

NAME_PLUGIN = "Catalog On The Fly"

class FeatureImage:

  def __init__(self, layer, iface):
    self.layer = layer
    self.canvas = iface.mapCanvas()
    self._image = self.geom = self.hl = self.msgError = None

  def _getGeometry(self, fid):
    fr = QgsFeatureRequest( fid )
    fr.setSubsetOfAttributes( [], self.layer.dataProvider().fields() )
    it = self.layer.getFeatures( fr )
    feat = QgsFeature()
    isOk = it.nextFeature( feat )
    it.close()

    return QgsGeometry( feat.geometry() ) if isOk else None

  def clear(self):
    del self.geom
    del self.hl
    self._image = self.geom = self.hl = None

  def setImage(self, image, dicImages):
    if self._image == image:
      return True
    #
    fid = dicImages[ image ]['id']
    geom = self._getGeometry( fid )
    if geom is None:
      msgtrans = QCoreApplication.translate("CatalogOTF", "Geometry of feature (fid = %d) of layer ('%s') is invalid")
      self.msgError = msgtrans % ( fid, self.layer.name() )
      return False
    #
    self.geom = geom
    self._image = image
    #
    del self.hl
    self.hl = QgsHighlight( self.canvas, self.geom, self.layer )
    self.hl.hide()
    #
    return True

  def image(self):
    return self._image

  def hide(self):
    self.hl.hide()
    self.canvas.refresh()

  def highlight(self, second=0 ):
    if self.hl is None:
      return
    #
    self.hl.setWidth( 5 )
    self.hl.show()
    self.canvas.refresh()
    #
    QTimer.singleShot( second * 1000, self.hide )

  def zoom(self):
    if self.geom is None:
      return
    #
    crsCanvas = self.canvas.mapSettings().destinationCrs()
    crsLayer = self.layer.crs()
    ct = QgsCoordinateTransform( crsCanvas, crsLayer )
    extent = self.geom.boundingBox() if crsCanvas == crsLayer else ct.transform( self.geom.boundingBox() )
    #
    self.canvas.setExtent( extent )
    self.canvas.refresh()

  def msgError(self):
    return self.msgError


class WorkerPopulateGroup(QObject):

  # Static
  TEMP_DIR = "/tmp"
  
  # Signals 
  finished = pyqtSignal( bool )
  messageStatus = pyqtSignal( str )
  messageError = pyqtSignal( str )

  def __init__(self, canvas):
    
    super(WorkerPopulateGroup, self).__init__()
    self.killed = False
    #
    self.canvas = canvas
    self.dicImages = self.nameFieldSource = self.layer = self.ltgCatalog = self.selectedImage = None

  def setData(self, data):
    self.dicImages = data['dicImages']
    self.nameFieldSource = data['nameFieldSource']
    self.layer = data['layer']
    self.ltgCatalog = data['ltgCatalog']
    self.selectedImage = data['selectedImage']

  @pyqtSlot()
  def run(self):

    def getImagesByCanvas():
      images = []
      #
      rectLayer = self.layer.extent() if not self.selectedImage else self.layer.boundingBoxOfSelected()
      crsLayer = self.layer.crs()
      #
      crsCanvas = self.canvas.mapSettings().destinationCrs()
      ct = QgsCoordinateTransform( crsCanvas, crsLayer )
      rectCanvas = self.canvas.extent() if crsCanvas == crsLayer else ct.transform( self.canvas.extent() )
      #
      if not rectLayer.intersects( rectCanvas ):
        return [] 
      #
      fr = QgsFeatureRequest()
      if self.selectedImage:
        fr.setFilterFids( self.layer.selectedFeaturesIds() )
      #fr.setSubsetOfAttributes( [ self.nameFieldSource ], self.layer.dataProvider().fields() )
      index = QgsSpatialIndex( self.layer.getFeatures( fr ) )
      fids = index.intersects( rectCanvas )
      #
      del fr
      del index
      #
      fr = QgsFeatureRequest()
      fr.setFilterFids ( fids )
      it = self.layer.getFeatures( fr ) 
      f = QgsFeature()
      while it.nextFeature( f ):
        if f.geometry().intersects( rectCanvas ):
          images.append( basename( f[ self.nameFieldSource ] ) )
      #
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
            #
            fw = open( localName, 'w' )
            fw.write( html )
            fw.close()

          localName = "%s/%s" % ( self.TEMP_DIR, basename( url_tms ) )
          fileInfo = QFileInfo( localName )
          #
          if not fileInfo.exists():
            createLocalFile()
            fileInfo = QFileInfo( localName )
          #
          return fileInfo

        value = self.dicImages[ image ]
        source = value['source']
        isUrl = source.find('http://') == 0 or source.find('https://') == 0
        fi = prepareFileTMS( source ) if isUrl else QFileInfo( source )
        #
        return { 'fileinfo': fi, 'date': value['date'] }
      #
      
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
          fileName = l_fileinfo_date[ id ]['fileinfo'].fileName()
          idExt = fileName.rfind( extension )
          if idExt == -1 or len( fileName ) != ( idExt + len ( extension ) ):
            l_raster[ id ].renderer().rasterTransparency().setTransparentThreeValuePixelList( l_ttvp )

      def cleanLists( lsts ):
        for item in lsts:
          del item[:]
      
      # Sorted images 
      l_image_date = map( lambda item: { '_image': item, 'date': self.dicImages [ item ]['date'] }, images )
      l_image_date_sorted = sorted( l_image_date, key = lambda item: item['date'], reverse = True )
      #
      l_image =  map( lambda item: item['_image'], l_image_date_sorted )
      #
      del l_image_date[:]
      del l_image_date_sorted[:]
      #
      totalRaster = -1 # isKilled
      #
      l_fileinfo_date = map( getFileInfoDate, l_image )
      #
      if self.isKilled:
        cleanLists( [ l_image, l_fileinfo_date ] )
        return totalRaster
      #
      l_raster = map( lambda item: 
                        QgsRasterLayer( item['fileinfo'].filePath(), item['fileinfo'].baseName() ),
                        l_fileinfo_date )
      #
      if self.isKilled:
        cleanLists( [ l_image, l_fileinfo_date, l_raster ] )
        return totalRaster
      #
      # Invalid raster
      l_id_error = []
      for id in range( 0, len( l_raster ) ):
        if not l_raster[ id ].isValid():
          l_id_error.append( id )
      #
      l_error = None
      if len( l_id_error ) > 0:
        l_error = map( lambda item: l_image[ item ], l_id_error )
        #
        l_removes = [ l_raster, l_fileinfo_date, l_image ]
        for id in l_id_error:
          for item in l_removes:
            item.remove( item[ id ] )
        del l_id_error[:]
        del l_removes[:]
      #
      if self.isKilled:
        cleanLists( [ l_image, l_fileinfo_date, l_raster, l_error ] )
        return totalRaster
      #
      totalRaster = len( l_raster ) 
      # Add raster
      if totalRaster > 0:
        setTransparence()
        l_layer = []
        for item in l_raster:
          l_layer.append( QgsMapLayerRegistry.instance().addMapLayer( item, addToLegend=False ) )
          #
          if self.isKilled:
            cleanLists( [ l_image, l_fileinfo_date, l_raster, l_error, l_layer ] )
            return -1
          #
        for id in range( 0, len( l_layer ) ):
          ltl = self.ltgCatalog.addLayer( l_layer[ id ] )
          ltl.setVisible( Qt.Unchecked )
          name = "%s (%s)" % ( l_fileinfo_date[ id ]['date'].toString( "yyyy-MM-dd" ), l_image[ id ] )
          ltl.setLayerName( name )
        #
        cleanLists( [ l_image, l_fileinfo_date, l_raster, l_layer ] )
      #
      # Message Error
      if not l_error is None:
        msgtrans = QCoreApplication.translate("CatalogOTF", "Images invalid:\n%s")
        self.messageError.emit( msgtrans % "\n" .join( l_error ) )
        del l_error[:]
      #
      return totalRaster

    self.isKilled = False
    images = getImagesByCanvas()
    msgtrans = QCoreApplication.translate("CatalogOTF", "Processing %d")
    self.messageStatus.emit( msgtrans %  len( images ) )
    totalRaster = addImages()
    msg = "" if totalRaster == -1 else str( totalRaster ) 
    self.messageStatus.emit( msg )
    #
    del images[:]
    self.finished.emit( self.isKilled )

  def kill(self):
    self.isKilled = True


class CatalogOTF(QObject):
  
  # Signals 
  settedLayer = pyqtSignal( str, str )
  removedLayer = pyqtSignal( str )
  changedNameLayer = pyqtSignal( str, str )
  changedNameGroup = pyqtSignal( str, str )
  removedGroup = pyqtSignal( str )
  changedTotal = pyqtSignal( str, str )

  def __init__(self, iface, tableCOTF):
    
    def connecTableCOTF():
      self.settedLayer.connect( tableCOTF.insertRow )
      self.removedLayer.connect( tableCOTF.removeRow )
      self.changedNameLayer.connect( tableCOTF.changedNameLayer )
      self.changedNameGroup.connect( tableCOTF.changedNameGroup )
      self.removedGroup.connect( tableCOTF.changedNameGroup )
      self.changedTotal.connect( tableCOTF.changedTotal )
    
    super(CatalogOTF, self).__init__()
    self.iface = iface
    self.canvas = iface.mapCanvas()
    self.ltv = iface.layerTreeView()
    self.model = self.ltv.layerTreeModel()
    self.ltgRoot = QgsProject.instance().layerTreeRoot()
    self.msgBar = iface.messageBar()
    #
    self._initThread()
    #
    connecTableCOTF()
    QgsMapLayerRegistry.instance().layersWillBeRemoved.connect( self.layersWillBeRemoved ) # Catalog layer removed
    #
    self.layer = self.layerName = self.nameFieldSource = self.nameFieldDate = None
    self.ltgCatalog = self.ltgCatalogName = self.dicImages = None
    self.featureImage = self.currentStatusLC = None
    self.zoomImage = self.highlightImage = self.selectedImage = False

  def __del__(self):
    self._finishThread()
    
  def _connect(self, isConnect = True):
    ss = [
      { 'signal': self.canvas.extentsChanged , 'slot': self.extentsChanged },
      { 'signal': self.canvas.destinationCrsChanged, 'slot': self.destinationCrsChanged_MapUnitsChanged },
      { 'signal': self.canvas.mapUnitsChanged, 'slot': self.destinationCrsChanged_MapUnitsChanged },
      { 'signal': self.layer.selectionChanged, 'slot': self.selectionChanged },
      { 'signal': self.ltv.activated, 'slot': self.activated },
      { 'signal': self.model.dataChanged, 'slot': self.dataChanged },
      { 'signal': self.ltgRoot.willRemoveChildren, 'slot': self.willRemoveChildren }
    ]
    if isConnect:
      for item in ss:
        item['signal'].connect( item['slot'] )  
    else:
      for item in ss:
        item['signal'].disconnect( item['slot'] )

  def _initThread(self):
    self.thread = QThread( self )
    self.thread.setObjectName( "QGIS_Plugin_%s" % NAME_PLUGIN )
    self.worker = WorkerPopulateGroup( self.canvas )
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

  def _setFeatureImage(self, layer):
    if layer is None or \
       layer.type() != QgsMapLayer.RasterLayer or \
       self.ltgCatalog is None or \
       self.ltgCatalog.findLayer( layer.id() ) is None:
      #
      return False
    #
    image = basename( layer.source() )
    if not image in self.dicImages .keys():
      msgtrans = QCoreApplication.translate("CatalogOTF", "Image (%s) not in catalog layer ('%s')")
      msg = msgtrans % ( image, self.layer.name() )
      self.msgBar.pushMessage( NAME_PLUGIN, msg, QgsMessageBar.CRITICAL, 4 )
      #
      return False
    #
    if not self.featureImage.setImage( image, self.dicImages ):
      self.msgBar.pushMessage( NAME_PLUGIN, self.featureImage.msgError(), QgsMessageBar.CRITICAL, 4 )
      #
      return False
    #
    return True

  def _populateGroupCatalog(self):

    def overrideCursor():
      cursor = QApplication.overrideCursor()
      if cursor is None or cursor == 0:
          QApplication.setOverrideCursor( QCursor( Qt.WaitCursor ) )
      elif cursor.shape() != Qt.WaitCursor:
          QApplication.setOverrideCursor( QCursor( Qt.WaitCursor ) )

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
      data['dicImages'] = self.dicImages
      data['nameFieldSource'] = self.nameFieldSource
      data['layer'] = self.layer
      data['ltgCatalog'] = self.ltgCatalog
      data['selectedImage'] = self.selectedImage
      self.worker.setData( data )
      self.thread.start()
    #
    if self.thread.isRunning():
      self.worker.kill()
      return
    #
    self.ltv.activated.disconnect( self.activated )
    overrideCursor()
    self.currentStatusLC = getCurrentStatusLayerCatalog()
    self.ltgCatalog.removeAllChildren()
    #
    runWorker() # See finishPG

  def _setGroupCatalog(self):
    self.ltgCatalogName = "%s - Catalog" % self.layer.name()
    self.changedNameGroup.emit( self.layer.id(), self.ltgCatalogName )
    self.ltgCatalog = self.ltgRoot.findGroup( self.ltgCatalogName  )
    if self.ltgCatalog is None:
      self.ltgCatalog = self.ltgRoot.addGroup( self.ltgCatalogName )

  @pyqtSlot( bool )
  def finishedPG(self, isKilled ):
    
    def setCurrentImage():
      sourceImage = self.dicImages[ self.featureImage.image() ]['source']
      ltlsImage = filter( lambda item: item.layer().source() == sourceImage, self.ltgCatalog.findLayers()  )
      if len( ltlsImage ) > 0:
        ltl = ltlsImage[0]
        layer = ltl.layer()
        self.ltv.setCurrentLayer( layer )
        if not self.currentStatusLC is None and self.currentStatusLC['source'] == layer.source():
          ltl.setVisible( self.currentStatusLC['visible'] ) 
    
    self.ltv.activated.connect( self.activated )
    QApplication.restoreOverrideCursor()
    #
    if not isKilled and not self.featureImage.image() is None:
      setCurrentImage()
    #
    self.thread.quit()
    #
    if isKilled:
      self._populateGroupCatalog()

  @pyqtSlot( str )
  def messageStatusPG(self, msg):
    self.changedTotal.emit( self.layer.id(), msg  )

  @pyqtSlot( str )
  def messageErrorPG(self, msg):
    self.msgBar.pushMessage( NAME_PLUGIN, msg, QgsMessageBar.CRITICAL, 4 )

  @pyqtSlot()
  def extentsChanged(self):
    if self.layer is None:
      msgtrans = QCoreApplication.translate("CatalogOTF", "Need define layer catalog")
      self.msgBar.pushMessage( NAME_PLUGIN, msgtrans, QgsMessageBar.WARNING, 2 )
      return
    #
    renderFlag = self.canvas.renderFlag()
    if renderFlag:
      self.canvas.setRenderFlag( False )
      self.canvas.stopRendering()
    #
    self._populateGroupCatalog()
    #
    if renderFlag:
      self.canvas.setRenderFlag( True )
      self.canvas.refresh()
    #
    if self.highlightImage:
      self.featureImage.highlight( 3 )

  @pyqtSlot( 'QModelIndex' )
  def activated(self, index ):
    if self.layer is None:
      msgtrans = QCoreApplication.translate("CatalogOTF", "Need define layer catalog")
      self.msgBar.pushMessage( NAME_PLUGIN, msgtrans, QgsMessageBar.WARNING, 2 )
      return
    #
    layer = self.ltv.currentLayer()
    #
    if layer is None: # or not self.highlightImage and not self.zoomImage :
      return
    #
    self.featureImage.clear()
    #
    if not self._setFeatureImage( layer ): 
      return
    #
    if self.zoomImage:
      ss = { 'signal': self.canvas.extentsChanged , 'slot': self.extentsChanged }
      ss['signal'].disconnect( ss['slot'] )
      self.featureImage.zoom()
      ss['signal'].connect( ss['slot'] )
      self._populateGroupCatalog()
    #
    if self.highlightImage:
      self.featureImage.highlight( 3 )

  @pyqtSlot( 'QModelIndex', 'QModelIndex' )
  def dataChanged(self, idTL, idBR):
    if idTL != idBR:
      return
    #
    if self.ltgCatalog == self.model.index2node( idBR ):
      name = self.ltgCatalog.name()
      if self.ltgCatalogName != name:
        self.changedNameGroup.emit( self.layer.id(), name )
        self.ltgCatalogName = name
    elif self.ltgRoot.findLayer( self.layer.id() ) == self.model.index2node( idBR ):
      name = self.layer.name()
      if self.layerName != name:
        self.changedNameLayer.emit( self.layer.id(), name )
        self.layerName = name

  @pyqtSlot( list )
  def layersWillBeRemoved(self, layerIds):
    if self.layer.id() in layerIds:
      self.removedLayer.emit( self.layer.id() )
      self.removeLayerCatalog()

  @pyqtSlot( 'QgsLayerTreeNode', int, int )
  def willRemoveChildren(self, node, indexFrom, indexTo):
    if node == self.ltgCatalog: 
      return
    #
    removeNode = node.children()[ indexFrom ]
    if removeNode == self.ltgCatalog:
      self.enable( False )
      self.removedGroup.emit( self.layer.id() )

  @pyqtSlot()
  def destinationCrsChanged_MapUnitsChanged(self):
    self.extentsChanged()

  @pyqtSlot()
  def selectionChanged(self):
    if self.selectedImage:
      self._populateGroupCatalog()

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
      #
      isUrl = value.find('http://') == 0 or value.find('https://') == 0
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
      if not fieldSource is None and not fieldDate is None :
        isOk = True
        break
    #
    return { 'nameSource': fieldSource, 'nameDate': fieldDate } if isOk else None 

  def setLayerCatalog(self, layer, nameFiedlsCatalog):

    def setDicImages():
      fr = QgsFeatureRequest()
      fieldsRequest = [ self.nameFieldSource, self.nameFieldDate ]
      fr.setSubsetOfAttributes( fieldsRequest, layer.dataProvider().fields() )
      fr.setFlags( QgsFeatureRequest.NoGeometry )
      #
      self.dicImages  = {}
      it = self.layer.getFeatures( fr )
      f = QgsFeature()
      while it.nextFeature( f ):
        key = basename( f[ self.nameFieldSource ] )
        value = { 'source': f[ self.nameFieldSource ], 'date': f[ self.nameFieldDate ], 'id': f.id() }
        self.dicImages [key] = value
      it.close()

    self.layer = layer
    self.layerName = layer.name()
    self.featureImage = FeatureImage( layer, self.iface )
    self.nameFieldSource = nameFiedlsCatalog[ 'nameSource' ]
    self.nameFieldDate = nameFiedlsCatalog[ 'nameDate' ]
    setDicImages()
    self.settedLayer.emit( self.layer.id(), self.layer.name() )

  def removeLayerCatalog(self):
    self.featureImage.clear()
    self.dicImages.clear()
    self.featureImage = self.dicImages = None 
    #
    self.ltgRoot.removeChildNode( self.ltgCatalog )
    self.ltgCatalog = None
    #
    self.layer = self.nameFieldSource = self.nameFieldDate =  None

  def enable( self, on=True ):
    if on:
      self._setGroupCatalog()
      self.ltgCatalogName = self.ltgCatalog.name()
      self._connect( True )
      self.extentsChanged()
    else:
      self._connect( False )
    
  def enableZoom(self, on=True):
    self.zoomImage = on
    if on and self._setFeatureImage( self.ltv.currentLayer() ): 
      ss = { 'signal': self.canvas.extentsChanged , 'slot': self.extentsChanged }
      ss['signal'].disconnect( ss['slot'] )
      self.featureImage.zoom()
      ss['signal'].connect( ss['slot'] )
      self._populateGroupCatalog()

  def enableHighlight(self, on=True):
    self.highlightImage = on
    if on and self._setFeatureImage( self.ltv.currentLayer() ):
      self.featureImage.highlight( 3 )

  def enableSelected(self, on=True):
    self.selectedImage = on
    self._populateGroupCatalog()


class TableCatalogOTF(QObject):

  # signal that change checkBox of Layer, Select, Highlight, Zoom
  checkedState = pyqtSignal( str, str, int )

  def __init__(self):
    super( TableCatalogOTF, self ).__init__()
    self.tableWidget = QTableWidget()
    self._init()

  def _init(self):
    self.tableWidget.setWindowTitle("Catalog OTF")
    self.tableWidget.setSortingEnabled( False )
    msgtrans = QCoreApplication.translate("CatalogOTF", "Layer,Group,Total,Select,Highlight,Zoom")
    headers = msgtrans.split(',')
    self.tableWidget.setColumnCount( len( headers ) )
    self.tableWidget.setHorizontalHeaderLabels( headers )
    self.tableWidget.resizeColumnsToContents()
    #
    self.tableWidget.itemChanged.connect( self.itemChanged )

  def _getLayerID(self, row ):
    item = self.tableWidget.item( row, 0)
    return item.data( Qt.UserRole )

  def _getRowLayerID(self, layerID):
    for row in range( self.tableWidget.rowCount() ):
      if layerID == self._getLayerID( row ):
        return row
    return -1

  def setFlagsByCheck(self, row, check, columns):
    ff = ( lambda f: f | Qt.ItemIsEnabled ) if check == Qt.Checked else ( lambda f: f ^ Qt.ItemIsEnabled )
    for column in columns:
      item = self.tableWidget.item( row, column)
      item.setFlags( ff( item.flags() ) )

  def _changedText(self, layerID, name, column):
    row = self._getRowLayerID( layerID )
    if row != -1:
      ss = { 'signal': self.tableWidget.itemChanged , 'slot': self.itemChanged   }
      ss['signal'].disconnect( ss['slot'] )
      #
      item = self.tableWidget.item( row, column )
      item.setText( name )
      item.setToolTip( name )
      #
      ss['signal'].connect( ss['slot'] )

  @pyqtSlot( 'QTableWidgetItem' )
  def itemChanged( self, item ):
    checkBoxs = {
           0: 'checkBoxLayer',
           3: 'checkBoxSelect',
           4: 'checkBoxHighlight',
           5: 'checkBoxZoom'
         }
    column = item.column()
    if not column in ( checkBoxs.keys() ):
      return
    #
    row = item.row()
    check = item.checkState()
    if column == 0:
      ss = { 'signal': self.tableWidget.itemChanged , 'slot': self.itemChanged   }
      ss['signal'].disconnect( ss['slot'] )
      self.setFlagsByCheck( row, check, range(3, 6, 1) )
      ss['signal'].connect( ss['slot'] )
    #
    self.checkedState.emit( self._getLayerID( row ), checkBoxs[ column ], check )

  @pyqtSlot( str, str )
  def insertRow(self, layerID, layerName):
    ss = { 'signal': self.tableWidget.itemChanged , 'slot': self.itemChanged   }
    ss['signal'].disconnect( ss['slot'] )
    #
    row = self.tableWidget.rowCount()
    self.tableWidget.insertRow( row )
    #
    # "Layer", "Group", "Total", "Select", "Highlight", "Zoom" 
    #
    lenTexts = 3
    #
    column = 0 # Layer
    item = QTableWidgetItem( layerName )
    item.setFlags( Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsUserCheckable )
    item.setCheckState(Qt.Unchecked)
    item.setData( Qt.UserRole, layerID )
    item.setToolTip( layerName )
    self.tableWidget.setItem( row, column, item )
    #
    for column in range( 1, lenTexts ):
      item = QTableWidgetItem("None")
      item.setFlags( Qt.ItemIsSelectable | Qt.ItemIsEnabled )
      self.tableWidget.setItem( row, column, item )
    # Check's
    for column in range( lenTexts, self.tableWidget.columnCount() ):
      item = QTableWidgetItem()
      item.setFlags( Qt.ItemIsSelectable | Qt.ItemIsUserCheckable )
      item.setCheckState(Qt.Unchecked)
      self.tableWidget.setItem( row, column, item )
    #
    self.tableWidget.resizeColumnsToContents()
    ss['signal'].connect( ss['slot'] )

  @pyqtSlot( str )
  def removeRow(self, layerID):
    row = self._getRowLayerID( layerID )
    if row != -1:
      self.tableWidget.removeRow( row )

  @pyqtSlot( str, str )
  def changedNameLayer(self, layerID, name):
    self._changedText( layerID, name, 0 )
    self.tableWidget.resizeColumnsToContents()
    
  @pyqtSlot( str, str )
  def changedNameGroup(self, layerID, name=None):

    def uncheckedLayer():
      row = self._getRowLayerID( layerID )
      if row != -1:
        ss = { 'signal': self.tableWidget.itemChanged , 'slot': self.itemChanged   }
        ss['signal'].disconnect( ss['slot'] )
        self.tableWidget.item( row, 0 ).setCheckState( Qt.Unchecked )
        self.setFlagsByCheck( row, Qt.Unchecked, range(3, 6, 1) )
        ss['signal'].connect( ss['slot'] )
    #
    if name is None:
      name = "None"
      uncheckedLayer()
      self._changedText( layerID, name, 2 )
    self._changedText( layerID, name, 1 )
    self.tableWidget.resizeColumnsToContents()

  @pyqtSlot( str, str )
  def changedTotal(self, layerID, value):
    self._changedText( layerID, value, 2 )
    self.tableWidget.resizeColumnsToContents()

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
    self.tbl_cotf = TableCatalogOTF( )
    self.tbl_cotf.checkedState.connect( self.checkedState )
    #
    setupUi()

  @pyqtSlot( str, str, int )
  def checkedState(self, layerID, nameCheckBox, checkState):
    checkBoxs = {
          'checkBoxLayer': self.cotf[ layerID ].enable,
          'checkBoxSelect': self.cotf[ layerID ].enableSelected,
          'checkBoxHighlight': self.cotf[ layerID ].enableHighlight,
          'checkBoxZoom': self.cotf[ layerID ].enableZoom
    }
    on = True if checkState == Qt.Checked else False
    checkBoxs[ nameCheckBox ]( on )

  @pyqtSlot( str )
  def removeLayer(self, layerID):
    del self.cotf[ layerID ]

  @pyqtSlot()
  def findCatalogs(self):

    def checkTempDir():
      tempDir = QDir( WorkerPopulateGroup.TEMP_DIR )
      if not tempDir.exists():
        msgtrans1 = QCoreApplication.translate("CatalogOTF", "Created temporary directory '%s' for TMS")
        msgtrans2 = QCoreApplication.translate("CatalogOTF", "Not possible create temporary directory '%s' for TMS")
        isOk = tempDir.mkpath( WorkerPopulateGroup.TEMP_DIR )
        msgtrans = msgtrans1 if isOk else msgtrans2
        tempDir.setPath( WorkerPopulateGroup.TEMP_DIR )
        msg = msgtrans % tempDir.absolutePath()
        msgBar.pushMessage( NAME_PLUGIN, msg, QgsMessageBar.CRITICAL, 5 )
    
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
        self.cotf[ layerID ].setLayerCatalog( item, nameFiedlsCatalog )
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
