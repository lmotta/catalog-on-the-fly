#
import urllib2
from os.path import basename

from PyQt4.QtCore import *

from qgis.gui import *
from qgis.core import *
from qgis import utils

class HighlightFeature:
  def __init__(self, layer):
    self.layer = layer
    self.msgBar = utils.iface.messageBar()
    self.hl = self.geom = self.width = None
  #
  def _changeWidth(self):
    if self.hl is None:
      return
    self.hl.setWidth( self.width )
    self.hl.update()
  #
  def _getGeometry(self, fid):
    fr = QgsFeatureRequest( fid )
    fr.setSubsetOfAttributes( [], self.layer.dataProvider().fields() )
    it = self.layer.getFeatures( fr )
    feat = QgsFeature()
    isOk = it.nextFeature( feat )
    it.close()
    #
    return QgsGeometry( feat.geometry() ) if isOk else None
  #
  def highlight(self, fid, second=0 ):
    self.geom = self.calcGeometry( fid )
    if self.geom is None:
      return
    #
    if not self.hl is None:
      del self.hl
    #
    self.hl = QgsHighlight( utils.iface.mapCanvas(), self.geom, self.layer )
    if second <> 0:
      self.width = 6
      self._changeWidth()        
      self.width = 1
      QTimer.singleShot( second * 1000, self._changeWidth )
  #
  def geometry(self):
    return self.geom
  #
  def calcGeometry(self, fid):
    geom = self._getGeometry( fid )
    if geom is None:
      msg = "Feature (fid = %d) of layer ('%s') is invalid" % ( fid, self.layer.name() )
      self.msgBar.pushMessage( msg, QgsMessageBar.CRITICAL, 4 )
      return None
    else:
      return geom
  #
  def clean(self):
    if not self.hl is None:
      del self.hl
      self.hl = None
      self.geom = None
#
class CatalogOTF:
  def __init__(self):
    self.canvas = utils.iface.mapCanvas()
    self.layer = self.nameFieldSource = self.nameFieldDate =  None
    self.ltgCatalog = self.dicImage = None
    self.hlFeature = self.currentImage= None
    self.zoomImage = False
    self.highlightImage = False
    self.msgBar = utils.iface.messageBar()
    self.tempDir = "/tmp"
  #
  def _connect(self, isConnect = True):
    ltv = utils.iface.layerTreeView()
    signal_slot = [
      { 'signal': self.canvas.extentsChanged , 'slot': self.onExtentsChangedMapCanvas },
      { 'signal': self.canvas.destinationCrsChanged, 'slot': self.onDestinationCrsChanged_MapUnitsChanged },
      { 'signal': self.canvas.mapUnitsChanged, 'slot': self.onDestinationCrsChanged_MapUnitsChanged },
      { 'signal': ltv.currentLayerChanged , 'slot': self.onCurrentLayerChanged  }
    ]
    if isConnect:
      for item in signal_slot:
        item['signal'].connect( item['slot'] )  
    else:
      for item in signal_slot:
        item['signal'].disconnect( item['slot'] )  
  #
  def onExtentsChangedMapCanvas(self):
    def getImagesByCanvas():
      images = []
      #
      rectLayer = self.layer.extent()
      crsLayer = self.layer.crs()
      #
      crsCanvas = self.canvas.mapSettings().destinationCrs()
      # Transform
      ct = QgsCoordinateTransform( crsCanvas, crsLayer )
      rectCanvas = self.canvas.extent() if crsCanvas == crsLayer else ct.transform( self.canvas.extent() )
      #
      if not rectLayer.intersects( rectCanvas ):
        return images 
      #
      fr = QgsFeatureRequest( rectCanvas )
      #fr.setSubsetOfAttributes( [ self.nameFieldSource ], self.layer.dataProvider().fields() )
      it = self.layer.getFeatures( fr )
      f = QgsFeature()
      while it.nextFeature( f ):
        images.append( basename( f[ self.nameFieldSource ] ) )
      #
      return images
    #
    def addImages(images):
      def addImage(image):
        def _addImage():
          def setTransparence():
            def getTTVP():
              ts = QgsRasterTransparency.TransparentThreeValuePixel()
              ts.red = ts.green = ts.blue = 0.0
              ts.percentTransparent = 100.0
              return ts
            #
            layerImage.renderer().rasterTransparency().setTransparentThreeValuePixelList( [ getTTVP() ] )
          #
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
        #
        def prepareFileTMS( url_tms ):
          def createLocalFile():
            response = urllib2.urlopen( url_tms )
            html = response.read()
            response.close()
            #
            fw = open( localName, 'w' )
            fw.write( html )
            fw.close()
          #
          localName = "%s/%s" % ( self.tempDir, basename( url_tms ) )
          fileInfo = QFileInfo( localName )
          #
          if not fileInfo.exists():
            createLocalFile()
            fileInfo = QFileInfo( localName )
          #
          return fileInfo
        #
        value = self.dicImage [image]
        source = value['source']
        date = value['date']
        fileInfo = prepareFileTMS( source ) if not source.find('http://') == -1 else QFileInfo( source )
        #
        return _addImage()
      #
      def getSortedImages(images, v_reverse=False):
        images_date = map( lambda item: { 'image': item, 'date': self.dicImage [ item ]['date'] }, images )
        return sorted( images_date, key = lambda item: item['date'], reverse = v_reverse ) 
      #
      l_error = []
      for item in getSortedImages( images, True ):
        if not addImage( item['image'] ):
          l_error.append( item['image'] )
      if len( l_error ) > 0:
        msg = "\n" .join( l_error )
        self.msgBar.pushMessage( "Images invalid:\n%s" % msg, QgsMessageBar.CRITICAL, 5 )
        del l_error[:]
      else:
        msg = "%s - Total %d" % ( self.ltgCatalog.name(), len( images ) )
        utils.iface.mainWindow().statusBar().showMessage( msg )
    #
    def setCurrentImage( ):
      sourceImage = self.dicImage[ self.currentImage ]['source']
      ltlsImage = filter( lambda item: item.layer().source() == sourceImage, self.ltgCatalog.findLayers()  )
      if len( ltlsImage ) > 0:
        ltv.setCurrentLayer( ltlsImage[0].layer() )
        if self.highlightImage:
          self.hlFeature.highlight( self.dicImage [ self.currentImage ]['id'], 3 )
      else:
        self.hlFeature.clean()
    #
    if self.layer is None:
      self.msgBar.pushMessage( "Need define layer catalog", QgsMessageBar.WARNING, 2 )
      return
    #
    ltv = utils.iface.layerTreeView()
    #
    prevFlag = self.canvas.renderFlag()
    self.canvas.setRenderFlag( False )
    signal_slot = { 'signal': ltv.currentLayerChanged , 'slot': self.onCurrentLayerChanged }
    signal_slot['signal'].disconnect( signal_slot['slot'] )
    #
    self.ltgCatalog.removeAllChildren()
    #
    addImages( getImagesByCanvas() )
    #
    if not self.currentImage is None:
      setCurrentImage() 
    #    
    signal_slot['signal'].connect( signal_slot['slot'] )
    self.canvas.setRenderFlag( prevFlag )
    self.canvas.refresh()
  #
  def onCurrentLayerChanged(self, rasterLayer):
    if not self.highlightImage and not self.zoomImage :
      return
    #
    self.currentImage = None
    #
    if rasterLayer is None or \
       rasterLayer.type() != QgsMapLayer.RasterLayer or \
       self.ltgCatalog is None or \
       self.ltgCatalog.findLayer( rasterLayer.id() ) is None:
      #
      self.hlFeature.clean()
      return
    #
    image = basename( rasterLayer.source() )
    if not image in self.dicImage .keys():
      msg = "Image (%s) not in catalog layer ('%s')" % ( image, self.layer.name() )
      self.msgBar.pushMessage( msg, QgsMessageBar.CRITICAL, 4 )
      return
    #
    self.currentImage = image
    #
    if self.highlightImage:
      self.hlFeature.highlight( self.dicImage[ self.currentImage ]['id'], 3 )
    #
    if self.zoomImage:
      geom = self.hlFeature.geometry()
      #
      if geom is None:
        geom = self.hlFeature.calcGeometry( self.dicImage [ self.currentImage ]['id'] )
        if geom is None:
          return
      #
      self.canvas.setExtent( geom.boundingBox() )
    #
  #
  def onDestinationCrsChanged_MapUnitsChanged(self):
    self.onExtentsChangedMapCanvas()
  #
  def setLayerCatalog(self, layer, nameFieldSource, nameFieldDate ):
    def setDicSourceDate():
      fr = QgsFeatureRequest()
      fieldsRequest = [ self.nameFieldSource, self.nameFieldDate ]
      fr.setSubsetOfAttributes( fieldsRequest, layer.dataProvider().fields() )
      fr.setFlags( QgsFeatureRequest.NoGeometry )
      #
      self.dicImage  = {}
      it = self.layer.getFeatures( fr )
      f = QgsFeature()
      while it.nextFeature( f ):
        key = basename( f[ self.nameFieldSource ] )
        value = { 'source': f[ self.nameFieldSource ], 'date': f[ self.nameFieldDate ], 'id': f.id() }
        self.dicImage [key] = value
      it.close()
    #
    self.layer = layer
    self.hlFeature = HighlightFeature( layer )
    self.nameFieldSource = nameFieldSource
    self.nameFieldDate = nameFieldDate
    setDicSourceDate()
  #
  def enable( self, onEnabled=True ):
    def setGroupCatalog():
      nameCatalogGroup = "%s - Catalog" % self.layer.name()
      root = QgsProject.instance().layerTreeRoot()
      self.ltgCatalog = root.findGroup( nameCatalogGroup )
      if self.ltgCatalog is None:
        self.ltgCatalog = root.addGroup( nameCatalogGroup )
    #
    self._connect( onEnabled )
    if onEnabled:
      setGroupCatalog()
      self.onExtentsChangedMapCanvas()
    else:
      self.hlFeature.clean()
      self.ltgCatalog = None
  #
  def onZoomImage(self, on=True):
    self.zoomImage = on
  #
  def onHighlightImage(self, on=True):
    self.highlightImage = on
    if not on:
      self.hlFeature.clean()
  #
#
def init():
  layer = iface.mapCanvas().currentLayer()
  if layer is None:
    print "Selecione o layer de catalogo"
    return None
  cotf = CatalogOTF(); cotf.setLayerCatalog( layer, "address", "data" )
  cotf.enable()
  #
  return cotf
#
#
"""
execfile(u'/home/lmotta/data/qgis_script_console/addimage_by_extension.py'.encode('UTF-8')); cotf = init()
cotf.onHighlightImage(); cotf.onZoomImage()
cotf.enable( False ); del cotf; cotf = None
"""