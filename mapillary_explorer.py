# -*- coding: utf-8 -*-
"""
/***************************************************************************
 go2mapillary
                                 A QGIS plugin
 mapillary explorer
                              -------------------
        begin                : 2016-01-21
        git sha              : $Format:%H$
        copyright            : (C) 2016 by enrico ferreguti
        email                : enricofer@gmail.com
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
from qgis.PyQt.QtCore import QObject, QSettings, QTranslator, qVersion, QCoreApplication, Qt
from qgis.PyQt.QtWidgets import QAction, QDockWidget
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.PyQt.QtNetwork import QNetworkProxy

from qgis.core import (QgsExpressionContextUtils,
                       QgsNetworkAccessManager,
                       QgsProject,
                       QgsGeometry,
                       QgsFeature,
                       QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform,
                       QgsPoint,
                       QgsPointXY,
                       QgsVectorLayer,
                       QgsRasterLayer,
                       QgsDataSourceUri,
                       QgsExpression,
                       QgsFeatureRequest,
                       QgsWkbTypes,)

from qgis.gui import QgsRubberBand,QgsVertexMarker

#from qgis.utils import *
# Initialize Qt resources from file resources.py
#from .res import resources

# Import the code for the DockWidget
from .mapillary_explorer_dockwidget import go2mapillaryDockWidget
from .mapillary_viewer import mapillaryViewer
from .mapillary_filter import mapillaryFilter
from .mapillary_settings import mapillarySettings
from .mapillary_form import mapillaryForm
from .mapillary_coverage import mapillary_coverage, LAYER_LEVELS
from .mapillary_image_info import mapillaryImageInfo
from .identifygeometry import IdentifyGeometry
from .geojson_request import geojson_request

import os.path
import json



class mapillary_cursor():

    def transformToWGS84(self, pPoint):
        # transformation from the current SRS to WGS84
        crcMappaCorrente = self.iface.mapCanvas().mapSettings().destinationCrs()  # get current crs
        crsSrc = crcMappaCorrente
        crsDest = QgsCoordinateReferenceSystem(4326)  # WGS 84
        xform = QgsCoordinateTransform(crsSrc, crsDest, QgsProject.instance())
        return xform.transform(pPoint)  # forward transformation: src -> dest

    def transformToCurrentSRS(self, pPoint):
        # transformation from the current SRS to WGS84
        crcMappaCorrente = self.iface.mapCanvas().mapSettings().destinationCrs()  # get current crs
        crsDest = crcMappaCorrente
        crsSrc = QgsCoordinateReferenceSystem(4326)  # WGS 84
        xform = QgsCoordinateTransform(crsSrc, crsDest, QgsProject.instance())
        return xform.transform(pPoint)  # forward transformation: src -> dest

    def __init__(self,parentInstance):
        self.parentInstance = parentInstance
        self.iface = parentInstance.iface
        self.mapCanvas = self.iface.mapCanvas()
        self.lineOfSight = QgsRubberBand(self.mapCanvas, QgsWkbTypes.LineGeometry)
        self.sightDirection = QgsRubberBand(self.mapCanvas, QgsWkbTypes.LineGeometry)
        self.pointOfView = QgsVertexMarker(self.mapCanvas)
        self.cursor = QgsVertexMarker(self.mapCanvas)
        self.sightDirection.setColor(QColor("#36AF6C"))
        self.lineOfSight.setColor(QColor("#36AF6C"))
        self.pointOfView.setColor(QColor("#36AF6C"))
        self.cursor.setColor(QColor("#36AF6C"))
        self.lineOfSight.setWidth(2)
        self.sightDirection.setWidth(1)
        self.sightDirection.setLineStyle(Qt.DashLine)
        self.pointOfView.setIconType(QgsRubberBand.ICON_CIRCLE)
        self.cursor.setIconType(QgsRubberBand.ICON_CIRCLE)
        self.pointOfView.setIconSize(20)
        self.cursor.setIconSize(20)
        self.cursor.setPenWidth(2)
        self.pointOfView.setPenWidth(2)
        self.samplesLayer = QgsVectorLayer("Point?crs=epsg:4326&field=id:integer&field=type:string(10)&field=cat:string(20)&field=key:string(20)&field=note:string(100)&field=img_coords:string(100)&index=yes","Mapillary samples","memory")
        self.samplesLayer.loadNamedStyle(os.path.join(os.path.dirname(__file__), "res", "mapillary_samples.qml"))
        self.samplesLayer.featureAdded.connect(self.newAddedFeat)


    def draw(self,pointOfView_coords,orig_pointOfView_coords,cursor_coords,endOfSight_coords):
        self.cursor.show()
        self.pointOfView.show()
        self.lineOfSight.reset()
        self.sightDirection.reset()
        pointOfView = self.transformToCurrentSRS(QgsPointXY(pointOfView_coords[1],pointOfView_coords[0]))
        cursor = self.transformToCurrentSRS(QgsPointXY(cursor_coords[1],cursor_coords[0]))
        endOfSight = self.transformToCurrentSRS(QgsPointXY(endOfSight_coords[1],endOfSight_coords[0]))
        #print ('cursor',cursor_coords[0],cursor_coords[1],cursor.x(),cursor.y())
        self.pointOfView.setCenter (pointOfView)
        self.cursor.setCenter (cursor)
        self.lineOfSight.addPoint(pointOfView)
        self.lineOfSight.addPoint(cursor)
        self.sightDirection.addPoint(pointOfView)
        self.sightDirection.addPoint(endOfSight)
        self.cursor.updatePosition()

    def delete(self):
        self.cursor.hide()
        self.pointOfView.hide()
        self.lineOfSight.reset()
        self.sightDirection.reset()

    def sample(self, type, id,key,sample_coords, img_coords=None):
        self.samplesLayer.startEditing()
        samplePoint = QgsPointXY(sample_coords[1],sample_coords[0])
        #sampleDevicePoint = self.iface.mapCanvas().getCoordinateTransform().transform(samplePoint.x(),samplePoint.y())
        if not QgsProject.instance().mapLayer(self.samplesLayer.id()):
            QgsProject.instance().addMapLayer(self.samplesLayer)
            self.parentInstance.reorderLegendInterface()
        sampleFeat = QgsFeature(self.samplesLayer.fields())
        sampleFeat['type'] = type
        sampleFeat['id'] = id
        sampleFeat['key'] = key
        if img_coords:
            sampleFeat['img_coords'] = img_coords
        sampleFeat.setGeometry(QgsGeometry.fromPointXY(samplePoint))
        #self.samplesLayer.dataProvider().addFeatures([sampleFeat])
        self.samplesLayer.addFeature(sampleFeat)
        self.samplesLayer.commitChanges()

    def newAddedFeat(self,featId):
        if featId < 0:
            return
        print ("added", featId)
        self.samplesLayer.triggerRepaint()
        if self.parentInstance.sample_settings.settings['auto_open_form']:
            newFeat = self.samplesLayer.getFeature(featId)
            print (newFeat)
            self.parentInstance.samples_form.open(newFeat)

    def getSamplesList(self):
        samples = []
        id = 1
        for feat in self.samplesLayer.getFeatures():
            samples.append({
                "id":id,
                "latLon":{
                    'lat':feat.geometry().asPoint().y(),
                    'lon':feat.geometry().asPoint().x(),
                }
            })

    def restoreTags(self,key):
        exp = QgsExpression('"type" = \'tag\' and "key" = \'%s\'' % key)
        print (exp)
        tags = []
        for feat in self.samplesLayer.getFeatures(QgsFeatureRequest(exp)):
            if feat['cat']:
                color = self.parentInstance.sample_settings.settings['categories'][feat['cat']]
            else:
                color = '#ffffff'
            tags.append({
                'id': feat['id'],
                'key': feat['key'],
                'note': feat['note'],
                'cat': feat['cat'],
                'color': color,
                'geometry': json.loads(feat['img_coords'])
            })
        print (tags)
        return tags

class go2mapillary:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        self.canvas = iface.mapCanvas()

        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'go2mapillary_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&go2mapillary')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'go2mapillary')
        self.toolbar.setObjectName(u'go2mapillary')

        #print "** INITIALIZING go2mapillary"

        self.pluginIsActive = False
        self.dockwidget = None


    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('go2mapillary', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action


    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = os.path.join(self.plugin_dir,'res','icon.png')
        self.add_action(
            icon_path,
            text=self.tr(u'go2mapillary'),
            callback=self.run,
            parent=self.iface.mainWindow())

        self.dlg = go2mapillaryDockWidget()

        self.dockwidget=QDockWidget("go2mapillary" , self.iface.mainWindow() )
        self.dockwidget.setObjectName("go2mapillary")
        self.dockwidget.setWidget(self.dlg)
        self.dlg.webView.page().setNetworkAccessManager(QgsNetworkAccessManager.instance())
        self.dlg.webView.page().mainFrame().setScrollBarPolicy(Qt.Vertical, Qt.ScrollBarAlwaysOff)
        self.dlg.webView.page().mainFrame().setScrollBarPolicy(Qt.Horizontal, Qt.ScrollBarAlwaysOff)
        self.canvas.mapToolSet.connect(self.toggleViewer)
        self.viewer = mapillaryViewer(self)
        self.viewer.messageArrived.connect(self.viewerConnection)
        self.viewer.openFilter.connect(self.filter_images_func)
        #QgsExpressionContextUtils.setGlobalVariable( "mapillaryCurrentKey","noKey")
        QgsExpressionContextUtils.removeGlobalVariable("mapillaryCurrentKey")
        self.mapSelectionTool = None
        self.coverage = mapillary_coverage(self)
        self.filterDialog = mapillaryFilter(self)
        self.filterAction_images = QAction(QIcon(icon_path), 'filter mapillary coverage', self.iface.mainWindow())
        self.filterAction_sequences = QAction(QIcon(icon_path), 'filter mapillary coverage', self.iface.mainWindow())
        self.filterAction_overview = QAction(QIcon(icon_path), 'filter mapillary coverage', self.iface.mainWindow())
        self.filterAction_images.triggered.connect(self.filter_images_func)
        self.filterAction_sequences.triggered.connect(self.filter_sequences_func)
        self.filterAction_overview.triggered.connect(self.filter_overview_func)
        self.sampleLocation = mapillary_cursor(self)
        self.sample_settings = mapillarySettings(self)
        self.samples_form = mapillaryForm(self)


    #--------------------------------------------------------------------------



    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""

        self.coverage.removeLevels()
        self.sampleLocation.delete()
        self.removeMapillaryLayerGroup()

        try:
            QgsProject.instance().removeMapLayer(self.sampleLocation.samplesLayer.id())
        except:
            pass

        try:
            self.canvas.extentsChanged.disconnect(self.mapChanged)
        except:
            pass

        try:
            self.canvas.mapCanvasRefreshed.disconnect(self.mapRefreshed)
        except:
            pass

        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&go2mapillary'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar
        self.dockwidget.hide()

    def filter_images_func(self):
        self.filterDialog.show('images')

    def filter_sequences_func(self):
        self.filterDialog.show('sequences')

    def filter_overview_func(self):
        self.filterDialog.show("overview")

    def toggleViewer(self,mapTool):
        if mapTool != self.mapSelectionTool:
            self.viewer.disable()

    def viewerConnection(self, message):
        print (self.sample_settings)
        #print (message)
        if message:
            if message["transport"] == "move_cursor":
                print('moving',message)
                self.sampleLocation.draw(message["pov"],message["orig_pov"],message["cursor"],message["endOfSight"])
            if message["transport"] == "disable_cursor":
                print('deleting')
                self.sampleLocation.delete()
            if message["transport"] == "create_marker":
                print('creating')
                self.sampleLocation.sample("marker",message['id'],message['key'],message['markerPos'])

            if message["transport"] == "view":
                self.sampleLocation.delete()
                self.currentLocation = message
                try:
                    QgsExpressionContextUtils.setLayerVariable(self.coverage.imagesLayer, "mapillaryCurrentKey", self.currentLocation['key'])
                    self.coverage.imagesLayer.triggerRepaint()
                except:
                    pass
            if message["transport"] == "focusOn":
                self.sampleLocation.delete()
                self.viewer.enable()
                self.canvas.setMapTool(self.mapSelectionTool)
            if message["transport"] == "open_settings":
                self.sample_settings.open()
            if message["transport"] == "image_info":
                mapillaryImageInfo.openKey(self,message["key"])
            if message["transport"] == "store_tag":
                print (message)
                self.sampleLocation.sample("tag", message['id'], message['key'], message['loc'], json.dumps(message['geometry']))


    def mapChanged(self):
        self.canvas.mapCanvasRefreshed.connect(self.mapRefreshed)

    def mapRefreshed(self):
        try:
            self.canvas.mapCanvasRefreshed.disconnect(self.mapRefreshed)
        except:
            pass

        enabledLevels = self.coverage.update_coverage()
        self.reorderLegendInterface()

        for level,layer in enabledLevels.items():
            if not (level == 'sequences' and 'images' in enabledLevels.keys()):
                self.mapSelectionTool = IdentifyGeometry(self.canvas, layer)
                self.mapSelectionTool.geomIdentified.connect(getattr(self,'changeMapillary_'+level))



    def run(self):
        """Run method that loads and starts the plugin"""

        if not self.pluginIsActive:
            self.pluginIsActive = True

            # show the dockwidget
            # TODO: fix to allow choice of dock location
            self.iface.addDockWidget(Qt.LeftDockWidgetArea, self.dockwidget)
            self.dockwidget.show()
            #self.setupLayer('')
            self.canvas.extentsChanged.connect(self.mapChanged)
            self.mapRefreshed()
            self.canvas.setMapTool(self.mapSelectionTool)

        else:
            # toggle show/hide the widget
            if self.dockwidget.isVisible():
                self.dockwidget.hide()
                self.pluginIsActive = False
                self.coverage.removeLevels()
                self.canvas.extentsChanged.disconnect(self.mapChanged)
                #self.removeMapillaryLayerGroup()
                self.reorderLegendInterface()
            else:
                self.dockwidget.show()
                self.canvas.setMapTool(self.mapSelectionTool)
                self.canvas.extentsChanged.connect(self.mapChanged)
                self.mapRefreshed()

    def changeMapillary_images(self, feature):
        #print("changeMapillary_images")
        self.viewer.openLocation(feature['key'])
        QgsExpressionContextUtils.setLayerVariable(self.coverage.imagesLayer, "mapillaryCurrentKey", feature['key'])
        QgsExpressionContextUtils.setLayerVariable(self.coverage.sequencesLayer, "mapillaryCurrentKey", feature['skey'])
        self.coverage.imagesLayer.triggerRepaint()
        self.coverage.sequencesLayer.triggerRepaint()

    def changeMapillary_sequences(self, feature):
        #print("changeMapillary_sequences")
        self.viewer.openLocation(feature['ikey'])
        QgsExpressionContextUtils.setLayerVariable(self.coverage.sequencesLayer, "mapillaryCurrentKey", feature['key'])
        self.coverage.sequencesLayer.triggerRepaint()

    def changeMapillary_overview(self, feature):
        #print("changeMapillary_overview")
        self.viewer.openLocation(feature['ikey'])
        QgsExpressionContextUtils.setLayerVariable(self.coverage.overviewLayer, "mapillaryCurrentKey", feature['key'])
        self.coverage.overviewLayer.triggerRepaint()

    def removeMapillaryLayerGroup(self):
        mapillaryGroup = self.getMapillaryLayerGroup()
        QgsProject.instance().layerTreeRoot().removeChildNode(mapillaryGroup)

    def getMapillaryLayerGroup(self):
        legendRoot = QgsProject.instance().layerTreeRoot()
        mapillaryGroupName = 'Mapillary'
        mapillaryGroup = legendRoot.findGroup(mapillaryGroupName)
        if not mapillaryGroup:
            mapillaryGroup = legendRoot.insertGroup(0, mapillaryGroupName)
        mapillaryGroup.setExpanded(False)
        return mapillaryGroup

    def reorderLegendInterface(self):
        mapillaryLayers = self.coverage.getActiveLayers() + [self.sampleLocation.samplesLayer]
        print (mapillaryLayers)
        legendRoot = QgsProject.instance().layerTreeRoot()
        mapillaryGroup = self.getMapillaryLayerGroup()

        for layer in mapillaryLayers:
            try:
                layerNode = legendRoot.findLayer(layer)
                print ('GROUP',layerNode.parent())
            except:
                layerNode = None
            if layerNode:# and layerNode.parent() != mapillaryGroup:
                print ('moving',layer.name())
                cloned_node = layerNode.clone()
                mapillaryGroup.insertChildNode(0, cloned_node)
                if layerNode.parent():
                    layerNode.parent().removeChildNode(layerNode)
                else:
                    legendRoot.removeChildNode(layerNode)


