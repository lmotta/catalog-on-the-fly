<!-- IBAMA logo -->
[ibama_logo]: http://upload.wikimedia.org/wikipedia/commons/thumb/8/81/Logo_IBAMA.svg/150px-Logo_IBAMA.svg.png

![][ibama_logo]  
[Brazilian Institute of Environment and Renewable Natural Resources](http://www.ibama.gov.br)

# Catalog on the fly Plugin QGIS

Automatically adds  images that are in the catalog layer that intersect with the map area.

## Author
Luiz Motta

## Changelog
- 2015-05-04:
Create 'tmp' directory (case for Windows user)
Refactoring the multiprocess (use of QThread) 
- 2015-04-11:
Add thread for calculate images in group of catalog
- 2015-03-29:
Create plugin, refactory and rename 'addimage_by_extension.py' for 'catalogotf.py'
- 2015-03-18:
 Initial with console for script 'addimage_by_extension.py'
