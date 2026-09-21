"""Host-side clients and entry points for the ethernet diagnostic.

`images.py` is the image-service client: the only host-side implementation of
the wire protocol in `PROTOCOL.md`, and the way anything that is not the FPGA
reaches the emulated card.

It is a package, and stays one, because that is how it is reached from outside.
The `linux-consoles` repository drives targets off this card and imports this
client by path rather than vendoring a copy, which would drift from the
gateware it speaks to: it loads `images.py` from the directory named by
`SD_EMULATOR_CLIENT_DIR`, defaulting to this one. The host tests here import it
the same way the shipped entry points do, as `from scripts import images`, with
`projects/ethernet-diagnostic` as the discovery root. Both of those are an
interface: this directory's name, the module's name, and the package `__init__`
that makes the import work are not free to change on their own.
"""
