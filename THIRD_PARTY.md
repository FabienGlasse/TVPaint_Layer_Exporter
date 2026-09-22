# Third-party components

The installer obtains Python from [python.org](https://www.python.org/) when needed and installs the Python packages listed in [requirements.txt](exporter/requirements.txt) from PyPI. These components retain their own licenses.

The TVPaint connection component is [BRUNCH Studio's tvpaint-rpc](https://github.com/brunchstudio/tvpaint-rpc), licensed under MIT. Setup downloads the version matched to TVPaint 11.7.3 or 12.1.0 and verifies its SHA-256 checksum before installation. The component is not stored in this repository or inside the release packages. Its [license](https://github.com/brunchstudio/tvpaint-rpc/blob/main/LICENSE.md) applies to that component.

TVPaint is a product of TVPaint Développement. This exporter is an independent tool and is not affiliated with TVPaint Développement or BRUNCH Studio.
