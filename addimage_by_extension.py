#!/usr/local/bin/python
# -*- coding: utf-8 -*-

import urllib2
from datetime import datetime
from os.path import basename
from PyQt4.QtCore import ( QTimer, QFileInfo, Qt, QVariant, QPyNullVariant )
from qgis.gui import ( QgsHighlight, QgsMessageBar ) 
from qgis.core import (
  QgsProject, QGis,
  QgsMapLayerRegistry, QgsMapLayer,
  QgsFeature, QgsFeatureRequest, QgsGeometry,
  QgsCoordinateTransform,
  QgsRasterLayer, QgsRasterTransparency,
  QgsLayerTreeNode
)
from qgis.utils import ( iface )

class FileDebug:
  def __init__(self):
    self.nameFileDebug = "/home/lmotta/data/qgis_script_console/addimage_by_extension/addimage_by_extension.log"

  def write(self, line):
    print self.nameFileDebug
    f = open(self.nameFileDebug, 'a')
    f.write( "%s - %s\r\n" % ( line, str( datetime.now() ) ) )
    f.close()


class FeatureImage:

  def __init__(self, layer):
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
      self.msgError = "Geometry of feature (fid = %d) of layer ('%s') is invalid" % ( fid, self.layer.name() )
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
    self.layer.triggerRepaint()

  def highlight(self, second=0 ):
    if self.hl is None:
      return
    #
    self.hl.setWidth( 5 )
    self.hl.show()
    self.layer.triggerRepaint()
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
    self.layer.triggerRepaint()

  def msgError(self):
    return self.msgError


class CatalogOTF:

  def __init__(self):
    self.canvas = iface.mapCanvas()
    self.ltv = iface.layerTreeView()
    self.ltgRoot = QgsProject.instance().layerTreeRoot()
    self.msgBar = iface.messageBar()
    self.tempDir = "/tmp"
    self.layer = self.nameFieldSource = self.nameFieldDate =  None
    self.ltgCatalog = self.dicImages = None
    self.featureImage = None
    self.zoomImage = self.highlightImage = self.selectedImage = False
    #
    #self.fileDebug = FileDebug()

  def _connect(self, isConnect = True):
    ss = [
      { 'signal': self.canvas.extentsChanged , 'slot': self.onExtentsChangedMapCanvas },
      { 'signal': self.canvas.destinationCrsChanged, 'slot': self.onDestinationCrsChanged_MapUnitsChanged },
      { 'signal': self.canvas.selectionChanged, 'slot': self.onSelectionChanged },
      { 'signal': self.canvas.mapUnitsChanged, 'slot': self.onDestinationCrsChanged_MapUnitsChanged },
      { 'signal': self.ltv.activated , 'slot': self.onActivated   },
      { 'signal': QgsMapLayerRegistry.instance().layersWillBeRemoved , 'slot': self.onLayersWillBeRemoved   },
      { 'signal': self.ltgRoot.willRemoveChildren , 'slot': self.onWillRemoveChildren  }
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
      msg = "Image (%s) not in catalog layer ('%s')" % ( image, self.layer.name() )
      self.msgBar.pushMessage( msg, QgsMessageBar.CRITICAL, 4 )
      #
      return False
    #
    if not self.featureImage.setImage( image, self.dicImages ):
      self.msgBar.pushMessage( self.featureImage.msgError(), QgsMessageBar.CRITICAL, 4 )
      #
      return False
    #
    return True

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

    def getImagesByCanvas():
      images = []
      #
      rectLayer = self.layer.extent() if not self.selectedImage else self.layer.boundingBoxOfSelected()
      
      crsLayer = self.layer.crs()
      #
      crsCanvas = self.canvas.mapSettings().destinationCrs()
      # Transform
      ct = QgsCoordinateTransform( crsCanvas, crsLayer )
      rectCanvas = self.canvas.extent() if crsCanvas == crsLayer else ct.transform( self.canvas.extent() )
      #
      if not rectLayer.intersects( rectCanvas ):
        return [] 
      #
      fr = QgsFeatureRequest( rectCanvas )
      if self.selectedImage:
        fr.setFilterFids( self.layer.selectedFeaturesIds() )
      #fr.setSubsetOfAttributes( [ self.nameFieldSource ], self.layer.dataProvider().fields() )
      it = self.layer.getFeatures( fr ) 
      f = QgsFeature()
      while it.nextFeature( f ):
        images.append( basename( f[ self.nameFieldSource ] ) )
      #
      return images

    def addImages(images):

      def addImage(image):

        def _addImage():

          def setTransparence():

            def getTTVP():
              ts = QgsRasterTransparency.TransparentThreeValuePixel()
              ts.red = ts.green = ts.blue = 0.0
              ts.percentTransparent = 100.0
              return ts

            layerImage.renderer().rasterTransparency().setTransparentThreeValuePixelList( [ getTTVP() ] )

          layerImage = QgsRasterLayer( fileInfo.filePath(), fileInfo.baseName() )
          if not layerImage.isValid():
            return False
          else:
            # If not XML, set transparence
            fileName = fileInfo.fileName()
            extension = ".xml"
            idExt = fileName.rfind( extension )
            if idExt == -1 or len( fileName ) != ( idExt + len ( extension ) ):
              setTransparence()
            #
            layer = QgsMapLayerRegistry.instance().addMapLayer( layerImage, addToLegend=False )
            ltl = self.ltgCatalog.addLayer( layer )
            ltl.setVisible( Qt.Unchecked )
            name = "%s (%s)" % ( date.toString( "yyyy-MM-dd" ), image )
            ltl.setLayerName( name )
            return True

        def prepareFileTMS( url_tms ):

          def createLocalFile():
            response = urllib2.urlopen( url_tms )
            html = response.read()
            response.close()
            #
            fw = open( localName, 'w' )
            fw.write( html )
            fw.close()

          localName = "%s/%s" % ( self.tempDir, basename( url_tms ) )
          fileInfo = QFileInfo( localName )
          #
          if not fileInfo.exists():
            createLocalFile()
            fileInfo = QFileInfo( localName )
          #
          return fileInfo

        value = self.dicImages [image]
        source = value['source']
        date = value['date']
        fileInfo = prepareFileTMS( source ) if not source.find('http://') == -1 else QFileInfo( source )
        #
        return _addImage()

      def getSortedImages(images, v_reverse=False):
        images_date = map( lambda item: { '_image': item, 'date': self.dicImages [ item ]['date'] }, images )
        return sorted( images_date, key = lambda item: item['date'], reverse = v_reverse ) 

      l_error = []
      for item in getSortedImages( images, True ):
        if not addImage( item['_image'] ):
          l_error.append( item['_image'] )
      if len( l_error ) > 0:
        msg = "\n" .join( l_error )
        self.msgBar.pushMessage( "Images invalid:\n%s" % msg, QgsMessageBar.CRITICAL, 5 )
        del l_error[:]
      else:
        msg = "%s - Total %d" % ( self.ltgCatalog.name(), len( images ) )
        iface.mainWindow().statusBar().showMessage( msg )

    def setCurrentImage():
      sourceImage = self.dicImages[ self.featureImage.image() ]['source']
      ltlsImage = filter( lambda item: item.layer().source() == sourceImage, self.ltgCatalog.findLayers()  )
      if len( ltlsImage ) > 0:
        ltl = ltlsImage[0]
        layer = ltl.layer()
        self.ltv.setCurrentLayer( layer )
        if not cslc is None and cslc['source'] == layer.source():
          ltl.setVisible( cslc['visible'] ) 
    
    ss = { 'signal': self.ltv.activated , 'slot': self.onActivated   }
    ss['signal'].disconnect( ss['slot'] )
    #
    cslc = getCurrentStatusLayerCatalog()
    #
    self.ltgCatalog.removeAllChildren()
    #
    addImages( getImagesByCanvas() )
    #
    if not self.featureImage.image() is None:
      setCurrentImage() 
    #    
    ss['signal'].connect( ss['slot'] )

  def _setGroupCatalog(self):
    nameCatalogGroup = "%s - Catalog" % self.layer.name()
    self.ltgCatalog = self.ltgRoot.findGroup( nameCatalogGroup )
    if self.ltgCatalog is None:
      self.ltgCatalog = self.ltgRoot.addGroup( nameCatalogGroup )

  def onExtentsChangedMapCanvas(self):
    if self.layer is None:
      self.msgBar.pushMessage( "Need define layer catalog", QgsMessageBar.WARNING, 2 )
      return
    #
    self._populateGroupCatalog()
    #
    if self.highlightImage:
      self.featureImage.highlight( 3 )

  def onActivated(self, index ):
    if self.layer is None:
      self.msgBar.pushMessage( "Need define layer catalog", QgsMessageBar.WARNING, 2 )
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
      ss = { 'signal': self.canvas.extentsChanged , 'slot': self.onExtentsChangedMapCanvas }
      ss['signal'].disconnect( ss['slot'] )
      self.featureImage.zoom()
      ss['signal'].connect( ss['slot'] )
      self._populateGroupCatalog()
    #
    if self.highlightImage:
      self.featureImage.highlight( 3 )

  def onLayersWillBeRemoved(self, layerIds):
    if self.layer.id() in layerIds:
      self.removeLayerCatalog()

  def onWillRemoveChildren(self, node, indexFrom, indexTo):
    if node == self.ltgCatalog: 
      return
    #
    removeNode = node.children()[ indexFrom ]
    if removeNode == self.ltgCatalog:
      self.enable( False )
      return

  def onDestinationCrsChanged_MapUnitsChanged(self):
    self.onExtentsChangedMapCanvas()

  def onSelectionChanged(self):
    if self.selectedImage:
      self._populateGroupCatalog()

  def getNameFieldsCatalog(self, layer):

    def getFirstFeature():
      f = QgsFeature()
      #
      fr = QgsFeatureRequest( 0 )
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
      if value.find('http://') == 0:
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

    if layer.type() != QgsMapLayer.VectorLayer or layer.geometryType() != QGis.Polygon:
      return None
    #
    firstFeature = getFirstFeature()
    if firstFeature is None:
      return None
    #
    fieldAddress = None
    fieldDate = None
    isOk = False
    for item in layer.pendingFields().toList():
      if item.type() == QVariant.String:
        if fieldAddress is None and hasAddress( firstFeature, layer.fieldNameIndex( item.name() ) ):
          fieldAddress = item.name()
      elif item.type() == QVariant.Date:
        if fieldDate is None and hasDate( firstFeature, layer.fieldNameIndex( item.name() ) ):
          fieldDate = item.name()
      if not fieldAddress is None and not fieldDate is None :
        isOk = True
        break
    #
    return { 'nameAddress': fieldAddress, 'nameDate': fieldDate } if isOk else None 

  def setLayerCatalog(self, layer, nameFieldSource, nameFieldDate ):

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
    self.featureImage = FeatureImage( layer )
    self.nameFieldSource = nameFieldSource
    self.nameFieldDate = nameFieldDate
    setDicImages()

  def removeLayerCatalog(self):
    self.featureImage.clear()
    self.dicImages.clear()
    self.featureImage = self.dicImages = None 
    #
    self.ltgRoot.removeChildNode( self.ltgCatalog )
    self.ltgCatalog = None
    #
    self.layer = self.nameFieldSource = self.nameFieldDate =  None

  def enable( self, onEnabled=True ):
    self._connect( onEnabled )
    if onEnabled:
      self._setGroupCatalog()
      self.onExtentsChangedMapCanvas()

  def enableZoomImage(self, on=True):
    self.zoomImage = on
    if on and self._setFeatureImage( self.ltv.currentLayer() ): 
      ss = { 'signal': self.canvas.extentsChanged , 'slot': self.onExtentsChangedMapCanvas }
      ss['signal'].disconnect( ss['slot'] )
      self.featureImage.zoom()
      ss['signal'].connect( ss['slot'] )
      self._populateGroupCatalog()

  def enableHighlightImage(self, on=True):
    self.highlightImage = on
    if on and self._setFeatureImage( self.ltv.currentLayer() ):
      self.featureImage.highlight( 3 )

  def enableSelectedImage(self, on=True):
    self.selectedImage = on
    self._populateGroupCatalog()


def init():
  layer = iface.mapCanvas().currentLayer()
  if layer is None:
    print "Selecione o layer de catalogo"
    return None
  if not layer.type() == QgsMapLayer.VectorLayer:
    print u"Layer selecionado não é do tipo VETOR, selecione o layer de catalogo"
    return None
  cotf = CatalogOTF(); cotf.setLayerCatalog( layer, "address", "data" )
  cotf.enable()
  #
  return cotf


#
#
"""
execfile(u'/home/lmotta/data/qgis_script_console/addimage_by_extension/addimage_by_extension.py'.encode('UTF-8')); cotf = init()
cotf.enableHighlightImage(); cotf.enableZoomImage()
cotf.enableSelectedImage()
cotf.enable( False ); cotf.removeLayerCatalog(); cotf = None

execfile(u'/home/lmotta/data/qgis_script_console/addimage_by_extension/addimage_by_extension.py'.encode('UTF-8'));
layer = iface.mapCanvas().currentLayer(); cotf = CatalogOTF()
fieldsName = cotf.getNameFieldsCatalog( layer )
"""