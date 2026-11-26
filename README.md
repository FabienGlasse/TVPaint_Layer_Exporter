# TVPaint Layer Exporter

Export the layers of a TVPaint clip as image sequences, with customizable export and folder options. With delivery reports that an animator can hand to compositing.

![TVPaint Layer Exporter in Auto Mode with an example clip and layer stack](docs/assets/screenshots/exporter-window.png)

TVPaint Layer Exporter will lists the current clip's layers, lets you choose settings like frame range and image format, and will automatically activate/inactivate layers to export images sequences, before restoring your file to its original state. Auto Mode makes a new dated folder for each export. Manual Mode keeps one folder for a series of exports and can combine selected layers into one sequence for more personal workflows. Exports can be interrupted and resumed. TVPaint must be running with the scene open for the exporter and bridge to work.

The TVPaint connection uses [BRUNCH Studio's tvpaint-rpc](https://github.com/brunchstudio/tvpaint-rpc). Their work makes it possible for the exporter to read the current clip and send export commands to TVPaint. The installer downloads the matching connection component from their project.

The layer list shows TVPaint's colour labels. Choose **AUTO** for individual layer exports, **MANUAL** to build a delivery over several exports, or **LAYER COLORS** for one combined sequence per colour group. The active mode is orange. Layer Colors starts with visible coloured layers selected; use the group checkboxes or individual layers to adjust the selection. Each export creates a new folder. Sequences use the top checked layer's name by default; naming settings also offer the bottom layer, TVPaint's color group names, or approximate universal color names such as Red, Green and Blue. Groups stay separate even when their approximate names match. Hover over buttons for help, or click **?** beside **Connect / Refresh** for the guided tutorial.

![Layer Colors with separate colour group and layer stack panes and sequence-name previews](docs/assets/screenshots/layer-colors.png)

Check **Use custom names** under **Edit sequence naming** to review and rename each output sequence before exporting. The window shows its colour group, source name and filename preview.

![Use custom names with editable sequence names, colour swatches and grey filename previews](docs/assets/screenshots/custom-names.png)

## Get started

Download one of the two packages from [Releases](https://github.com/FabienGlasse/TVPaint_Layer_Exporter/releases):

| Package | Start with |
| --- | --- |
| Guided CMD installer | Extract the ZIP, then open `Install.bat`. It asks before each setup stage. |
| Conventional installer | Extract the ZIP, then open `TVPaintLayerExporterSetup.exe`. Leave the final configuration option selected. |

Close TVPaint before installation. Setup needs an internet connection and Windows administrator approval to install the TVPaint connection component. When setup finishes, open TVPaint and use the **TVPaint Layer Exporter** desktop shortcut. The [User Guide](docs/assets/User%20Guide.html) walks through the first export, settings, Manual Mode, delivery and uninstalling without assuming any knowledge of Python.

The installer was trialled on Windows 11 with TVPaint 11.7.3 and 12.1.0.

## Updates

Click **Check for updates** at the bottom of the exporter to check published GitHub releases. Read the release notes, then choose **Download and update**. The exporter verifies the download, closes, updates its application files and opens again. Settings, exported images, Python and the TVPaint connection component are kept. Failed file replacements restore the previous application files from a backup. Releases that need different Python or TVPaint components use the full installer instead.

Install a package containing the updater once to add this button to an older installation. Source checkouts update through Git. Update checks happen only when requested.

## In the export folder

Each selected layer normally gets its own sequence folder. You can also combine checked layers, put all images at the export folder root, add separate folder and filename prefixes, or include the TVPaint background. `Delivery Report.txt` records the full source layer for compositing use and adds the details of each export. A hidden `export_manifest.json` keeps the latest export's resume information.

## Source and build

The exporter source is in [exporter](exporter); the guided and conventional installers are in [packaging](packaging). See [Building and testing](BUILDING.md) for the test commands and package build. The source checkout is for development; freelancers should use a release package.

Created by Fabien Glasse. See [copyright and use](COPYRIGHT.md) and [third-party components](THIRD_PARTY.md).
