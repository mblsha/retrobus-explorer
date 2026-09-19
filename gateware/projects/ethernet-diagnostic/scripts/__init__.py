"""Host-side clients and entry points for the ethernet diagnostic.

`images.py` is the image-service client and is shared beyond the RG35XX work,
so it stays here rather than moving into the `rg35xx` package; the package
imports it as `from scripts import images`.
"""
