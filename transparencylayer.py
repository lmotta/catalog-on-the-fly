# -*- coding: utf-8 -*-
"""
/***************************************************************************
Name                 : Transparency Layer
Description          : Set transparency in layer.
Date                 : February, 2019
copyright            : (C) 2019 by Luiz Motta
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
__date__ = '2019-02-11'
__copyright__ = '(C) 2019, Luiz Motta'
__revision__ = '$Format:%H$'

from qgis.core import QgsRasterTransparency, QgsMultiBandColorRenderer, QgsSingleBandGrayRenderer

class RasterTransparency():
    @staticmethod
    def setTransparency(raster):
        renderer = raster.renderer()
        tvp, setTransparent = None, None
        if isinstance( renderer, QgsSingleBandGrayRenderer ):
            tvp = QgsRasterTransparency.TransparentSingleValuePixel()
            setTransparent = renderer.rasterTransparency().setTransparentSingleValuePixelList
        elif isinstance( renderer, QgsMultiBandColorRenderer ):
            tvp = QgsRasterTransparency.TransparentThreeValuePixel()
            tvp.percentTransparent = 100.0
            setTransparent = renderer.rasterTransparency().setTransparentThreeValuePixelList
        else:
            return
        tvp.percentTransparent = 100.0
        setTransparent( [ tvp ] )
        raster.triggerRepaint()
