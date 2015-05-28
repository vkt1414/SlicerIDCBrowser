from __future__  import division
import urllib2, urllib,sys, os
import time
import string, json, zipfile, os.path
import csv
import pickle
import xml.etree.ElementTree as ET
import webbrowser
import unittest
import codecs
from random import randint
import dicom
from __main__ import vtk, qt, ctk, slicer
import TCIABrowserLib

#
# TCIABrowser
#

class TCIABrowser:
  def __init__(self, parent):
    parent.title = "TCIA Browser" # TODO make this more human readable by adding spaces
    parent.categories = ["Informatics"]
    parent.dependencies = []
    parent.contributors = ["Alireza Mehrtash (SPL, BWH), Andrey Fedorov (SPL, BWH)"]
    parent.helpText = """
    Connect to TCIA web archive and get a list of all available collections. From collection selector choose a collection and the patients table will be populated. Click on a patient and the studies for the patient will be presented. Do the same for studies. Finally choose a series from the series table and download the images from the server by pressing the "Download and Load" button. See <a href=\"http://wiki.slicer.org/slicerWiki/index.php/Documentation/Nightly/Extensions/TCIABrowser\">the documentation</a> for more information.
    """
    parent.acknowledgementText = """
    <img src=':Logos/QIICR.png'><br><br>
    Supported by NIH U24 CA180918 (PIs Kikinis and Fedorov)
    """ 
    self.parent = parent

    # Add this test to the SelfTest module's list for discovery when the module
    # is created.  Since this module may be discovered before SelfTests itself,
    # create the list if it doesn't already exist.
    try:
      slicer.selfTests
    except AttributeError:
      slicer.selfTests = {}
    slicer.selfTests['TCIABrowser'] = self.runTest

  def runTest(self):
    tester = TCIABrowserTest()
    tester.runTest()
#
# qTCIABrowserWidget
#

class TCIABrowserWidget:
  def __init__(self, parent = None):
    if not parent:
      self.parent = slicer.qMRMLWidget()
      self.parent.setLayout(qt.QVBoxLayout())
      self.parent.setMRMLScene(slicer.mrmlScene)
    else:
      self.parent = parent
    self.layout = self.parent.layout()
    if not parent:
      self.setup()
      self.parent.show()

    self.loadToScene = False

    self.browserWidget = qt.QWidget()
    self.browserWidget.setWindowTitle('TCIA Browser')

    self.initialConnection = False
    self.seriesTableRowCount = 0
    self.studiesTableRowCount = 0
    self.downloadProgressBars = {}
    self.downloadProgressLabels = {}
    self.selectedSeriesNicknamesDic = {} 
    self.downloadQueue = {}
    self.seriesRowNumber = {}

    self.imagesToDownloadCount = 0

    self.downloadProgressBarWidgets = []

    self.progress = qt.QProgressDialog(self.browserWidget)
    self.progress.setWindowTitle("TCIA Browser")
    # setup API key
    self.slicerApiKey = 'f88ff53d-882b-4c0d-b60c-0fb560e82cf1'
    self.currentAPIKey = self.slicerApiKey
    item = qt.QStandardItem()

    dicomAppWidget = ctk.ctkDICOMAppWidget()
    databaseDirectory = dicomAppWidget.databaseDirectory
    self.storagePath = databaseDirectory + "/TCIALocal/"
    if not os.path.exists(self.storagePath):
      os.makedirs(self.storagePath)

    self.cachePath = self.storagePath + "/ServerResponseCache/"
    self.downloadedSeriesArchiveFile = self.storagePath + 'archive.p'
    if os.path.isfile(self.downloadedSeriesArchiveFile):
      f = open(self.downloadedSeriesArchiveFile,'r')
      self.previouslyDownloadedSeries = pickle.load(f)
      f.close()
    else:
      with open(self.downloadedSeriesArchiveFile, 'w') as f:
        self.previouslyDownloadedSeries = []
        pickle.dump(self.previouslyDownloadedSeries, f)
      f.close()

    if not os.path.exists(self.cachePath):
      os.makedirs(self.cachePath)
    self.useCacheFlag = True

    # setup the TCIA client

  def enter(self):
    if self.showBrowserButton != None and self.showBrowserButton.enabled:
      self.showBrowser()
    if not self.initialConnection:
      self.getCollectionValues()

  def setup(self):
    # Instantiate and connect widgets ...
    self.modulePath = slicer.modules.tciabrowser.path.replace("TCIABrowser.py","")
    self.reportIcon = qt.QIcon(self.modulePath + '/Resources/Icons/report.png')
    downloadAndIndexIcon = qt.QIcon(self.modulePath + '/Resources/Icons/downloadAndIndex.png')
    downloadAndLoadIcon = qt.QIcon(self.modulePath + '/Resources/Icons/downloadAndLoad.png')
    browserIcon = qt.QIcon(self.modulePath + '/Resources/Icons/TCIABrowser.png')
    cancelIcon = qt.QIcon(self.modulePath + '/Resources/Icons/cancel.png')
    self.downloadIcon = qt.QIcon(self.modulePath + '/Resources/Icons/download.png')
    self.storedlIcon = qt.QIcon(self.modulePath + '/Resources/Icons/stored.png')
    self.browserWidget.setWindowIcon(browserIcon)

    #
    # Reload and Test area
    #
    reloadCollapsibleButton = ctk.ctkCollapsibleButton()
    reloadCollapsibleButton.text = "Reload && Test"
    # uncomment the next line for developing and testing
    self.layout.addWidget(reloadCollapsibleButton)
    reloadFormLayout = qt.QFormLayout(reloadCollapsibleButton)

    # reload button
    # (use this during development, but remove it when delivering
    #  your module to users)
    self.reloadButton = qt.QPushButton("Reload")
    self.reloadButton.toolTip = "Reload this module."
    self.reloadButton.name = "TCIABrowser Reload"
    reloadFormLayout.addWidget(self.reloadButton)
    self.reloadButton.connect('clicked()', self.onReload)

    # reload and test button
    # (use this during development, but remove it when delivering
    #  your module to users)
    self.reloadAndTestButton = qt.QPushButton("Reload and Test")
    self.reloadAndTestButton.toolTip = "Reload this module and then run the self tests."
    reloadFormLayout.addWidget(self.reloadAndTestButton)
    self.reloadAndTestButton.connect('clicked()', self.onReloadAndTest)

    #
    # Browser Area
    #
    browserCollapsibleButton = ctk.ctkCollapsibleButton()
    browserCollapsibleButton.text = "TCIA Browser"
    self.layout.addWidget(browserCollapsibleButton)
    browserLayout = qt.QVBoxLayout(browserCollapsibleButton)

    self.popupGeometry = qt.QRect()
    settings = qt.QSettings()
    mainWindow = slicer.util.mainWindow()
    if mainWindow:
      width = mainWindow.width*0.75
      height = mainWindow.height*0.75
      self.popupGeometry.setWidth(width)
      self.popupGeometry.setHeight(height)
      self.popupPositioned = False
      self.browserWidget.setGeometry(self.popupGeometry)

    #
    # Show Browser Button
    #
    self.showBrowserButton = qt.QPushButton("Show Browser")
    # self.showBrowserButton.toolTip = "."
    self.showBrowserButton.enabled = False 
    browserLayout.addWidget(self.showBrowserButton)


    # Browser Widget Layout within the collapsible button
    browserWidgetLayout = qt.QVBoxLayout(self.browserWidget)
    #

    self.collectionsCollapsibleGroupBox = ctk.ctkCollapsibleGroupBox()
    self.collectionsCollapsibleGroupBox.setTitle('Collections')
    browserWidgetLayout.addWidget(self.collectionsCollapsibleGroupBox)  # 
    collectionsFormLayout = qt.QHBoxLayout(self.collectionsCollapsibleGroupBox)

    #
    # Collection Selector ComboBox
    #
    self.collectionSelectorLabel = qt.QLabel('Current Collection:')
    collectionsFormLayout.addWidget(self.collectionSelectorLabel)
    # Selector ComboBox
    self.collectionSelector = qt.QComboBox()
    self.collectionSelector.setMinimumWidth(200)
    collectionsFormLayout.addWidget( self.collectionSelector)

    #
    # Use Cache CheckBox
    #
    self.useCacheCeckBox= qt.QCheckBox("Cache server responses")
    self.useCacheCeckBox.toolTip = '''For faster browsing if this box is checked\
    the browser will cache server responses and on further calls\
    would populate tables based on saved data on disk.'''

    collectionsFormLayout.addWidget(self.useCacheCeckBox)
    self.useCacheCeckBox.setCheckState(True)
    self.useCacheCeckBox.setTristate(False)
    collectionsFormLayout.addStretch(4)
    logoLabelText = "<img src='" + self.modulePath + "/Resources/Logos/logo-vertical.png'" +">"
    self.logoLabel = qt.QLabel(logoLabelText)
    collectionsFormLayout.addWidget(self.logoLabel)
    

    #
    # Patient Table Widget 
    #
    self.patientsCollapsibleGroupBox = ctk.ctkCollapsibleGroupBox()
    self.patientsCollapsibleGroupBox.setTitle('Patients')
    browserWidgetLayout.addWidget(self.patientsCollapsibleGroupBox)
    patientsVBoxLayout1 = qt.QVBoxLayout(self.patientsCollapsibleGroupBox)
    patientsExpdableArea = ctk.ctkExpandableWidget()
    patientsVBoxLayout1.addWidget(patientsExpdableArea)
    patientsVBoxLayout2 = qt.QVBoxLayout(patientsExpdableArea)
    #patientsVerticalLayout = qt.QVBoxLayout(patientsExpdableArea)
    self.patientsTableWidget = qt.QTableWidget()
    self.patientsModel = qt.QStandardItemModel()
    self.patientsTableHeaderLabels = ['Patient ID','Patient Name','Patient BirthDate',
        'Patient Sex','Ethnic Group','Clinical Data']
    self.patientsTableWidget.setColumnCount(6)
    self.patientsTableWidget.sortingEnabled = True
    self.patientsTableWidget.setHorizontalHeaderLabels(self.patientsTableHeaderLabels)
    self.patientsTableWidgetHeader = self.patientsTableWidget.horizontalHeader()
    self.patientsTableWidgetHeader.setStretchLastSection(True)
    # patientsTableWidgetHeader.setResizeMode(qt.QHeaderView.Stretch)
    patientsVBoxLayout2.addWidget(self.patientsTableWidget)
    self.patientsTreeSelectionModel = self.patientsTableWidget.selectionModel()
    abstractItemView =qt.QAbstractItemView()
    self.patientsTableWidget.setSelectionBehavior(abstractItemView.SelectRows) 
    verticalheader = self.patientsTableWidget.verticalHeader()
    verticalheader.setDefaultSectionSize(20)
    patientsVBoxLayout1.setSpacing(0)
    patientsVBoxLayout2.setSpacing(0)
    patientsVBoxLayout1.setMargin(0)
    patientsVBoxLayout2.setContentsMargins(7,3,7,7)


    #
    # Studies Table Widget
    #
    self.studiesCollapsibleGroupBox = ctk.ctkCollapsibleGroupBox()
    self.studiesCollapsibleGroupBox.setTitle('Studies')
    browserWidgetLayout.addWidget(self.studiesCollapsibleGroupBox) 
    studiesVBoxLayout1 = qt.QVBoxLayout(self.studiesCollapsibleGroupBox)
    studiesExpdableArea = ctk.ctkExpandableWidget()
    studiesVBoxLayout1.addWidget(studiesExpdableArea)
    studiesVBoxLayout2 = qt.QVBoxLayout(studiesExpdableArea)
    self.studiesTableWidget = qt.QTableWidget()
    self.studiesTableWidget.setCornerButtonEnabled(True)
    self.studiesModel = qt.QStandardItemModel()
    self.studiesTableHeaderLabels = ['Study Instance UID','Study Date','Study Description',
        'Admitting Diagnosis Description','Study ID','Patient Age','Series Count']
    self.studiesTableWidget.setColumnCount(7)
    self.studiesTableWidget.sortingEnabled = True
    self.studiesTableWidget.hideColumn(0)
    self.studiesTableWidget.setHorizontalHeaderLabels(self.studiesTableHeaderLabels)
    self.studiesTableWidget.resizeColumnsToContents()
    studiesVBoxLayout2.addWidget(self.studiesTableWidget)
    self.studiesTreeSelectionModel = self.studiesTableWidget.selectionModel()
    self.studiesTableWidget.setSelectionBehavior(abstractItemView.SelectRows) 
    studiesVerticalheader = self.studiesTableWidget.verticalHeader()
    studiesVerticalheader.setDefaultSectionSize(20)
    self.studiesTableWidgetHeader = self.studiesTableWidget.horizontalHeader()
    self.studiesTableWidgetHeader.setStretchLastSection(True)

    studiesSelectOptionsWidget = qt.QWidget()
    studiesSelectOptionsLayout = qt.QHBoxLayout(studiesSelectOptionsWidget )
    studiesSelectOptionsLayout.setMargin(0)
    studiesVBoxLayout2.addWidget(studiesSelectOptionsWidget )
    studiesSelectLabel = qt.QLabel('Select:')
    studiesSelectOptionsLayout.addWidget(studiesSelectLabel)
    self.studiesSelectAllButton = qt.QPushButton('All')
    self.studiesSelectAllButton.enabled = False
    self.studiesSelectAllButton.setMaximumWidth(50)
    studiesSelectOptionsLayout.addWidget(self.studiesSelectAllButton)
    self.studiesSelectNoneButton = qt.QPushButton('None')
    self.studiesSelectNoneButton.enabled = False
    self.studiesSelectNoneButton.setMaximumWidth(50)
    studiesSelectOptionsLayout.addWidget(self.studiesSelectNoneButton)
    studiesSelectOptionsLayout.addStretch(1)
    studiesVBoxLayout1.setSpacing(0)
    studiesVBoxLayout2.setSpacing(0)
    studiesVBoxLayout1.setMargin(0)
    studiesVBoxLayout2.setContentsMargins(7,3,7,7)

    #
    # Series Table Widget 
    #
    self.seriesCollapsibleGroupBox = ctk.ctkCollapsibleGroupBox()
    self.seriesCollapsibleGroupBox.setTitle('Series')
    browserWidgetLayout.addWidget(self.seriesCollapsibleGroupBox)
    seriesVBoxLayout1 = qt.QVBoxLayout(self.seriesCollapsibleGroupBox)
    seriesExpdableArea = ctk.ctkExpandableWidget()
    seriesVBoxLayout1.addWidget(seriesExpdableArea)
    seriesVBoxLayout2 = qt.QVBoxLayout(seriesExpdableArea)
    self.seriesTableWidget = qt.QTableWidget()
    #self.seriesModel = qt.QStandardItemModel()
    self.seriesTableWidget.setColumnCount(13)
    self.seriesTableWidget.sortingEnabled = True
    self.seriesTableWidget.hideColumn(0)
    self.seriesTableHeaderLabels = ['Series Instance UID','Status','Modality',
        'Protocol Name','Series Date','Series Description','Body Part Examined',
        'Series Number','Annotation Flag','Manufacturer',
        'Manufacturer Model Name','Software Versions','Image Count']
    self.seriesTableWidget.setHorizontalHeaderLabels(self.seriesTableHeaderLabels)
    self.seriesTableWidget.resizeColumnsToContents()
    seriesVBoxLayout2.addWidget(self.seriesTableWidget)
    self.seriesTreeSelectionModel = self.studiesTableWidget.selectionModel()
    self.seriesTableWidget.setSelectionBehavior(abstractItemView.SelectRows) 
    self.seriesTableWidget.setSelectionMode(3) 
    self.seriesTableWidgetHeader = self.seriesTableWidget.horizontalHeader()
    self.seriesTableWidgetHeader.setStretchLastSection(True)
    #seriesTableWidgetHeader.setResizeMode(qt.QHeaderView.Stretch)
    seriesVerticalheader = self.seriesTableWidget.verticalHeader()
    seriesVerticalheader.setDefaultSectionSize(20)

    seriesSelectOptionsWidget = qt.QWidget()
    seriesSelectOptionsLayout = qt.QHBoxLayout(seriesSelectOptionsWidget )
    seriesVBoxLayout2.addWidget(seriesSelectOptionsWidget )
    seriesSelectOptionsLayout.setMargin(0)
    seriesSelectLabel = qt.QLabel('Select:')
    seriesSelectOptionsLayout.addWidget(seriesSelectLabel)
    self.seriesSelectAllButton = qt.QPushButton('All')
    self.seriesSelectAllButton.enabled = False
    self.seriesSelectAllButton.setMaximumWidth(50)
    seriesSelectOptionsLayout.addWidget(self.seriesSelectAllButton)
    self.seriesSelectNoneButton = qt.QPushButton('None')
    self.seriesSelectNoneButton.enabled = False
    self.seriesSelectNoneButton.setMaximumWidth(50)
    seriesSelectOptionsLayout.addWidget(self.seriesSelectNoneButton)
    seriesVBoxLayout1.setSpacing(0)
    seriesVBoxLayout2.setSpacing(0)
    seriesVBoxLayout1.setMargin(0)
    seriesVBoxLayout2.setContentsMargins(7,3,7,7)


    seriesSelectOptionsLayout.addStretch(1)
    self.imagesCountLabel = qt.QLabel()
    self.imagesCountLabel.text = 'No. of images to download: ' + '<span style=" font-size:8pt; font-weight:600; color:#aa0000;">'+  str(self.imagesToDownloadCount) +'</span>' + ' '
    seriesSelectOptionsLayout.addWidget(self.imagesCountLabel)
    #seriesSelectOptionsLayout.setAlignment(qt.Qt.AlignTop)

    # Index Button
    #
    self.indexButton = qt.QPushButton()
    self.indexButton.setMinimumWidth(50)
    self.indexButton.toolTip = "Download and Index: The browser will download"\
        " the selected sereies and index them in 3D Slicer DICOM Database."
    self.indexButton.setIcon(downloadAndIndexIcon)
    iconSize = qt.QSize(70,40)
    self.indexButton.setIconSize(iconSize)
    #self.indexButton.setMinimumHeight(50)
    self.indexButton.enabled = False 
    #downloadWidgetLayout.addStretch(4)
    seriesSelectOptionsLayout.addWidget(self.indexButton)

    #downloadWidgetLayout.addStretch(1)
    #
    # Load Button
    #
    self.loadButton = qt.QPushButton("")
    self.loadButton.setMinimumWidth(50)
    self.loadButton.setIcon(downloadAndLoadIcon)
    self.loadButton.setIconSize(iconSize)
    #self.loadButton.setMinimumHeight(50)
    self.loadButton.toolTip = "Download and Load: The browser will download"\
        " the selected sereies and Load them in 3D Slicer scene."
    self.loadButton.enabled = False 
    seriesSelectOptionsLayout.addWidget(self.loadButton)
    #downloadWidgetLayout.addStretch(4)

    self.cancelDownloadButton = qt.QPushButton('')
    seriesSelectOptionsLayout.addWidget(self.cancelDownloadButton)
    self.cancelDownloadButton.setIconSize(iconSize)
    self.cancelDownloadButton.toolTip = "Cancel all downloads."
    self.cancelDownloadButton.setIcon(cancelIcon)
    self.cancelDownloadButton.enabled = False

    self.statusFrame = qt.QFrame()
    browserWidgetLayout.addWidget(self.statusFrame)
    statusHBoxLayout = qt.QHBoxLayout(self.statusFrame)
    statusHBoxLayout.setMargin(0)
    statusHBoxLayout.setSpacing(0)
    self.statusLabel = qt.QLabel('')
    statusHBoxLayout.addWidget(self.statusLabel)
    statusHBoxLayout.addStretch(1)
    #
    # context menu
    #
    self.patientsTableWidget.setContextMenuPolicy(2)
    self.clinicalDataRetrieveAction = qt.QAction("Get Clincal Data", self.patientsTableWidget)
    self.patientsTableWidget.addAction(self.clinicalDataRetrieveAction)
    #self.contextMenu = qt.QMenu(self.patientsTableWidget)
    #self.contextMenu.addAction(self.clinicalDataRetrieveAction)
    self.clinicalDataRetrieveAction.enabled = False 

    #
    # Settings Area
    #
    settingsCollapsibleButton = ctk.ctkCollapsibleButton()
    settingsCollapsibleButton.text = "Settings"
    self.layout.addWidget(settingsCollapsibleButton)
    settingsGridLayout = qt.QGridLayout(settingsCollapsibleButton)
    settingsCollapsibleButton.collapsed = True

    # Storage Path button
    #
    #storageWidget = qt.QWidget()
    #storageFormLayout = qt.QFormLayout(storageWidget)
    #settingsVBoxLayout.addWidget(storageWidget)

    storagePathLabel = qt.QLabel("Storage Folder: ")
    self.storagePathButton = ctk.ctkDirectoryButton()
    self.storagePathButton.directory = self.storagePath
    settingsGridLayout.addWidget(storagePathLabel,0,0,1,1)
    settingsGridLayout.addWidget(self.storagePathButton,0,1,1,4)
    self.apiSettingsPopup = TCIABrowserLib.APISettingsPopup()
    self.clinicalPopup = TCIABrowserLib.clinicalDataPopup(self.cachePath,self.reportIcon)

    #
    # Connection Area
    #
    # Add remove button
    customAPILabel = qt.QLabel("Custom API Key: ")

    addRemoveApisButton = qt.QPushButton("+")
    addRemoveApisButton.toolTip = "Add or Remove APIs"
    addRemoveApisButton.enabled = True
    addRemoveApisButton.setMaximumWidth(20)

    # API selection combo box
    self.apiSelectionComboBox = qt.QComboBox()
    self.apiSelectionComboBox.addItem('Slicer API')
    settings = qt.QSettings()
    settings.beginGroup("TCIABrowser/API-Keys")
    self.userApiNames = settings.childKeys()

    for api in self.userApiNames:
      self.apiSelectionComboBox.addItem(api)
    settings.endGroup()

    self.connectButton = qt.QPushButton("Connect")
    self.connectButton.toolTip = "Connect to TCIA Server."
    self.connectButton.enabled = True

    settingsGridLayout.addWidget(customAPILabel,1,0,1,1)
    settingsGridLayout.addWidget(addRemoveApisButton,1,1,1,1)
    settingsGridLayout.addWidget(self.apiSelectionComboBox,1,2,1,2)
    settingsGridLayout.addWidget(self.connectButton,1,4,2,1)

    # connections
    self.showBrowserButton.connect('clicked(bool)', self.onShowBrowserButton)
    addRemoveApisButton.connect('clicked(bool)', self.apiSettingsPopup.open)
    self.apiSelectionComboBox.connect('currentIndexChanged(QString)',self.apiKeySelected)
    self.collectionSelector.connect('currentIndexChanged(QString)',self.collectionSelected)
    self.patientsTableWidget.connect('itemSelectionChanged()', self.patientsTableSelectionChanged)
    self.studiesTableWidget.connect('itemSelectionChanged()', self.studiesTableSelectionChanged)
    self.seriesTableWidget.connect('itemSelectionChanged()',self.seriesSelected)
    self.connectButton.connect('clicked(bool)', self.getCollectionValues)
    self.useCacheCeckBox.connect('stateChanged(int)', self.onUseCacheStateChanged)
    self.indexButton.connect('clicked(bool)', self.onIndexButton)
    self.loadButton.connect('clicked(bool)', self.onLoadButton)
    self.cancelDownloadButton.connect('clicked(bool)', self.onCancelDownloadButton)
    self.storagePathButton.connect('directoryChanged(const QString &)',self.onStoragePathButton)
    self.clinicalDataRetrieveAction.connect('triggered()', self.onContextMenuTriggered)
    self.clinicalDataRetrieveAction.connect('triggered()', self.clinicalPopup.open)
    self.seriesSelectAllButton.connect('clicked(bool)', self.onSeriesSelectAllButton)
    self.seriesSelectNoneButton.connect('clicked(bool)', self.onSeriesSelectNoneButton)
    self.studiesSelectAllButton.connect('clicked(bool)', self.onStudiesSelectAllButton)
    self.studiesSelectNoneButton.connect('clicked(bool)', self.onStudiesSelectNoneButton)

    # Add vertical spacer
    self.layout.addStretch(1)

  def cleanup(self):
    pass

  def apiKeySelected(self):
    settings = qt.QSettings()
    settings.beginGroup("TCIABrowser/API-Keys")

    #self.connectButton.enabled = True
    if self.apiSelectionComboBox.currentText == 'Slicer API':
      self.currentAPIKey = self.slicerApiKey
    else:
      self.currentAPIKey = settings.value(self.apiSelectionComboBox.currentText)

  def onShowBrowserButton(self):
    self.showBrowser()

  def onUseCacheStateChanged(self,state):
    if state == 0:
      self.useCacheFlag = False
    elif state ==2:
      self.useCacheFlag= True

  def onContextMenuTriggered(self):
    self.clinicalPopup.getData(self.selectedCollection,self.selectedPatient)

  def showBrowser(self):
    if not self.browserWidget.isVisible():
      self.popupPositioned = False
      self.browserWidget.show()
      if self.popupGeometry.isValid():
        self.browserWidget.setGeometry(self.popupGeometry)
    self.browserWidget.raise_() 

    if not self.popupPositioned:
      mainWindow = slicer.util.mainWindow()
      screenMainPos = mainWindow.pos
      x = screenMainPos.x() + 100
      y = screenMainPos.y() + 100
      self.browserWidget.move(qt.QPoint(x,y))
      self.popupPositioned = True

  def showStatus(self, message, waitMessage='Waiting for TCIA server .... '):
    self.statusLabel.text = waitMessage + message
    self.statusLabel.setStyleSheet("QLabel { background-color : #F0F0F0 ; color : #383838; }")
    slicer.app.processEvents()

  def clearStatus(self):
    self.statusLabel.text = ''
    self.statusLabel.setStyleSheet("QLabel { background-color : white; color : black; }")

  def onStoragePathButton(self):
    self.storagePath = self.storagePathButton.directory

  def getCollectionValues(self):
    self.initialConnection = True
    # Instantiate TCIAClient object
    self.TCIAClient = TCIABrowserLib.TCIAClient()
    self.showStatus("Getting Available Collections")
    try:
      response = self.TCIAClient.get_collection_values()
      responseString = response.read()[:]
      self.populateCollectionsTreeView(responseString)
      self.clearStatus()

    except Exception, error:
      self.connectButton.enabled = True
      self.clearStatus()
      message = "Error in getting response from TCIA server.\nHTTP Error:\n"+ str(error)
      qt.QMessageBox.critical(slicer.util.mainWindow(),
                        'TCIA Browser', message, qt.QMessageBox.Ok)
    self.showBrowserButton.enabled = True
    self.showBrowser()

  def onStudiesSelectAllButton(self):
    self.studiesTableWidget.selectAll()

  def onStudiesSelectNoneButton(self):
    self.studiesTableWidget.clearSelection()

  def onSeriesSelectAllButton(self):
    self.seriesTableWidget.selectAll()

  def onSeriesSelectNoneButton(self):
    self.seriesTableWidget.clearSelection()

  def collectionSelected(self,item):
    self.loadButton.enabled = False
    self.indexButton.enabled = False
    self.clearPatientsTableWidget()
    self.clearStudiesTableWidget()
    self.clearSeriesTableWidget()
    self.selectedCollection = item
    cacheFile = self.cachePath+self.selectedCollection+'.json'
    self.progressMessage = "Getting available patients for collection: " + self.selectedCollection
    self.showStatus(self.progressMessage)
    if self.selectedCollection[0:4] != 'TCGA':
      self.clinicalDataRetrieveAction.enabled = False 
    else:
      self.clinicalDataRetrieveAction.enabled = True

    if os.path.isfile(cacheFile) and self.useCacheFlag:
      f = codecs.open(cacheFile,'r',encoding='utf8')
      responseString = f.read()[:]
      f.close()
      self.populatePatientsTableWidget(responseString)
      self.clearStatus()
      groupBoxTitle = 'Patients (Accessed: '+ time.ctime(os.path.getmtime(cacheFile))+')'
      self.patientsCollapsibleGroupBox.setTitle(groupBoxTitle)

    else:
      try:
        response = self.TCIAClient.get_patient(collection = self.selectedCollection)

        with open(cacheFile, 'w') as outputFile:
          self.stringBufferRead(outputFile, response)
        outputFile.close()
        f = codecs.open(cacheFile,'r',encoding='utf8')
        responseString = f.read()[:]
        self.populatePatientsTableWidget(responseString)
        groupBoxTitle = 'Patients (Accessed: '+ time.ctime(os.path.getmtime(cacheFile))+')'
        self.patientsCollapsibleGroupBox.setTitle(groupBoxTitle)
        self.clearStatus()

      except Exception, error:
        self.clearStatus()
        message = "Error in getting response from TCIA server.\nHTTP Error:\n"+ str(error)
        qt.QMessageBox.critical(slicer.util.mainWindow(),
                        'TCIA Browser', message, qt.QMessageBox.Ok)

  def patientsTableSelectionChanged(self):
    self.clearStudiesTableWidget()
    self.clearSeriesTableWidget()
    self.studiesTableRowCount = 0
    self.numberOfSelectedPatinets = 0
    for n in range(len(self.patientsIDs)):
      if self.patientsIDs[n].isSelected():
        self.numberOfSelectedPatinets += 1
        self.patientSelected(n)

  def patientSelected(self,row):
    self.loadButton.enabled = False
    self.indexButton.enabled = False
    #self.clearStudiesTableWidget()
    self.clearSeriesTableWidget()
    self.selectedPatient = self.patientsIDs[row].text()
    cacheFile = self.cachePath+self.selectedPatient+'.json'
    self.progressMessage = "Getting available studies for patient ID: " + self.selectedPatient
    self.showStatus(self.progressMessage)
    if os.path.isfile(cacheFile) and self.useCacheFlag:
      f = codecs.open(cacheFile,'r',encoding='utf8')
      responseString = f.read()[:]
      f.close()
      self.populateStudiesTableWidget(responseString)
      self.clearStatus()
      if self.numberOfSelectedPatinets == 1:
        groupBoxTitle = 'Studies (Accessed: '+ time.ctime(os.path.getmtime(cacheFile))+')'
      else:
        groupBoxTitle = 'Studies '

      self.studiesCollapsibleGroupBox.setTitle(groupBoxTitle)

    else:
      try:    
        response = self.TCIAClient.get_patient_study(patientId = self.selectedPatient)
        responseString = response.read()[:]
        with open(cacheFile, 'w') as outputFile:
          outputFile.write(responseString)
          outputFile.close()
        f = codecs.open(cacheFile,'r',encoding='utf8')
        responseString = f.read()[:]
        self.populateStudiesTableWidget(responseString)
        if self.numberOfSelectedPatinets == 1:
          groupBoxTitle = 'Studies (Accessed: '+ time.ctime(os.path.getmtime(cacheFile))+')'
        else:
          groupBoxTitle = 'Studies '

        self.studiesCollapsibleGroupBox.setTitle(groupBoxTitle)
        self.clearStatus()

      except Exception, error:
        self.clearStatus()
        message = "Error in getting response from TCIA server.\nHTTP Error:\n"+ str(error)
        qt.QMessageBox.critical(slicer.util.mainWindow(),
                          'TCIA Browser', message, qt.QMessageBox.Ok)

  def studiesTableSelectionChanged(self):
    self.clearSeriesTableWidget()
    self.seriesTableRowCount = 0
    self.numberOfSelectedStudies = 0
    for n in range(len(self.studyInstanceUIDs)):
      if self.studyInstanceUIDs[n].isSelected():
        self.numberOfSelectedStudies += 1
        self.studySelected(n)

  def studySelected(self,row):
    self.loadButton.enabled = False
    self.indexButton.enabled = False
    self.selectedStudy = self.studyInstanceUIDs[row].text()
    self.selectedStudyRow = row
    self.progressMessage = "Getting available series for studyInstanceUID: " + self.selectedStudy
    self.showStatus(self.progressMessage)
    cacheFile = self.cachePath+self.selectedStudy+'.json'
    if os.path.isfile(cacheFile) and self.useCacheFlag:
      f = codecs.open(cacheFile,'r',encoding='utf8')
      responseString = f.read()[:]
      f.close()
      self.populateSeriesTableWidget(responseString)
      self.clearStatus()
      if self.numberOfSelectedStudies == 1:
        groupBoxTitle = 'Series (Accessed: '+ time.ctime(os.path.getmtime(cacheFile))+')'
      else:
        groupBoxTitle = 'Series '

      self.seriesCollapsibleGroupBox.setTitle(groupBoxTitle)

    else:
      self.progressMessage = "Getting available series for studyInstanceUID: " + self.selectedStudy
      self.showStatus(self.progressMessage)
      try:
        response = self.TCIAClient.get_series(studyInstanceUID = self.selectedStudy)
        responseString = response.read()[:]
        with open(cacheFile, 'w') as outputFile:
          outputFile.write(responseString)
          outputFile.close()
        self.populateSeriesTableWidget(responseString)

        if self.numberOfSelectedStudies == 1:
          groupBoxTitle = 'Series (Accessed: '+ time.ctime(os.path.getmtime(cacheFile))+')'
        else:
          groupBoxTitle = 'Series '

        self.seriesCollapsibleGroupBox.setTitle(groupBoxTitle)
        self.clearStatus()

      except Exception, error:
        self.clearStatus()
        message = "Error in getting response from TCIA server.\nHTTP Error:\n"+ str(error)
        qt.QMessageBox.critical(slicer.util.mainWindow(),
                          'TCIA Browser', message, qt.QMessageBox.Ok)

    self.onSeriesSelectAllButton()
    #self.loadButton.enabled = True
    #self.indexButton.enabled = True

  def seriesSelected(self):
    self.imagesToDownloadCount = 0
    self.loadButton.enabled = False
    self.indexButton.enabled = False
    for n in range(len(self.seriesInstanceUIDs)):
      if self.seriesInstanceUIDs[n].isSelected():
        self.imagesToDownloadCount += int(self.imageCounts[n].text())
        self.loadButton.enabled = True
        self.indexButton.enabled = True
    self.imagesCountLabel.text = 'No. of images to download: ' + '<span style=" font-size:8pt; font-weight:600; color:#aa0000;">'+  str(self.imagesToDownloadCount) +'</span>' + ' '


  def onIndexButton(self):
    self.loadToScene = False
    self.addSelectedToDownloadQueue()
    #self.addFilesToDatabase()

  def onLoadButton(self):
    self.loadToScene = True
    self.addSelectedToDownloadQueue()

  def onCancelDownloadButton(self):
    self.cancelDownload = True
    for series in self.downloadQueue.keys():
      self.removeDownloadProgressBar(series)
    downloadQueue = {}
    seriesRowNumber = {}

  def addFilesToDatabase(self,seriesUID):
    self.progressMessage = "Adding Files to DICOM Database "
    self.showStatus(self.progressMessage)
    dicomWidget = slicer.modules.dicom.widgetRepresentation().self()

    indexer = ctk.ctkDICOMIndexer()
    indexer.addDirectory(slicer.dicomDatabase, self.extractedFilesDirectory)
    indexer.waitForImportFinished()
    seriesUID = seriesUID.replace("'","")
    self.dicomDatabase = slicer.dicomDatabase
    self.fileList = slicer.dicomDatabase.filesForSeries(seriesUID)
    originalDatabaseDirectory = os.path.split(slicer.dicomDatabase.databaseFilename)[0]
    # change database directory to update dicom browser tables
    dicomWidget.onDatabaseDirectoryChanged(self.extractedFilesDirectory)
    dicomWidget.onDatabaseDirectoryChanged(originalDatabaseDirectory)
    self.clearStatus()

  def addSelectedToDownloadQueue(self):
    self.cancelDownload = False
    allSelectedSeriesUIDs = []
    downloadQueue = {}
    self.seriesRowNumber = {}

    for n in range(len(self.seriesInstanceUIDs)):
      #print self.seriesInstanceUIDs[n]
      if self.seriesInstanceUIDs[n].isSelected():
        selectedCollection = self.selectedCollection
        selectedPatient = self.selectedPatient
        selectedStudy = self.selectedStudy
        selectedSeries =  self.seriesInstanceUIDs[n].text()
        allSelectedSeriesUIDs.append(selectedSeries)
        # selectedSeries = self.selectedSeriesUIdForDownload
        self.selectedSeriesNicknamesDic[selectedSeries] = str(selectedPatient
            )+'-' +str(self.selectedStudyRow+1)+'-'+str(n+1)

        # create download queue
        if not any(selectedSeries == s for s in self.previouslyDownloadedSeries):
          downloadFolderPath =  self.storagePath + str(len(self.previouslyDownloadedSeries))+ "/"
          self.makeDownloadProgressBar(selectedSeries,n)
          self.downloadQueue[selectedSeries] = downloadFolderPath
          self.seriesRowNumber[selectedSeries] = n

    self.seriesTableWidget.clearSelection()
    self.patientsTableWidget.enabled = False
    self.studiesTableWidget.enabled = False
    self.collectionSelector.enabled = False
    self.downloadSelectedSeries()

    if self.loadToScene:
      for seriesUID in allSelectedSeriesUIDs:
        if any(seriesUID == s for s in self.previouslyDownloadedSeries):
          self.progressMessage = "Examine Files to Load"
          self.showStatus(self.progressMessage,'')
          plugin = slicer.modules.dicomPlugins['DICOMScalarVolumePlugin']()
          seriesUID = seriesUID.replace("'","")
          dicomDatabase = slicer.dicomDatabase
          fileList = slicer.dicomDatabase.filesForSeries(seriesUID)
          loadables = plugin.examine([fileList])
          self.clearStatus()
          volume = plugin.load(loadables[0])

  def downloadSelectedSeries(self):
    while self.downloadQueue and not self.cancelDownload:
      self.cancelDownloadButton.enabled = True
      selectedSeries, downloadFolderPath = self.downloadQueue.popitem()
      if not os.path.exists(downloadFolderPath):
        os.makedirs(downloadFolderPath)
      # save series uid in a text file for further reference
      with open(downloadFolderPath + 'seriesUID.txt', 'w') as f:
        f.write(selectedSeries)
      f.close()
      fileName = downloadFolderPath +  'images.zip'
      self.extractedFilesDirectory = downloadFolderPath +  'images'
      self.progressMessage = "Downloading Images for series InstanceUID: " + selectedSeries
      self.showStatus(self.progressMessage)
      seriesSize = self.getSeriesSize(selectedSeries)
      try:
        response = self.TCIAClient.get_image(seriesInstanceUid = selectedSeries)
        slicer.app.processEvents()
        # Save server response as images.zip in current directory
        if response.getcode() == 200:
          destinationFile = open(fileName, "wb")
          status = self.__bufferRead(destinationFile, response, selectedSeries, seriesSize)

          destinationFile.close()
          # print "\nDownloaded file %s.zip from the TCIA server" %fileName
          self.clearStatus()
          if status:
            self.progressMessage = "Extracting Images"
            # Unzip the data
            self.showStatus(self.progressMessage)   
            self.unzip(fileName,self.extractedFilesDirectory)
            self.clearStatus()
            # Import the data into dicomAppWidget and open the dicom browser
            self.addFilesToDatabase(selectedSeries)
            #
            self.previouslyDownloadedSeries.append(selectedSeries)
            with open(self.downloadedSeriesArchiveFile, 'w') as f:
              pickle.dump(self.previouslyDownloadedSeries, f)
            f.close()
            n = self.seriesRowNumber[selectedSeries]
            table = self.seriesTableWidget
            item = table.item(n,1)
            item.setIcon(self.storedlIcon)
          else:
            self.removeDownloadProgressBar(selectedSeries)
            self.downloadQueue.pop(selectedSeries, None)

          os.remove(fileName)

        else:
          self.clearStatus()
          print "Error : " + str(response.getcode) # print error code
          print "\n" + str(response.info())

      except Exception, error:
        self.clearStatus()
        message = "Error in getting response from TCIA server.\nHTTP Error:\n"+ str(error)
        qt.QMessageBox.critical(slicer.util.mainWindow(),
                          'TCIA Browser', message, qt.QMessageBox.Ok)
    self.cancelDownloadButton.enabled = False
    self.collectionSelector.enabled = True
    self.patientsTableWidget.enabled = True
    self.studiesTableWidget.enabled = True

  def makeDownloadProgressBar(self, selectedSeries,n):
    downloadProgressBar = qt.QProgressBar()
    self.downloadProgressBars [selectedSeries] = downloadProgressBar
    titleLabel = qt.QLabel(selectedSeries)
    progressLabel = qt.QLabel(self.selectedSeriesNicknamesDic[selectedSeries]+' (0 KB)')
    self.downloadProgressLabels[selectedSeries] = progressLabel
    table = self.seriesTableWidget
    table.setCellWidget(n,1,downloadProgressBar)
    #self.downloadFormLayout.addRow(progressLabel,downloadProgressBar)

  def removeDownloadProgressBar(self, selectedSeries):
    n = self.seriesRowNumber[selectedSeries]
    table = self.seriesTableWidget
    table.setCellWidget(n,1,None)
    self.downloadProgressBars[selectedSeries].deleteLater()
    del self.downloadProgressBars[selectedSeries]
    self.downloadProgressLabels[selectedSeries].deleteLater()
    del self.downloadProgressLabels[selectedSeries]

  def stringBufferRead(self, dstFile, response, bufferSize=819):
    self.downloadSize = 0
    while 1:
      #
      # If DOWNLOAD FINISHED
      #
      buffer = response.read(bufferSize)[:]
      slicer.app.processEvents()
      if not buffer: 
        # Pop from the queue
        break
      #
      # Otherwise, Write buffer chunk to file
      #
      slicer.app.processEvents()
      dstFile.write(buffer)
      #
      # And update progress indicators
      #
      self.downloadSize += len(buffer)
      #print self.downloadSize

  # This part was adopted from XNATSlicer module
  def __bufferRead(self, dstFile, response, selectedSeries, seriesSize, bufferSize=8192):

    currentDownloadProgressBar = self.downloadProgressBars[selectedSeries]
    currentProgressLabel = self.downloadProgressLabels[selectedSeries]

    # Define the buffer read loop
    self.downloadSize = 0
    while 1:
      # If DOWNLOAD FINISHED
      buffer = response.read(bufferSize)
      slicer.app.processEvents()
      if not buffer: 
        # Pop from the queue
        currentDownloadProgressBar.setMaximum(100)
        currentDownloadProgressBar.setValue(100)
        #currentDownloadProgressBar.setVisible(False)
        #currentProgressLabel.setVisible(False)
        self.removeDownloadProgressBar(selectedSeries)
        self.downloadQueue.pop(selectedSeries, None)
        break
      if self.cancelDownload:
        return False

      # Otherwise, Write buffer chunk to file
      slicer.app.processEvents()
      dstFile.write(buffer)
      #
      # And update progress indicators
      #
      self.downloadSize += len(buffer)
      currentDownloadProgressBar.setValue(self.downloadSize/seriesSize*100)
      #currentDownloadProgressBar.setMaximum(0)
      currentProgressLabel.text = self.selectedSeriesNicknamesDic[
          selectedSeries]+' ('+ str(int(self.downloadSize/1024)
              ) + ' of ' + str(int(seriesSize/1024)) + " KB)"
    #return self.downloadSize
    return True

  def unzip(self,sourceFilename, destinationDir):
    with zipfile.ZipFile(sourceFilename) as zf:
      for member in zf.infolist():
        words = member.filename.split('/')
        path = destinationDir 
        for word in words[:-1]:
          drive, word = os.path.splitdrive(word)
          head, word = os.path.split(word)
          if word in (os.curdir, os.pardir, ''): continue
          path = os.path.join(path, word)
        zf.extract(member, path)

  def getSeriesSize(self, seriesInstanceUID):
    response = self.TCIAClient.get_series_size(seriesInstanceUID)
    responseString = response.read()[:]
    jsonResponse = json.loads(responseString)
    # TCIABrowser returns the total size of the series while we are
    # recieving series in compressed zip format. The compression ration
    # is an approximation.
    compressionRatio = 1.5
    size = float(jsonResponse[0]['TotalSizeInBytes'])/compressionRatio
    return size

  def populateCollectionsTreeView(self,responseString):
    collections = json.loads(responseString)
    # populate collection selector
    n = 0
    self.collectionSelector.disconnect('currentIndexChanged(QString)')
    self.collectionSelector.clear()
    self.collectionSelector.connect('currentIndexChanged(QString)',self.collectionSelected)

    collectionNames = []
    for collection in collections:
      collectionNames.append(collection['Collection'])
    collectionNames.sort()

    for name in collectionNames:
      self.collectionSelector.addItem(name)

  def populatePatientsTableWidget(self,responseString):
    self.clearPatientsTableWidget()
    table = self.patientsTableWidget
    patients = json.loads(responseString)
    table.setRowCount(len(patients))
    n = 0
    for patient in patients:
      keys = patient.keys()
      for key in keys:
        if key == 'PatientID':
          patientIDString = str(patient['PatientID'])
          patientID = qt.QTableWidgetItem(patientIDString)
          self.patientsIDs.append(patientID)
          table.setItem(n,0,patientID)
          if patientIDString[0:4] == 'TCGA':
            patientID.setIcon(self.reportIcon)
        if key == 'PatientName':
          patientName = qt.QTableWidgetItem(str(patient['PatientName']))
          self.patientNames.append(patientName)
          table.setItem(n,1,patientName )
        if key == 'PatientBirthDate':
          patientBirthDate= qt.QTableWidgetItem(str(patient['PatientBirthDate']))
          self.patientBirthDates.append(patientBirthDate)
          table.setItem(n,2,patientBirthDate)
        if key == 'PatientSex':
          patientSex = qt.QTableWidgetItem(str(patient['PatientSex']))
          self.patientSexes.append(patientSex)
          table.setItem(n,3,patientSex)
        if key == 'EthnicGroup':
          ethnicGroup= qt.QTableWidgetItem(str(patient['EthnicGroup']))
          self.ethnicGroups.append(ethnicGroup)
          table.setItem(n,4,ethnicGroup)
      n += 1
    self.patientsTableWidget.resizeColumnsToContents()
    self.patientsTableWidgetHeader.setStretchLastSection(True)

  def populateStudiesTableWidget(self,responseString):
    self.studiesSelectAllButton.enabled = True
    self.studiesSelectNoneButton.enabled = True
    #self.clearStudiesTableWidget()
    table = self.studiesTableWidget
    studies = json.loads(responseString)

    n = self.studiesTableRowCount
    table.setRowCount(n+len(studies))

    for study in studies:
      keys = study.keys()
      for key in keys:
        if key == 'StudyInstanceUID':
          studyInstanceUID= qt.QTableWidgetItem(str(study['StudyInstanceUID']))
          self.studyInstanceUIDs.append(studyInstanceUID)
          table.setItem(n,0,studyInstanceUID)
        if key == 'StudyDate':
          studyDate = qt.QTableWidgetItem(str(study['StudyDate']))
          self.studyDates.append(studyDate)
          table.setItem(n,1,studyDate)
        if key == 'StudyDescription':
          studyDescription = qt.QTableWidgetItem(str(study['StudyDescription']))
          self.studyDescriptions.append(studyDescription)
          table.setItem(n,2,studyDescription)
        if key == 'AdmittingDiagnosesDescriptions':
          admittingDiagnosesDescription= qt.QTableWidgetItem(str(study['AdmittingDiagnosesDescriptions']))
          self.admittingDiagnosesDescriptions.append(admittingDiagnosesDescription)
          table.setItem(n,3,admittingDiagnosesDescription)
        if key == 'StudyID':
          studyID= qt.QTableWidgetItem(str(study['StudyID']))
          self.studyIDs.append(studyID)
          table.setItem(n,4,studyID)
        if key == 'PatientAge':
          patientAge = qt.QTableWidgetItem(str(study['PatientAge']))
          self.patientAges.append(patientAge)
          table.setItem(n,5,patientAge)
        if key == 'SeriesCount':
          seriesCount = qt.QTableWidgetItem(str(study['SeriesCount']))
          self.seriesCounts.append(seriesCount)
          table.setItem(n,6,seriesCount)
      n += 1
    self.studiesTableWidget.resizeColumnsToContents()
    self.studiesTableWidgetHeader.setStretchLastSection(True)
    self.studiesTableRowCount = n

  def populateSeriesTableWidget(self,responseString):
    #self.clearSeriesTableWidget()
    table = self.seriesTableWidget
    seriesCollection = json.loads(responseString)
    self.seriesSelectAllButton.enabled = True
    self.seriesSelectNoneButton.enabled = True

    n = self.seriesTableRowCount
    table.setRowCount(n+len(seriesCollection))

    for series in seriesCollection:
      keys = series.keys()
      for key in keys:
        if key == 'SeriesInstanceUID':
          seriesInstanceUID = str(series['SeriesInstanceUID'])
          seriesInstanceUIDItem = qt.QTableWidgetItem(seriesInstanceUID)
          self.seriesInstanceUIDs.append(seriesInstanceUIDItem)
          table.setItem(n,0,seriesInstanceUIDItem)
          if any(seriesInstanceUID == s for s in self.previouslyDownloadedSeries):
            icon = self.storedlIcon
          else:
            icon = self.downloadIcon
          downloadStatusItem = qt.QTableWidgetItem(str(''))
          downloadStatusItem.setTextAlignment(qt.Qt.AlignCenter)
          downloadStatusItem.setIcon(icon)
          self.downloadStatusCollection.append(downloadStatusItem)
          table.setItem(n,1,downloadStatusItem)
        if key == 'Modality':
          modality = qt.QTableWidgetItem(str(series['Modality']))
          self.modalities.append(modality)
          table.setItem(n,2,modality)
        if key == 'ProtocolName':
          protocolName = qt.QTableWidgetItem(str(series['ProtocolName']))
          self.protocolNames.append(protocolName)
          table.setItem(n,3,protocolName)
        if key == 'SeriesDate':
          seriesDate = qt.QTableWidgetItem(str(series['SeriesDate']))
          self.seriesDates.append(seriesDate)
          table.setItem(n,4,seriesDate)
        if key == 'SeriesDescription':
          seriesDescription = qt.QTableWidgetItem(str(series['SeriesDescription']))
          self.seriesDescriptions.append(seriesDescription)
          table.setItem(n,5,seriesDescription)
        if key == 'BodyPartExamined':
          bodyPartExamined = qt.QTableWidgetItem(str(series['BodyPartExamined']))
          self.bodyPartsExamined.append(bodyPartExamined)
          table.setItem(n,6,bodyPartExamined)
        if key == 'SeriesNumber':
          seriesNumber = qt.QTableWidgetItem(str(series['SeriesNumber']))
          self.seriesNumbers.append(seriesNumber)
          table.setItem(n,7,seriesNumber)
        if key == 'AnnotationsFlag':
          annotationsFlag = qt.QTableWidgetItem(str(series['AnnotationsFlag']))
          self.annotationsFlags.append(annotationsFlag)
          table.setItem(n,8,annotationsFlag)
        if key == 'Manufacturer':
          manufacturer = qt.QTableWidgetItem(str(series['Manufacturer']))
          self.manufacturers.append(manufacturer)
          table.setItem(n,9,manufacturer)
        if key == 'ManufacturerModelName':
          manufacturerModelName = qt.QTableWidgetItem(str(series['ManufacturerModelName']))
          self.manufacturerModelNames.append(manufacturerModelName )
          table.setItem(n,10,manufacturerModelName)
        if key == 'SoftwareVersions':
          softwareVersions = qt.QTableWidgetItem(str(series['SoftwareVersions']))
          self.softwareVersionsCollection.append(softwareVersions )
          table.setItem(n,11,softwareVersions)
        if key == 'ImageCount':
          imageCount = qt.QTableWidgetItem(str(series['ImageCount']))
          self.imageCounts.append(imageCount )
          table.setItem(n,12,imageCount )
      n += 1
    self.seriesTableWidget.resizeColumnsToContents()
    self.seriesTableRowCount = n
    self.seriesTableWidgetHeader.setStretchLastSection(True)

  def clearPatientsTableWidget(self):
    table = self.patientsTableWidget
    self.patientsCollapsibleGroupBox.setTitle('Patients')
    self.patientsIDs =[]
    self.patientNames = []
    self.patientBirthDates = []
    self.patientSexes = []
    self.ethnicGroups = []
    #self.collections = []
    table.clear()
    table.setHorizontalHeaderLabels(self.patientsTableHeaderLabels)

  def clearStudiesTableWidget(self):
    self.studiesTableRowCount = 0
    table = self.studiesTableWidget
    self.studiesCollapsibleGroupBox.setTitle('Studies')
    self.studyInstanceUIDs =[]
    self.studyDates = []
    self.studyDescriptions = []
    self.admittingDiagnosesDescriptions = []
    self.studyIDs = []
    self.patientAges = []
    self.seriesCounts = []
    table.clear()
    table.setHorizontalHeaderLabels(self.studiesTableHeaderLabels)

  def clearSeriesTableWidget(self):
    self.seriesTableRowCount = 0
    table = self.seriesTableWidget
    self.seriesCollapsibleGroupBox.setTitle('Series')
    self.seriesInstanceUIDs= []
    self.downloadStatusCollection = []
    self.modalities = []
    self.protocolNames = []
    self.seriesDates = []
    self.seriesDescriptions = []
    self.bodyPartsExamined = []
    self.seriesNumbers =[]
    self.annotationsFlags = []
    self.manufacturers = []
    self.manufacturerModelNames = []
    self.softwareVersionsCollection = []
    self.imageCounts = []
    table.clear()
    table.setHorizontalHeaderLabels(self.seriesTableHeaderLabels)

  def onReload(self,moduleName="TCIABrowser"):
    """Generic reload method for any scripted module.
    ModuleWizard will subsitute correct default moduleName.
    """
    import imp, sys, os, slicer
    import time
    import urllib2, urllib,sys, os
    import xml.etree.ElementTree as ET
    import webbrowser
    import string, json
    import csv
    import zipfile, os.path

    widgetName = moduleName + "Widget"

    # reload the source code
    # - set source file path
    # - load the module to the global space
    filePath = eval('slicer.modules.%s.path' % moduleName.lower())
    p = os.path.dirname(filePath)
    if not sys.path.__contains__(p):
      sys.path.insert(0,p)
    fp = open(filePath, "r")
    globals()[moduleName] = imp.load_module(
        moduleName, fp, filePath, ('.py', 'r', imp.PY_SOURCE))
    fp.close()

    # rebuild the widget
    # - find and hide the existing widget
    # - create a new widget in the existing parent
    parent = slicer.util.findChildren(name='%s Reload' % moduleName)[0].parent().parent()
    for child in parent.children():
      try:
        child.hide()
      except AttributeError:
        pass
    # Remove spacer items
    item = parent.layout().itemAt(0)
    while item:
      parent.layout().removeItem(item)
      item = parent.layout().itemAt(0)

    # delete the old widget instance
    if hasattr(globals()['slicer'].modules, widgetName):
      getattr(globals()['slicer'].modules, widgetName).cleanup()

    # create new widget inside existing parent
    globals()[widgetName.lower()] = eval(
        'globals()["%s"].%s(parent)' % (moduleName, widgetName))
    globals()[widgetName.lower()].setup()
    setattr(globals()['slicer'].modules, widgetName, globals()[widgetName.lower()])

  def onReloadAndTest(self,moduleName="TCIABrowser"):
    self.onReload()
    evalString = 'globals()["%s"].%sTest()' % (moduleName, moduleName)
    tester = eval(evalString)
    tester.runTest()
#
# TCIABrowserLogic
#

class TCIABrowserLogic:
  """This class should implement all the actual 
  computation done by your module.  The interface 
  should be such that other python code can import
  this class and make use of the functionality without
  requiring an instance of the Widget
  """
  def __init__(self):
    pass

  def hasImageData(self,volumeNode):
    """This is a dummy logic method that 
    returns true if the passed in volume
    node has valid image data
    """
    if not volumeNode:
      print('no volume node')
      return False
    if volumeNode.GetImageData() == None:
      print('no image data')
      return False
    return True

  def delayDisplay(self,message,msec=1000):
    #
    # logic version of delay display
    #
    print(message)
    self.info = qt.QDialog()
    self.infoLayout = qt.QVBoxLayout()
    self.info.setLayout(self.infoLayout)
    self.label = qt.QLabel(message,self.info)
    self.infoLayout.addWidget(self.label)
    qt.QTimer.singleShot(msec, self.info.close)
    self.info.exec_()

  def takeScreenshot(self,name,description,type=-1):
    # show the message even if not taking a screen shot
    self.delayDisplay(description)

    if self.enableScreenshots == 0:
      return

    lm = slicer.app.layoutManager()
    # switch on the type to get the requested window
    widget = 0
    if type == -1:
      # full window
      widget = slicer.util.mainWindow()
    elif type == slicer.qMRMLScreenShotDialog().FullLayout:
      # full layout
      widget = lm.viewport()
    elif type == slicer.qMRMLScreenShotDialog().ThreeD:
      # just the 3D window
      widget = lm.threeDWidget(0).threeDView()
    elif type == slicer.qMRMLScreenShotDialog().Red:
      # red slice window
      widget = lm.sliceWidget("Red")
    elif type == slicer.qMRMLScreenShotDialog().Yellow:
      # yellow slice window
      widget = lm.sliceWidget("Yellow")
    elif type == slicer.qMRMLScreenShotDialog().Green:
      # green slice window
      widget = lm.sliceWidget("Green")

    # grab and convert to vtk image data
    qpixMap = qt.QPixmap().grabWidget(widget)
    qimage = qpixMap.toImage()
    imageData = vtk.vtkImageData()
    slicer.qMRMLUtils().qImageToVtkImageData(qimage,imageData)

    annotationLogic = slicer.modules.annotations.logic()
    annotationLogic.CreateSnapShot(name, description, type, self.screenshotScaleFactor, imageData)

  def run(self,inputVolume,outputVolume,enableScreenshots=0,screenshotScaleFactor=1):
    """
    Run the actual algorithm
    """

    self.delayDisplay('Running the aglorithm')

    self.enableScreenshots = enableScreenshots
    self.screenshotScaleFactor = screenshotScaleFactor

    self.takeScreenshot('TCIABrowser-Start','Start',-1)

    return True


class TCIABrowserTest(unittest.TestCase):
  """
  This is the test case for your scripted module.
  """

  def delayDisplay(self,message,msec=1000):
    """This utility method displays a small dialog and waits.
    This does two things: 1) it lets the event loop catch up
    to the state of the test so that rendering and widget updates
    have all taken place before the test continues and 2) it
    shows the user/developer/tester the state of the test
    so that we'll know when it breaks.
    """
    print(message)
    self.info = qt.QDialog()
    self.infoLayout = qt.QVBoxLayout()
    self.info.setLayout(self.infoLayout)
    self.label = qt.QLabel(message,self.info)
    self.infoLayout.addWidget(self.label)
    qt.QTimer.singleShot(msec, self.info.close)
    self.info.exec_()

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear(0)

  def runTest(self):
    import traceback
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.testBrowserDownloadAndLoad()

  def testBrowserDownloadAndLoad(self):
    self.delayDisplay("Starting browser test")
    mainWindow = slicer.util.mainWindow()
    if mainWindow:
      mainWindow.moduleSelector().selectModule('TCIABrowser')
      if 'TCIABrowser' in slicer.util.moduleNames():
        module = slicer.modules.tciabrowser
        moduleWidget = module.widgetRepresentation()
        children = moduleWidget.findChildren('QPushButton')
        activeWindow = slicer.app.activeWindow()
        if activeWindow.windowTitle == 'TCIA Browser':
          browserWindow = activeWindow
        if browserWindow != None:
          collectionsCombobox = browserWindow.findChildren('QComboBox')[0]
          print 'Number of collections: ',collectionsCombobox.count
          if collectionsCombobox.count> 0:
            collectionsCombobox.setCurrentIndex(randint(0,collectionsCombobox.count-1))
            currentCollection = collectionsCombobox.currentText
            if currentCollection != '':
              print 'connected to the server successfully'
              print 'current collection :', currentCollection

            tableWidgets = browserWindow.findChildren('QTableWidget')

            patientsTable = tableWidgets[0]
            if patientsTable.rowCount> 0:
              selectedRow = randint(0,patientsTable.rowCount-1)
              selectedPatient = patientsTable.item(selectedRow,0).text()
              if selectedPatient != '':
                print 'current patient:', selectedPatient
                patientsTable.selectRow(selectedRow)

              studiesTable = tableWidgets[1]
              if studiesTable.rowCount> 0:
                selectedRow = randint(0,studiesTable.rowCount-1)
                selectedStudy = studiesTable.item(selectedRow,0).text()
                if selectedStudy != '':
                  print 'current study:', selectedStudy
                  studiesTable.selectRow(selectedRow)

                seriesTable = tableWidgets[2]
                if seriesTable.rowCount> 0:
                  selectedRow = randint(0,seriesTable.rowCount-1)
                  selectedSeries = seriesTable.item(selectedRow,0).text()
                  if selectedSeries != '':
                    print 'current series:', selectedSeries
                    seriesTable.selectRow(selectedRow)

                  pushButtons = browserWindow.findChildren('QPushButton')
                  for pushButton in pushButtons:
                    toolTip = pushButton.toolTip
                    if toolTip[16:20] == 'Load':
                      print toolTip[16:20]
                      loadButton = pushButton

                  if loadButton != None:
                    print 'load button clicked'
                    loadButton.click()
                  else:
                    print 'could not find Load button'
      else:
        print "Test Failed. Couldn't get slicer.modules.tciabrowser."
    else:
        print "Test Failed. There was no main window."
    scene = slicer.mrmlScene
    self.assertEqual(scene.GetNumberOfNodesByClass('vtkMRMLScalarVolumeNode'), 1)
    self.delayDisplay('Browser Test Passed!')

