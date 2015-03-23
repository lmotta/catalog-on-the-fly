#!/usr/local/bin/python
# -*- coding: utf-8 -*-

import urllib2
from datetime import datetime
from os.path import basename
from PyQt4.QtCore import ( QTimer, QFileInfo, Qt )
from qgis.gui import ( QgsHighlight, QgsMessageBar ) 
from qgis.core import (
  QgsProject,
  QgsMapLayerRegistry, QgsMapLayer,
  QgsFeature, QgsFeatureRequest, QgsGeometry,
  QgsCoordinateTransform,
  QgsRasterLayer, QgsRasterTransparency,
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
    self._image = self.geom = self.hl = self.msgError = None
    self.canvas = iface.mapCanvas()

  def _getGeometry(self, fid):
    fr = QgsFeatureRequest( fid )
    fr.setSubsetOfAttributes( [], self.layer.dataProvider().fields() )
    it = self.layer.getFeatures( fr )
    feat = QgsFeature()
    isOk = it.nextFeature( feat )
    it.close()

    return QgsGeometry( feat.geometry() ) if isOk else None

  def setImage(self, image=None, dicImages=None):
    if image is None and dicImages is None:
      self._image = None
      del self.geom
      self.geom = None
      return True 
    #
    if self._image == image:
      return True
    #
    fid = dicImages[ image ]['id']
    geom = self._getGeometry( fid )
    if geom is None:
      self.msgError = "Feature (fid = %d) of layer ('%s') is invalid" % ( fid, self.layer.name() )
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
      { 'signal': self.ltv.activated , 'slot': self.onActivated   }
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
        self.ltv.setCurrentLayer( ltlsImage[0].layer() )
    
    ss = { 'signal': self.ltv.activated , 'slot': self.onActivated   }
    ss['signal'].disconnect( ss['slot'] )
    #
    #self.fileDebug.write("_populateGroupCatalog")
    self.ltgCatalog.removeAllChildren()
    #
    addImages( getImagesByCanvas() )
    #
    if not self.featureImage.image() is None:
      setCurrentImage() 
    #    
    ss['signal'].connect( ss['slot'] )

  def onExtentsChangedMapCanvas(self):
    if self.layer is None:
      self.msgBar.pushMessage( "Need define layer catalog", QgsMessageBar.WARNING, 2 )
      return
    #
    self._populateGroupCatalog()

  def onActivated(self, index ):
    if self.layer is None:
      self.msgBar.pushMessage( "Need define layer catalog", QgsMessageBar.WARNING, 2 )
      return
    #
    layer = self.ltv.currentLayer()
    #
    if layer is None or not self.highlightImage and not self.zoomImage :
      return
    #
    self.featureImage.setImage() # Clear
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

  def onDestinationCrsChanged_MapUnitsChanged(self):
    self.onExtentsChangedMapCanvas()

  def onSelectionChanged(self):
    if self.selectedImage:
      self._populateGroupCatalog()

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

  def enable( self, onEnabled=True ):

    def setGroupCatalog():
      nameCatalogGroup = "%s - Catalog" % self.layer.name()
      root = QgsProject.instance().layerTreeRoot()
      self.ltgCatalog = root.findGroup( nameCatalogGroup )
      if self.ltgCatalog is None:
        self.ltgCatalog = root.addGroup( nameCatalogGroup )

    self._connect( onEnabled )
    if onEnabled:
      setGroupCatalog()
      self.onExtentsChangedMapCanvas()

  def onZoomImage(self, on=True):
    self.zoomImage = on
    if on and self._setFeatureImage( self.ltv.currentLayer() ): 
      ss = { 'signal': self.canvas.extentsChanged , 'slot': self.onExtentsChangedMapCanvas }
      ss['signal'].disconnect( ss['slot'] )
      self.featureImage.zoom()
      ss['signal'].connect( ss['slot'] )
      self._populateGroupCatalog()

  def onHighlightImage(self, on=True):
    self.highlightImage = on
    if on and self._setFeatureImage( self.ltv.currentLayer() ):
      self.featureImage.highlight( 3 )

  def onSelectedImage(self, on=True):
    self.selectedImage = on
    self._populateGroupCatalog()

def init():
  layer = iface.mapCanvas().currentLayer()
  if layer is None:
    print "Selecione o layer de catalogo"
    return None
  if layer.type() == QgsMapLayer.RasterLayer:
    print u"Layer selecione é do tipo RASTER, selecione o layer de catalogo"
    return None
  cotf = CatalogOTF(); cotf.setLayerCatalog( layer, "address", "data" )
  cotf.enable()
  #
  return cotf
#
#
"""
execfile(u'/home/lmotta/data/qgis_script_console/addimage_by_extension/addimage_by_extension.py'.encode('UTF-8')); cotf = init()
cotf.onHighlightImage(); cotf.onZoomImage()
cotf.onSelectedImage()
cotf.enable( False ); del cotf; cotf = None
"""