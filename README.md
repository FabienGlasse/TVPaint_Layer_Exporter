# TVPaint Layer Exporter

Export the layers of a TVPaint clip as image sequences, with a folder and delivery report that an artist can hand to compositing.

![TVPaint Layer Exporter in Auto Mode with an example clip and layer stack](docs/assets/exporter-window.png)

The exporter lists the current clip's layers, lets you choose a frame range and image format, and shows filenames before it writes anything. Auto Mode makes a new dated folder for each export. Manual Mode keeps one folder for a series of exports and can combine selected layers into one sequence. Interrupted exports can be resumed when the source scene has not changed.

## Get started

Download one of the two packages from [Releases](https://github.com/FabienGlasse/TVPaint-Layer-Exporter/releases):

| Package | Start with |
| --- | --- |
| Guided CMD installer | Extract the ZIP, then open `Install.bat`. It asks before each setup stage. |
| Conventional installer | Extract the ZIP, then open `TVPaintLayerExporterSetup.exe`. Leave the final configuration option selected. |

Close TVPaint before installation. Setup may need an internet connection and Windows administrator approval to install the TVPaint connection component. When setup finishes, open TVPaint and use the **TVPaint Layer Exporter** desktop shortcut. The [User Guide](packaging/User%20Guide.html) walks through the first export, Manual Mode, delivery and uninstalling without assuming any knowledge of Python.

The installer targets 64-bit Windows with TVPaint 11.7.3 or 12.1.0. TVPaint 11.7.3 has been used for live export checks. The TVPaint 12.1.0 installer path has been corrected based on setup logs, but a complete live export on 12.1.0 still needs confirmation.

## In the export folder

Each selected layer normally gets its own sequence folder. You can also combine checked layers, put all images at the export folder root, add separate folder and filename prefixes, or include the TVPaint background. `Delivery Report.txt` records the full source layer stack once and adds the details of each export. A hidden `export_manifest.json` keeps the latest export's resume information.

## Source and build

The exporter source is in [portable_exporter](portable_exporter); the guided and conventional installers are in [packaging](packaging). See [Building and testing](BUILDING.md) for the test commands and package build. The source checkout is for development; freelancers should use a release package.

Created by Fabien Glasse. See [copyright and use](COPYRIGHT.md) and [third-party components](THIRD_PARTY.md).
