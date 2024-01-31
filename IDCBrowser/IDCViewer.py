import json
import logging
import os
import platform
import unittest
from urllib.request import urlopen

import ctk
import pkg_resources
import qt
import slicer
import vtk
from packaging import version
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

# Register slicer url
def register_linux_slicer_url_protocol():
    if platform.system() == "Linux":
        # Check if the protocol is already registered
        if os.path.exists(
            os.path.expanduser("~/.local/share/applications/slicer.desktop")
        ):
            print("Slicer URL protocol is already registered.")
            return
        # Register Slicer URL protocol
        with open(
            os.path.expanduser("~/.local/share/applications/slicer.desktop"), "w"
        ) as f:
            f.write(
                f"""[Desktop Entry]
Name=Slicer
Exec={get_slicer_location()} %u
Type=Application
Terminal=false
MimeType=x-scheme-handler/slicer;
"""
            )
        # Update MIME database
        os.system("update-desktop-database ~/.local/share/applications/")
        os.system("xdg-mime default slicer.desktop x-scheme-handler/slicer")
    else:
        print(
            "Slicer URL protocol registration is not supported on this operating system."
        )


def get_slicer_location():
    launcherPath = qt.QDir.toNativeSeparators(
        qt.QFileInfo(slicer.app.launcherExecutableFilePath).absoluteFilePath()
    )
    return launcherPath


register_linux_slicer_url_protocol()

def check_macos_slicer_protocol_registration():
    plist_path = os.path.expanduser("/Applications/slicer-app.app/Contents/Info.plist")
    return os.path.exists(plist_path)

def register_macos_slicer_url_protocol():
    if check_macos_slicer_protocol_registration():
        print("Slicer URL protocol is already registered.")
        return

    # Create the AppleScript
    applescript_path = os.path.expanduser("~/slicer.applescript")
    with open(applescript_path, "w") as applescript_file:
        applescript_file.write("""
on open location this_URL
    do shell script "/Applications/Slicer.app/Contents/MacOS/Slicer " & quoted form of this_URL
end open location
""")

    # Compile the AppleScript into an app
    os.system(f"osacompile -o /Applications/slicer-app.app {applescript_path}")


    # Create or modify the plist file
    plist_content = """
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleAllowMixedLocalizations</key>
    <true/>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>applet</string>
    <key>CFBundleIconFile</key>
    <string>applet</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>slicer-app</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>aplt</string>
    <key>LSMinimumSystemVersionByArchitecture</key>
    <dict>
        <key>x86_64</key>
        <string>10.6</string>
    </dict>
    <key>LSRequiresCarbon</key>
    <true/>
    <key>NSAppleEventsUsageDescription</key>
    <string>This script needs to control other applications to run.</string>
    <key>NSAppleMusicUsageDescription</key>
    <string>This script needs access to your music to run.</string>
    <key>NSCalendarsUsageDescription</key>
    <string>This script needs access to your calendars to run.</string>
    <key>NSCameraUsageDescription</key>
    <string>This script needs access to your camera to run.</string>
    <key>NSContactsUsageDescription</key>
    <string>This script needs access to your contacts to run.</string>
    <key>NSHomeKitUsageDescription</key>
    <string>This script needs access to your HomeKit Home to run.</string>
    <key>NSMicrophoneUsageDescription</key>
    <string>This script needs access to your microphone to run.</string>
    <key>NSPhotoLibraryUsageDescription</key>
    <string>This script needs access to your photos to run.</string>
    <key>NSRemindersUsageDescription</key>
    <string>This script needs access to your reminders to run.</string>
    <key>NSSiriUsageDescription</key>
    <string>This script needs access to Siri to run.</string>
    <key>NSSystemAdministrationUsageDescription</key>
    <string>This script needs access to administer this system to run.</string>
    <key>OSAAppletShowStartupScreen</key>
    <false/>
    <key>CFBundleIdentifier</key>
    <string>slicer.protocol.registration</string>
    <key>CFBundleURLTypes</key>
    <array>
        <dict>
            <key>CFBundleURLName</key>
            <string>Slicer</string>
            <key>CFBundleURLSchemes</key>
            <array>
                <string>slicer</string>
            </array>
        </dict>
    </array>
</dict>
</plist>
"""

    plist_path = os.path.expanduser("/Applications/slicer-app.app/Contents/Info.plist")
    with open(plist_path, "w") as plist_file:
        plist_file.write(plist_content)

    print("Slicer URL protocol registered successfully.")


register_macos_slicer_url_protocol()

def is_module_installed(module_name):
    """
    This function checks if a Python package is installed.

    Parameters:
    module_name (str): The name of the module to check.

    Returns:
    bool: True if the module is installed, False otherwise.
    """
    try:
        pkg_resources.get_distribution(module_name)
        return True
    except pkg_resources.DistributionNotFound:
        return False


package_name = "idc-index"

if is_module_installed(package_name):
    print(package_name + " is installed\n")
    print(f"Checking if the {package_name} is outdated\n")
    # Check if the package is outdated
    installed_version = version.parse(
        pkg_resources.get_distribution(package_name).version
    )
    available_version = None

    try:
        response = urlopen(f"https://pypi.org/pypi/{package_name}/json")
        data = json.loads(response.read())
        available_version = version.parse(data["info"]["version"])
    except Exception as e:
        print(f"Error fetching available version: {e}")

    if available_version and installed_version < available_version:
        print(package_name + " is outdated")
        slicer.util.pip_install(package_name)
    else:
        print(package_name + " is up-to-date")
else:
    print(f"{package_name} is not installed, installing {package_name}")
    slicer.util.pip_install(package_name)


from idc_index import index

idc_client = index.IDCClient()

#
# IDCViewer
#


class IDCViewer(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "IDC Viewer"
        self.parent.categories = ["Utilities"]
        self.parent.dependencies = []
        self.parent.contributors = [
            "Vamsi Thiriveedhi (BWH), Andrey Fedorov(BWH), Steve Pieper (Isomics Inc.)"
        ]
        self.parent.helpText = """
This module loads ImagingDataCommons data from custom URLs such as:
slicer://idc-browser/?download=1.2.840.113654.2.55.154809705591242159075253605419469935510
"""
        self.parent.acknowledgementText = """
This file was modified from the origin version developed by Andras Lasso, PerkLab and ASH. 
The modified version is developed by Vamsi Thiriveedhi, Andrey Fedorov, and Steve Pieper 
to integrate with ImagingDataCommons 
"""
        # Initilize self.sampleDataLogic. At this point, Slicer modules are not initialized yet, so we cannot instantiate the logic yet.
        self.sampleDataLogic = None

        slicer.app.connect("urlReceived(QString)", self.onURLReceived)

    def reportProgress(self, message, logLevel=None):
        # Print progress in the console
        print(f"Loading... {self.sampleDataLogic.downloadPercent}%")
        # Abort download if cancel is clicked in progress bar
        if self.progressWindow.wasCanceled:
            raise Exception("download aborted")
        # Update progress window
        self.progressWindow.show()
        self.progressWindow.activateWindow()
        self.progressWindow.setValue(int(self.sampleDataLogic.downloadPercent))
        self.progressWindow.setLabelText("Downloading...")
        # Process events to allow screen to refresh
        slicer.app.processEvents()

    def center3dViews(self):
        layoutManager = slicer.app.layoutManager()
        for threeDViewIndex in range(layoutManager.threeDViewCount):
            threeDWidget = layoutManager.threeDWidget(0)
            threeDView = threeDWidget.threeDView()
            threeDView.resetFocalPoint()

    def showSliceViewsIn3d(self):
        layoutManager = slicer.app.layoutManager()
        for sliceViewName in layoutManager.sliceViewNames():
            controller = layoutManager.sliceWidget(sliceViewName).sliceController()
            controller.setSliceVisible(True)

    def onURLReceived(self, urlString):
        """Process DICOM view requests. URL protocol and path must be: slicer://viewer/
        Query parameters:
          - `download`: download and show with default file type
          - `image` or `volume`: download and show as image
          - `segmentation`: download and show as segmentation
          - `show3d`: show segmentation in 3D and center 3D view
          - `filename`: filename to specify file format and node name for the first node; useful if the download URL does not contain filename

        Display a file (using default file type):

            slicer://viewer/?download=https%3A%2F%2Fgithub.com%2Frbumm%2FSlicerLungCTAnalyzer%2Freleases%2Fdownload%2FSampleData%2FLungCTAnalyzerChestCT.nrrd

        Display a segmentation and volume file:

            slicer://viewer/?show3d=true&segmentation=https%3A%2F%2Fgithub.com%2Frbumm%2FSlicerLungCTAnalyzer%2Freleases%2Fdownload%2FSampleData%2FLungCTAnalyzerMaskSegmentation.seg.nrrd&image=https%3A%2F%2Fgithub.com%2Frbumm%2FSlicerLungCTAnalyzer%2Freleases%2Fdownload%2FSampleData%2FLungCTAnalyzerChestCT.nrrd

        """
        logging.info(f"URL received: {urlString}")

        # Check if we understand this URL
        url = qt.QUrl(urlString)
        if url.authority().lower() != "idc-browser":
            return
        query = qt.QUrlQuery(url)

        # Parse options
        queryMap = {}
        for key, value in query.queryItems(qt.QUrl.FullyDecoded):
            queryMap[key] = value

        # Get list of files to load
        filesToOpen = []
        for nodeIndex, [key, value] in enumerate(
            query.queryItems(qt.QUrl.FullyDecoded)
        ):
            if key == "download":
                fileType = None
            elif key == "image" or key == "volume":
                fileType = "VolumeFile"
            elif key == "segmentation":
                fileType = "SegmentationFile"
            else:
                continue
            downloadUrl = qt.QUrl(value)

            # Get the node name from URL
            if (nodeIndex == 0) and ("filename" in queryMap):
                baseName = queryMap["filename"]
            else:
                baseName = os.path.basename(downloadUrl.path())

            nodeName, ext = os.path.splitext(baseName)
            # Generate random filename to avoid reusing/overwriting older downloaded files that may have the same name
            import uuid

            fileName = f"{nodeName}-{uuid.uuid4().hex}{ext}"
            info = {
                "downloadUrl": downloadUrl,
                "nodeName": nodeName,
                "fileName": fileName,
                "fileType": fileType,
            }
            filesToOpen.append(info)

        if not filesToOpen:
            return

        show3d = False
        if "show3d" in queryMap:
            print("Show 3d")
            show3d = slicer.util.toBool(queryMap["show3d"])

        # Ensure sampleData logic is created
        if not self.sampleDataLogic:
            import SampleData

            self.sampleDataLogic = SampleData.SampleDataLogic()

        for info in filesToOpen:
            downloadUrlString = info["downloadUrl"].toString()
            logging.info(
                f"Download URL detected - get the file from {downloadUrlString} and load it now"
            )
            try:
                self.progressWindow = slicer.util.createProgressDialog()
                self.sampleDataLogic.logMessage = self.reportProgress

                # loadedNodes = self.sampleDataLogic.downloadFromURL(nodeNames=info["nodeName"], fileNames=info["fileName"], uris=downloadUrlString, loadFileTypes=info["fileType"])

                destFolderPath = (
                    slicer.mrmlScene.GetCacheManager().GetRemoteCacheDirectory()
                )
                seriesInstanceUID = str(downloadUrl)

                # Create a new folder named with 'seriesInstanceUID' in 'destFolderPath'
                download_folder_path = os.path.join(
                    destFolderPath, str(seriesInstanceUID)
                )

                print("seriesInstanceUID: " + seriesInstanceUID)
                print("destFolderPath " + download_folder_path)

                # Download the DICOM series to the new folder
                idc_client.download_dicom_series(
                    seriesInstanceUID=seriesInstanceUID,
                    downloadDir=download_folder_path,
                )

                indexer = ctk.ctkDICOMIndexer()
                indexer.addDirectory(slicer.dicomDatabase, download_folder_path)

                plugin = slicer.modules.dicomPlugins["DICOMScalarVolumePlugin"]()
                seriesUID = seriesInstanceUID.replace("'", "")
                dicomDatabase = slicer.dicomDatabase
                fileList = slicer.dicomDatabase.filesForSeries(seriesUID)
                loadables = plugin.examine([fileList])
                if len(loadables) > 0:
                    volume = plugin.load(loadables[0])
                    logging.debug("Loaded volume: " + volume.GetName())
                else:
                    self.showStatus(
                        "Unable to load DICOM content. Please retry from DICOM Browser!"
                    )

                # remove downloaded file
                # os.remove(slicer.app.cachePath + "/" + info["fileName"])

                # if show3d:
                #  for loadedNode in loadedNodes:
                #    if type(loadedNode) == slicer.vtkMRMLSegmentationNode:
                # Show segmentation in 3D
                #      loadedNode.CreateClosedSurfaceRepresentation()
                # elif type(loadedNode) == slicer.vtkMRMLVolumeNode:
                #   # Show volume rendering in 3D
                #   pluginHandler = slicer.qSlicerSubjectHierarchyPluginHandler().instance()
                #   vrPlugin = pluginHandler.pluginByName("VolumeRendering")
                #   volumeItem = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene).GetItemByDataNode(loadedNode)
                #   vrPlugin.setDisplayVisibility(volumeItem, True)
                #   vrPlugin.showVolumeRendering(True, volumeItem)
            finally:
                self.progressWindow.close()

        if show3d:
            self.center3dViews()
            self.showSliceViewsIn3d()
